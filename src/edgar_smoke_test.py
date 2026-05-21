"""
src/edgar_smoke_test.py

Sanity-check the SEC EDGAR pipeline:
  1. Identify ourselves to SEC (User-Agent header required for every API call)
  2. Pull JPMorgan Chase most recent 10-Q filing
  3. Parse XBRL financials -> pandas DataFrames
  4. Print a summary so we know the pipeline works end-to-end

Run from project root with venv active:
    python src/edgar_smoke_test.py
"""
from edgar import Company, set_identity
import pandas as pd

# SEC EDGAR requires User-Agent identity per https://www.sec.gov/os/accessing-edgar-data
set_identity("Fahad Amjad fahadamjad_10@hotmail.com")

# ---------- 1. Resolve the company ----------
print("=" * 60)
print("Stage 1: Resolve company")
print("=" * 60)
jpm = Company("JPM")
print(f"  Name:          {jpm.name}")
print(f"  CIK:           {jpm.cik}")
print(f"  Industry:      {getattr(jpm, 'industry', 'n/a')}")
print(f"  FY end:        {getattr(jpm, 'fiscal_year_end', 'n/a')}")

# ---------- 2. Pull the most recent 10-Q ----------
print()
print("=" * 60)
print("Stage 2: Pull latest 10-Q")
print("=" * 60)
filings_10q = jpm.get_filings(form="10-Q")
print(f"  Total 10-Q filings on record: {len(filings_10q)}")

latest_10q = filings_10q.latest()
print(f"  Form:          {latest_10q.form}")
print(f"  Filing date:   {latest_10q.filing_date}")
print(f"  Period:        {getattr(latest_10q, 'period_of_report', 'n/a')}")
print(f"  Accession:     {latest_10q.accession_no}")

# ---------- 3. Parse XBRL financials ----------
print()
print("=" * 60)
print("Stage 3: Parse XBRL financial statements")
print("=" * 60)
xbrl = latest_10q.xbrl()

income = xbrl.statements.income_statement()
balance = xbrl.statements.balance_sheet()
cashflow = xbrl.statements.cashflow_statement()

income_df = income.to_dataframe(view="standard")
balance_df = balance.to_dataframe(view="standard")
cashflow_df = cashflow.to_dataframe(view="standard")

print(f"  Income statement rows:  {len(income_df)}")
print(f"  Balance sheet rows:     {len(balance_df)}")
print(f"  Cash flow rows:         {len(cashflow_df)}")
print(f"  Income statement cols:  {list(income_df.columns)}")

# ---------- 4. Preview ----------
print()
print("=" * 60)
print("Stage 4: Income statement preview")
print("=" * 60)
preview_cols = [c for c in ["label", "level", "value"] if c in income_df.columns]
if not preview_cols:
    preview_cols = list(income_df.columns)[:5]
print(income_df[preview_cols].head(15).to_string(index=False))

print()
print("--- Smoke test complete ---")
print("If you see real numbers above, the pipeline is wired correctly.")
print("Next: src/ingest_edgar.py for the full universe.")
