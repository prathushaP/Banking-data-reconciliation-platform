# Banking Data Reconciliation Platform

**Author:** Prathusha Pasam

Detects missing, duplicate, and mismatched banking records using **SQL + Python**, with automated validation rules, match-quality scoring, and an interactive Streamlit exception workbench.

## Live demo

> After deploy, replace this line with your Streamlit Cloud URL  
> Example: `https://banking-reconciliation-prathusha.streamlit.app`

## Features

- Rich synthetic **accounts + internal core ledger + external settlement feed**
- SQL validation rules for:
  - Missing in external / internal
  - Amount, fee, date, and status mismatches
  - Duplicate business-key groups
  - High-value breaks
- Match quality scoring (0–100) on overlapping transactions
- Account exposure ranking, channel/region analytics, daily break trends
- Exception workbench with workflow status + priority score
- Filters, drill-downs, and CSV exports

## Data note

Synthetic data is modeled on common public banking/transaction schemas such as:

- PKDD'99 Financial dataset style entities (accounts, transactions, branch/region)
- Kaggle-style bank transaction fields (amount, merchant, channel, category, status)

No real customer data is used.

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
├── app.py
├── requirements.txt
├── src/
│   ├── generate_data.py
│   └── reconcile.py
└── data/
    ├── accounts.csv
    ├── internal_ledger.csv
    ├── external_ledger.csv
    └── banking.db
```

## Deploy free on Streamlit Community Cloud

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. **New app** → select this repo.
4. Main file path: `app.py`
5. Deploy → copy the live URL into your portfolio.

The app auto-generates data on first run if `data/banking.db` is missing. Use **Regenerate synthetic data** in the sidebar anytime.

## Validation rules

| ID | Rule | Severity |
|----|------|----------|
| R1 | Missing in External | High |
| R2 | Missing in Internal | High |
| R3 | Amount Mismatch | Critical |
| R4 | Date Mismatch | Medium |
| R5 | Status Mismatch | Medium |
| R6 | Fee Mismatch | Medium |
| R7 | Internal Duplicates | Medium |
| R8 | External Duplicates | Medium |
| R9 | High Value Breaks | Critical |

## License

MIT · Built for portfolio use by Prathusha Pasam
