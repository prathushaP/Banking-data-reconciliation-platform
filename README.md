# Banking Data Reconciliation Platform

**Author:** Prathusha Pasam

Detects missing, duplicate, and mismatched banking records using **SQL + Python**, with automated validation rules and an interactive Streamlit dashboard.

## Live demo

> After deploy, replace this line with your Streamlit Cloud URL  
> Example: `https://banking-reconciliation-prathusha.streamlit.app`

## Features

- Synthetic internal vs external ledgers (realistic banking schema)
- SQL validation rules for:
  - Missing in external / internal
  - Amount mismatches
  - Duplicate groups
- KPI cards, charts, rule drill-down, filters, CSV export

## Tech stack

- Python, pandas, SQLite
- Streamlit, Plotly

## Quick start (local)

```bash
pip install -r requirements.txt
python src/generate_data.py
streamlit run app.py
```

## Project structure

```text
banking-reconciliation/
├── app.py                 # Streamlit dashboard
├── requirements.txt
├── src/
│   ├── generate_data.py   # Synthetic dataset + SQLite views
│   └── reconcile.py       # Rule engine
└── data/                  # Generated CSVs + banking.db
```

## Deploy free on Streamlit Community Cloud

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. **New app** → select this repo.
4. Main file path: `app.py`
5. Deploy → copy the live URL into your portfolio.

The app auto-generates data on first run if `data/banking.db` is missing.

## Validation rules

| ID | Rule | Severity |
|----|------|----------|
| R1 | Missing in External | High |
| R2 | Missing in Internal | High |
| R3 | Amount Mismatch | Critical |
| R4 | Internal Duplicates | Medium |
| R5 | External Duplicates | Medium |

## License

MIT · Built for portfolio use by Prathusha Pasam
