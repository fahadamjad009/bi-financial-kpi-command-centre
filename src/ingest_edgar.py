"""
src/ingest_edgar.py

Fetch SEC EDGAR 10-K and 10-Q filings for the bank universe and save raw
financial statements (income, balance sheet, cash flow) as parquet files.

Each filing becomes 3 parquet files (one per statement type), kept in WIDE
format with the period-named columns edgartools returns. The wide -> long
melt happens in src/transform.py.

Output:
    data/raw/edgar/
        JPM/
            10-Q_2026-05-01_0001628280-26-029344_income.parquet
            10-Q_2026-05-01_0001628280-26-029344_balance.parquet
            10-Q_2026-05-01_0001628280-26-029344_cashflow.parquet
            ...

Usage:
    # Smoke test: one ticker, two most recent filings per form
    python src/ingest_edgar.py --tickers JPM --limit 2

    # Full run: all 6 banks, all filings since FILING_START_DATE
    python src/ingest_edgar.py
"""
import argparse
import sys
from pathlib import Path

# Add project root to path so "from src.config import ..." works when running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from edgar import Company, set_identity
from src.config import (
    EDGAR_IDENTITY,
    TICKERS,
    FILING_FORMS,
    FILING_START_DATE,
    RAW_DIR,
)

STATEMENTS = [
    ("income", "income_statement"),
    ("balance", "balance_sheet"),
    ("cashflow", "cashflow_statement"),
]


def ingest_company(ticker: str, limit: int | None = None) -> int:
    """Fetch all filings for one ticker and save as parquet. Returns count saved."""
    company = Company(ticker)
    print(f"\n[{ticker}] {company.name} (CIK: {company.cik})")

    out_dir = RAW_DIR / ticker
    out_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    for form in FILING_FORMS:
        filings = company.get_filings(form=form, filing_date=f"{FILING_START_DATE}:")
        if limit:
            filings = filings.head(limit)
        print(f"  {form}: {len(filings)} filings in scope")

        for filing in filings:
            try:
                xbrl = filing.xbrl()
                if xbrl is None:
                    print(f"    skip (no XBRL): {filing.filing_date} {filing.accession_no}")
                    continue

                stem = f"{form}_{filing.filing_date}_{filing.accession_no}"

                for stmt_name, stmt_method in STATEMENTS:
                    try:
                        stmt_obj = getattr(xbrl.statements, stmt_method)()
                        df = stmt_obj.to_dataframe(view="standard")

                        # Annotate with provenance â€” useful in transform step
                        df["ticker"] = ticker
                        df["form"] = form
                        df["filing_date"] = str(filing.filing_date)
                        df["accession_no"] = filing.accession_no
                        df["statement"] = stmt_name

                        # Cast all object columns to string to avoid pyarrow mixed-type errors
                        for col in df.select_dtypes(include=["object", "string"]).columns:
                            df[col] = df[col].astype(str)

                        out_path = out_dir / f"{stem}_{stmt_name}.parquet"
                        df.to_parquet(out_path, engine="pyarrow", index=False)
                        saved += 1
                    except Exception as e:
                        print(f"    error on {stmt_name}: {type(e).__name__}: {e}")

            except Exception as e:
                print(f"    error on filing {filing.accession_no}: {type(e).__name__}: {e}")

    return saved


def main():
    parser = argparse.ArgumentParser(description="Ingest SEC EDGAR filings")
    parser.add_argument(
        "--tickers", nargs="+", default=TICKERS, help=f"Tickers to ingest (default: {TICKERS})"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit filings per form (default: all)"
    )
    args = parser.parse_args()

    set_identity(EDGAR_IDENTITY)
    print(f"Ingesting tickers={args.tickers}, forms={FILING_FORMS}, limit={args.limit}")
    print(f"Output: {RAW_DIR}")

    total = 0
    for ticker in args.tickers:
        count = ingest_company(ticker, limit=args.limit)
        print(f"[{ticker}] saved {count} parquet files")
        total += count

    print(f"\n=== Ingestion complete: {total} parquet files saved ===")


if __name__ == "__main__":
    main()

