"""
src/transform.py

Transform raw SEC EDGAR parquets (wide format, one file per filing x statement)
into a Power BI-ready star schema in long format.

Reads:  data/raw/edgar/<ticker>/<form>_<filing_date>_<accession>_<stmt>.parquet
Writes: data/processed/fact_financials.parquet
        data/processed/dim_company.parquet
        data/processed/dim_concept.parquet
        data/processed/dim_date.parquet

Dedup strategy: when the same (ticker, concept, period_end_date) appears in
multiple filings (e.g. Q3 reported in Q3 10-Q AND restated in 10-K), keep
the most recently filed value (latest filing_date wins).

Usage:
    python src/transform.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import re
import glob
import pandas as pd
from src.config import RAW_DIR, PROCESSED_DIR

# Period column name patterns
PERIOD_SUFFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*\(([^)]+)\)$")  # "2024-12-31 (FY)"
BARE_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})$")  # "2020-12-31"

META_COLS = {
    "concept", "label", "standard_concept", "level", "abstract", "dimension",
    "is_breakdown", "dimension_axis", "dimension_member", "dimension_member_label",
    "dimension_label", "balance", "weight", "preferred_sign", "parent_concept",
    "parent_abstract_concept", "ticker", "form", "filing_date", "accession_no",
    "statement",
}

# Company metadata (hardcoded — portfolio scope is fixed at 6 US large-cap banks)
COMPANY_META = {
    "JPM": ("JPMorgan Chase & Co", "Diversified Banks"),
    "BAC": ("Bank of America Corp", "Diversified Banks"),
    "WFC": ("Wells Fargo & Company", "Diversified Banks"),
    "C":   ("Citigroup Inc", "Diversified Banks"),
    "GS":  ("Goldman Sachs Group Inc", "Capital Markets"),
    "MS":  ("Morgan Stanley", "Capital Markets"),
}


def parse_period_col(col_name):
    """Return (period_end_date, period_type) or None if not a period column."""
    s = str(col_name).strip()
    m = PERIOD_SUFFIX.match(s)
    if m:
        return m.group(1), m.group(2)
    m = BARE_DATE.match(s)
    if m:
        return m.group(1), "POINT_IN_TIME"
    return None


def melt_filing(df):
    """Wide -> long for one filing's statement dataframe. Returns empty df if no period cols."""
    period_cols = []
    for c in df.columns:
        if c in META_COLS:
            continue
        parsed = parse_period_col(c)
        if parsed:
            period_cols.append((c, parsed[0], parsed[1]))

    if not period_cols:
        return pd.DataFrame()

    period_col_names = [pc[0] for pc in period_cols]
    period_meta = {pc[0]: (pc[1], pc[2]) for pc in period_cols}
    id_cols = [c for c in df.columns if c not in period_col_names]

    melted = df.melt(
        id_vars=id_cols,
        value_vars=period_col_names,
        var_name="period_col",
        value_name="value",
    )

    melted["period_end_date"] = melted["period_col"].map(lambda c: period_meta[c][0])
    melted["period_type"] = melted["period_col"].map(lambda c: period_meta[c][1])
    melted = melted.drop(columns=["period_col"])

    # Drop NaN values (header/abstract rows have NaN in period columns)
    melted = melted[melted["value"].notna()]

    # Type coercion
    melted["value"] = pd.to_numeric(melted["value"], errors="coerce")
    melted = melted[melted["value"].notna()]
    melted["period_end_date"] = pd.to_datetime(melted["period_end_date"])
    melted["filing_date"] = pd.to_datetime(melted["filing_date"])

    return melted


