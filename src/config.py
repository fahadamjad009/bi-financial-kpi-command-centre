"""Project constants for the SEC EDGAR ingestion pipeline."""
from pathlib import Path

# SEC EDGAR User-Agent identity (required for every API call)
EDGAR_IDENTITY = "Fahad Amjad fahadamjad_10@hotmail.com"

# Universe: US large-cap banks (GICS Financials / Diversified Banks + Capital Markets)
TICKERS = ["JPM", "BAC", "WFC", "C", "GS", "MS"]

# Filing forms: 10-Q quarterly, 10-K annual
FILING_FORMS = ["10-Q", "10-K"]

# Pull 5 years of history
FILING_START_DATE = "2021-01-01"

# Paths (resolve relative to project root, regardless of where script is run)
PROJECT_ROOT = Path(__file__).parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "edgar"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
