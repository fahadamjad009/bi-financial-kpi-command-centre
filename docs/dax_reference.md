# DAX Reference & Engineering Decisions

Documentation for the 8 DAX measures in the US Bank Financial KPI Command Centre dashboard, plus the XBRL data engineering decisions that shaped them.

This file is the "show your engineering thinking" surface of the project — what each measure does, why it's filtered the way it is, and what gotchas were caught during development.

---

## Measure Catalogue

| # | Measure | Type | Format | Purpose |
|---|---|---|---|---|
| 1 | `Net Income FY` | Base KPI | $bn | Annual net income, FY period only, income statement source |
| 2 | `Net Income FY LY` | Time intelligence | $bn | Prior-year net income via SAMEPERIODLASTYEAR |
| 3 | `Net Income YoY %` | Derived ratio | % | Year-over-year growth |
| 4 | `Total Assets` | Semi-additive | $T | Latest balance sheet snapshot, data-aware date |
| 5 | `Total Equity` | Semi-additive | $bn | Same pattern as Total Assets |
| 6 | `ROE %` | Ratio | % | Net Income / Equity |
| 7 | `Bank Rank by Net Income` | Ranking | integer | Rank across banks via RANKX |
| 8 | `Net Income LTM` | Time intelligence | $bn | Trailing 12-month rolling total |

---

## Sense Checks (validated against reported figures)

| Bank | 2024 Net Income (dashboard) | 2024 Net Income (reported) | Match |
|---|---|---|---|
| JPM | $58.47B | ~$58.5B | ✓ |
| BAC | $26.97B | ~$27.0B | ✓ |
| WFC | $19.72B | ~$20.0B | ✓ |
| GS | $14.28B | ~$14.3B | ✓ |
| MS | $13.39B | ~$13.4B | ✓ |
| C | $12.68B | ~$12.7B | ✓ |
| **Total** | **$145.51B** | **~$145B** | **✓** |

| Bank | Total Assets (latest) | Reported | Match |
|---|---|---|---|
| JPM | ~$4.00T | $4.0T | ✓ |
| BAC | ~$3.3T | $3.3T | ✓ |
| WFC | ~$1.9T | $1.9T | ✓ |

ROE figures land in the **10–17% range** for the major banks, which is the standard expectation for US large-cap banking.

---

## Engineering Decisions

### 1. XBRL Double-Count: Net Income appears in multiple statements

**Problem:** When first built, `Net Income FY` returned exactly **2× the real value** for every bank. JPM 2024 showed $116.94B instead of $58.47B.

**Root cause:** XBRL filings report `us-gaap_NetIncomeLoss` in multiple statements:
- Income statement (the canonical source)
- Cash flow statement (as the starting point for indirect-method reconciliation)
- Sometimes statement of stockholders' equity

The Python transform correctly preserved each row (different `statement` value per row). But the original DAX measure filtered only by `concept`, so `SUM(value)` aggregated across all three statement contexts.

**Fix:** Add `dim_concept[statement] = "income"` to the filter. This restricts to the income-statement variant only.

```dax
Net Income FY =
CALCULATE(
    SUM(fact_financials[value]),
    dim_concept[concept] = "us-gaap_NetIncomeLoss",
    dim_concept[statement] = "income",    -- this line is the fix
    fact_financials[period_type] = "FY",
    fact_financials[is_breakdown] = FALSE
)
```

**Diagnostic that confirmed the issue:**

```
JPM Net Income FY 2024 — all contributing rows:
period_end_date  statement  is_breakdown  dimension     value
2024-12-31       income     False         False         5.847100e+10
2024-12-31       cashflow   False         False         5.847100e+10
Sum: 116,942,000,000  (= 2x actual)
```

### 2. Semi-Additive Balance Sheet: Don't sum across periods

**Problem:** `Total Assets` with no year filter returned **$8.17T** instead of the real ~$4.0T for JPM. Across all 6 banks (no ticker filter) it summed to even higher absurd values.

**Root cause:** Balance sheet snapshots are point-in-time values. Summing total assets across Q1, Q2, Q3, Q4 of a year is meaningless — they're not flows, they're stocks.

**First fix attempt:** `LASTDATE(dim_date[date])` returned the latest date in the dim_date table. Worked when year was filtered, but **returned blank** when no year was selected (dim_date extends to 2027 for time-intelligence padding; no fact rows exist at those future dates).

**Final fix:** Use `MAX(fact_financials[period_end_date])` instead — this iterates the **fact** table and returns the latest date that **actually has data**.