def build_fact():
    """Read all raw parquets, melt, dedupe across overlapping filings."""
    files = sorted(glob.glob(str(RAW_DIR / "*" / "*.parquet")))
    print(f"  Reading {len(files)} raw parquets")

    long_dfs = []
    skipped = 0
    for f in files:
        try:
            df = pd.read_parquet(f)
            melted = melt_filing(df)
            if not melted.empty:
                long_dfs.append(melted)
            else:
                skipped += 1
        except Exception as e:
            print(f"    ERROR melting {f}: {type(e).__name__}: {e}")
            skipped += 1

    fact = pd.concat(long_dfs, ignore_index=True)
    print(f"  Skipped (no period cols / errors): {skipped}")
    print(f"  Pre-dedupe rows: {len(fact):,}")

    # Dedupe: latest filing wins for any (ticker, concept, period, type, statement) collision
    fact = (
        fact.sort_values("filing_date")
        .drop_duplicates(
            subset=["ticker", "concept", "period_end_date", "period_type", "statement"],
            keep="last",
        )
        .reset_index(drop=True)
    )
    print(f"  Post-dedupe rows: {len(fact):,}")
    return fact


def build_dim_company(fact):
    rows = []
    for ticker in sorted(fact["ticker"].unique()):
        name, industry = COMPANY_META.get(ticker, (ticker, "Unknown"))
        rows.append({"ticker": ticker, "company_name": name,
                     "sector": "Financials", "industry": industry})
    return pd.DataFrame(rows)


def build_dim_concept(fact):
    cols = ["concept", "label", "standard_concept", "statement",
            "parent_concept", "level", "balance", "weight"]
    dim = (
        fact[cols]
        .drop_duplicates(subset=["concept", "statement", "label"])
        .reset_index(drop=True)
    )
    return dim


def build_dim_date(fact):
    """Full calendar covering all period_end_dates, +/-1 year padding for time intel."""
    min_d = fact["period_end_date"].min()
    max_d = fact["period_end_date"].max()
    min_d = pd.Timestamp(min_d.year - 1, 1, 1)
    max_d = pd.Timestamp(max_d.year + 1, 12, 31)

    dates = pd.date_range(min_d, max_d, freq="D")
    dim = pd.DataFrame({"date": dates})
    dim["date_id"] = dim["date"].dt.strftime("%Y%m%d").astype(int)
    dim["year"] = dim["date"].dt.year
    dim["quarter"] = dim["date"].dt.quarter
    dim["quarter_label"] = "Q" + dim["quarter"].astype(str) + " " + dim["year"].astype(str)
    dim["month"] = dim["date"].dt.month
    dim["month_name"] = dim["date"].dt.month_name()
    dim["month_short"] = dim["date"].dt.strftime("%b")
    dim["day"] = dim["date"].dt.day
    dim["day_of_week"] = dim["date"].dt.day_name()
    dim["is_month_end"] = dim["date"].dt.is_month_end
    dim["is_quarter_end"] = dim["date"].dt.is_quarter_end
    dim["is_year_end"] = dim["date"].dt.is_year_end
    # US banks use calendar year as fiscal year
    dim["fiscal_year"] = dim["year"]
    dim["fiscal_quarter"] = dim["quarter"]
    return dim


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Building fact_financials")
    print("=" * 60)
    fact = build_fact()
    p = PROCESSED_DIR / "fact_financials.parquet"
    fact.to_parquet(p, engine="pyarrow", index=False)
    print(f"  -> {p.name}  ({len(fact):,} rows, {p.stat().st_size / 1024:.1f} KB)")

    print()
    print("=" * 60)
    print("Building dimensions")
    print("=" * 60)
    for name, builder in [
        ("dim_company",  lambda: build_dim_company(fact)),
        ("dim_concept",  lambda: build_dim_concept(fact)),
        ("dim_date",     lambda: build_dim_date(fact)),
    ]:
        dim = builder()
        p = PROCESSED_DIR / f"{name}.parquet"
        dim.to_parquet(p, engine="pyarrow", index=False)
        print(f"  -> {p.name}  ({len(dim):,} rows, {p.stat().st_size / 1024:.1f} KB)")

    print()
    print("=" * 60)
    print("Star schema complete")
    print("=" * 60)
    print(f"Output: {PROCESSED_DIR}")
    for p in sorted(PROCESSED_DIR.glob("*.parquet")):
        print(f"  {p.name:30s} {p.stat().st_size / 1024:7.1f} KB")


if __name__ == "__main__":
    main()
