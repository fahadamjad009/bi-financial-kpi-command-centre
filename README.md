# Financial KPI Command Centre

Executive-grade financial intelligence dashboard analysing US large-cap bank quarterly performance. Built on SEC EDGAR XBRL filings with Power BI, demonstrating star-schema data modelling, DAX time intelligence, variance analysis, and Python-automated data ingestion.

## Live Demo
*Phase 3 — Power BI Service publish planned.*

## Companies Covered
JPMorgan Chase (JPM), Bank of America (BAC), Wells Fargo (WFC), Citigroup (C), Goldman Sachs (GS), Morgan Stanley (MS) — 5 years quarterly, sourced from 10-K and 10-Q SEC filings.

## Architecture
SEC EDGAR XBRL  →  Python ETL (edgartools)  →  Parquet  →  Power BI Star Schema  →  DAX  →  Visuals

## Tech Stack
- **BI**: Power BI Desktop, DAX (time intelligence, ranking, iterators, variance)
- **Data**: Python 3.11, edgartools, pandas, pyarrow
- **Source**: SEC EDGAR REST API (free, unlimited, regulatory-grade)

## DAX Patterns Demonstrated
- Time intelligence (YoY, QoQ, YTD via SAMEPERIODLASTYEAR, DATESYTD, DATEADD)
- Ranking (RANKX, TOPN)
- Variance analysis (Budget vs Actual, Prior Period)
- Semi-additive measures (LASTNONBLANK for balance-sheet snapshots)
- Iterator functions (SUMX, AVERAGEX)
- Context transition (CALCULATE wrapping row context)

## Project Structure
.
├── data/
│   ├── raw/edgar/       # Raw XBRL filings (gitignored)
│   └── processed/       # Star-schema parquets (gitignored, re-derivable)
├── src/                 # Python ETL pipeline
├── pbi/                 # Power BI workbook (.pbix)
├── notebooks/           # Exploration / data profiling
├── tests/               # pytest data quality + transformation tests
└── docs/screenshots/    # Dashboard screenshots

## Setup
```powershell
D:\Python311\python.exe -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python src/ingest_edgar.py
```

## Status
- [x] Phase 1 — Project scaffold
- [ ] Phase 1 — SEC EDGAR data pipeline
- [ ] Phase 2 — Power BI star schema + DAX
- [ ] Phase 2 — Visuals + drill-throughs
- [ ] Phase 3 — README polish, screenshots, GitHub
- [ ] Phase 3 — Power BI Service publish

---

Built by Fahad Amjad — part of a portfolio of deployed analytics platforms. See also: customer-churn-ml-benchmark, asx-abs-early-warning, fintech-fraud-detection-platform, mining-operations-analytics-platform.