```dax
Total Assets =
VAR LastDataDate =
    CALCULATE(
        MAX(fact_financials[period_end_date]),
        dim_concept[concept] = "us-gaap_Assets",
        dim_concept[statement] = "balance",
        fact_financials[period_type] = "POINT_IN_TIME",
        fact_financials[is_breakdown] = FALSE
    )
RETURN
CALCULATE(
    SUM(fact_financials[value]),
    fact_financials[period_end_date] = LastDataDate,
    dim_concept[concept] = "us-gaap_Assets",
    dim_concept[statement] = "balance",
    fact_financials[is_breakdown] = FALSE
)
```

This pattern is reusable for any balance sheet metric (Total Liabilities, Tier 1 Capital, Total Loans, etc.).

### 3. Composite Key for dim_concept (PBI Case Insensitivity)

**Problem:** Building the relationship `fact_financials[concept] -> dim_concept[concept]` resulted in **Many-to-Many cardinality** with the warning: *"Column 'concept_key' contains a duplicate value..."*

**Root cause #1 (multi-grain):** The same XBRL concept code (e.g. `us-gaap_NetIncomeLoss`) appears in multiple statements with different labels:
- (`us-gaap_NetIncomeLoss`, `income`, "Net income")
- (`us-gaap_NetIncomeLoss`, `cashflow`, "Net income/loss")

These are distinct rows in dim_concept — meaning `concept` alone isn't a unique key.

**Root cause #2 (case sensitivity):** Even after creating a composite key `concept_key = concept + "|" + statement`, PBI still saw duplicates. Reason: **PBI does case-insensitive string comparison**, while pandas `drop_duplicates` is case-sensitive. EDGAR XBRL filings occasionally use inconsistent casing (`bac_Proceedsfrom...` vs `bac_ProceedsFrom...`) which pandas treated as distinct but PBI collapsed.

**Fix (in `src/transform.py`):**

```python
# Composite key + lowercase normalization
fact["concept_key"] = (fact["concept"] + "|" + fact["statement"]).str.lower()
```

Then dedupe dim_concept on `concept_key`. Result: 443 unique rows, PBI accepts the relationship as Many-to-One.

### 4. RANKX with HASONEVALUE Guard

**Problem:** A naive `RANKX` measure shows nonsense values at the matrix total row (since rank requires a single value to rank).

**Fix:** Wrap in `IF(HASONEVALUE(dim_company[ticker]), ...)` so the rank only computes when exactly one ticker is in filter context.

```dax
Bank Rank by Net Income =
IF(
    HASONEVALUE(dim_company[ticker]),
    RANKX(
        ALL(dim_company[ticker]),
        [Net Income FY],
        ,
        DESC,
        Dense
    )
)
```

`ALL(dim_company[ticker])` removes any ticker filter so the rank is computed across the full set of banks regardless of which row is being evaluated.

### 5. Date Table Marking

`dim_date` is explicitly marked as the date table in PBI with `date` as the key column. This enables:

- `SAMEPERIODLASTYEAR` (used in `Net Income FY LY`)
- `DATESINPERIOD` (used in `Net Income LTM`)
- Built-in time intelligence on the dim_date columns

Without this marking, time intelligence functions return wrong results or fail silently.

---

## Patterns Worth Remembering

1. **For XBRL data:** Always filter by `statement` for income/cashflow metrics to avoid double-counting from cross-statement appearances.
2. **For balance sheet measures:** Use `MAX(fact[period_end_date])` rather than `LASTDATE(dim_date[date])` to find the latest date that actually has data — survives time-table padding.
3. **For composite keys spanning multi-grain dims:** Lowercase-normalize when the target consumer (PBI, SQL Server, etc.) is case-insensitive. Pandas isn't, and your dedupe will silently leak duplicates.
4. **For ranking measures:** Always guard with `HASONEVALUE` for the dimension being ranked, or accept that totals will show garbage.
5. **For star schema:** Many-to-One cardinality with Single-direction cross-filtering is the default. If PBI auto-detects Many-to-Many, that's a data quality signal, not just a warning to dismiss.

---

## Source Data Provenance

- **Source:** US SEC EDGAR (Electronic Data Gathering, Analysis, and Retrieval)
- **Extraction tool:** `edgartools` Python library (v5.x)
- **Filings:** 10-K and 10-Q for the 6 largest US banks (JPM, BAC, WFC, C, GS, MS)
- **Date range:** 2018–2025 (5+ years of statements)
- **Total filings ingested:** 393 of 402 attempted (97.7% success rate)
- **Failed filings:** 3 (2 amended filings with non-standard schemas, 1 EDGAR timeout)
- **Star schema output:** 19,910 fact rows × 443 unique concepts × 6 banks × 4,017 dates
