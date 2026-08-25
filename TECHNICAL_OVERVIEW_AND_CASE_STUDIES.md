# Banking Data Reconciliation Platform
## Technical Overview & Case Studies

**Author:** Prathusha Pasam  
**Project type:** Portfolio data engineering / analytics application  
**Stack:** Python · pandas · SQLite · Streamlit · Plotly  
**Scope:** Detect missing, duplicate, and mismatched banking records between a core banking ledger and an external settlement feed

---

# 1. Technical Overview

## 1.1 Problem statement

Banks and fintech operations teams routinely compare an **internal core ledger** with an **external settlement / processor feed**. Breaks appear when:

- a transaction posts in one system but not the other
- amounts, fees, value dates, or statuses diverge
- duplicate operational re-posts inflate balances
- high-value items are delayed or silently dropped

Manual spreadsheet checks do not scale. This project demonstrates an automated, explainable reconciliation pipeline with SQL validation rules, Python analytics, and an interactive dashboard for exception investigation.

## 1.2 Solution summary

The platform:

1. Generates realistic synthetic banking data modeled on public dataset schemas
2. Loads accounts + dual ledgers into SQLite
3. Runs deterministic SQL views for each validation rule
4. Scores pairwise match quality in Python
5. Builds an exception workbench with priority and workflow status
6. Surfaces KPIs, trends, and drill-downs in Streamlit

```text
[Synthetic Generator]
        |
        v
 accounts.csv
 internal_ledger.csv  ----->  SQLite (banking.db)
 external_ledger.csv            |
                                | SQL views (R1-R9)
                                v
                     Reconciliation Engine (Python)
                                |
                +---------------+----------------+
                |               |                |
           KPIs / Exposure  Match Quality   Exception Queue
                |               |                |
                +---------------+----------------+
                                |
                                v
                     Streamlit Dashboard (Plotly)
```

## 1.3 Data design

Synthetic data is intentionally aligned with common public banking schemas:

| Public pattern | Project fields |
|----------------|----------------|
| PKDD'99-style accounts / districts | `account_id`, branch, city, state, region, product, risk segment |
| Kaggle-style bank transactions | amount, merchant, channel, category, status, currency |
| Core vs settlement ops | booking_date, value_date, fee_amount, reference, counterparty, source_system |

### Entities

**accounts** (~80 rows)
- Customer/account master with branch geography and product type

**internal_ledger** (~4,545 rows)
- Core banking postings (`source_system = CORE_BANKING`)

**external_ledger** (~4,495 rows)
- Settlement/processor feed (`source_system = SETTLEMENT_FEED`)

### Controlled break injection

To make the demo realistic, the generator injects known issue classes:

- missing on external side
- missing on internal side (settlement residuals)
- principal amount mismatches
- value-date drift
- lifecycle status mismatches
- fee mismatches (wire/ATM style)
- duplicate re-posts on either ledger

## 1.4 Architecture components

| Component | File | Responsibility |
|-----------|------|----------------|
| Data generator | `src/generate_data.py` | Create accounts/ledgers, inject breaks, create SQL views |
| Rule engine | `src/reconcile.py` | Execute rules, KPIs, exposure, match score, exception queue |
| Dashboard | `app.py` | Interactive UI for ops-style investigation |
| Persistence | `data/banking.db` + CSVs | Portable local dataset for portfolio demos |

## 1.5 Validation rule catalog

| ID | Rule | Severity | Detection logic |
|----|------|----------|-----------------|
| R1 | Missing in External | High | Internal `txn_id` not in settlement feed |
| R2 | Missing in Internal | High | External residual with no core match |
| R3 | Amount Mismatch | Critical | Same `txn_id`, different principal amount |
| R4 | Date Mismatch | Medium | `value_date` differs across systems |
| R5 | Status Mismatch | Medium | Lifecycle status differs (POSTED/PENDING/SETTLED/REVERSED) |
| R6 | Fee Mismatch | Medium | Fee amounts differ |
| R7 | Internal Duplicates | Medium | Duplicate business-key groups in core |
| R8 | External Duplicates | Medium | Duplicate business-key groups in feed |
| R9 | High Value Breaks | Critical | Large amount breaks or high-value missing items |

Rules are implemented as **SQL views** for transparency and auditability. Python orchestrates execution, scoring, and presentation.

## 1.6 Match quality model

For overlapping `txn_id` pairs, a 0–100 score is computed:

| Check | Points |
|-------|--------|
| Amount equal | 40 |
| Value date equal | 20 |
| Status equal | 20 |
| Fee equal | 20 |
| **Perfect match** | **100** |

Bands:

- Perfect: 100
- Good: 80–99
- Fair: 60–79
- Poor: < 60

## 1.7 Exception workbench design

Each non-aggregate finding is enriched with:

- `workflow_status`: Open / Investigating / Resolved
- `age_days`: aging relative to booking date
- `priority_score`: severity weight × age (+ amount/exposure factor)

This mirrors how ops teams triage breaks: high severity + older + larger exposure first.

## 1.8 Dashboard capabilities

1. **Overview** — KPIs, rule volume, severity mix, channel/region heat, daily trend, top account exposure  
2. **Validation Rules** — drill into any rule and export CSV  
3. **Exception Workbench** — filter by severity, workflow, channel, region; sort by priority  
4. **Match Quality** — score distribution and imperfect pairs  
5. **Explore Data** — browse accounts/ledgers with filters and charts  
6. **About** — project narrative for portfolio reviewers

## 1.9 Baseline run metrics (current synthetic snapshot)

| KPI | Value |
|-----|------:|
| Accounts | 80 |
| Internal transactions | 4,545 |
| External transactions | 4,495 |
| Clean matches | 4,130 |
| Match rate | 90.87% |
| Total rule findings | 670 |
| Amount mismatch exposure | $1,841.89 |
| Missing-side exposure | $137,087.55 |
| Total exposure | $138,929.44 |
| Open exceptions | 417 |
| Average match score | 98.4 / 100 |

### Findings by rule (baseline)

| Rule | Issues |
|------|-------:|
| Missing in External | 165 |
| Missing in Internal | 115 |
| Amount Mismatch | 90 |
| Date Mismatch | 70 |
| Status Mismatch | 52 |
| Fee Mismatch | 40 |
| Internal Duplicates | 45 |
| External Duplicates | 35 |
| High Value Breaks | 58 |

### Channel concentration (selected break types)

| Channel | Issues | Amount sum (break metric) |
|---------|-------:|--------------------------:|
| CARD | 126 | $6,265.23 |
| ACH | 74 | $21,141.67 |
| ONLINE | 49 | $9,630.12 |
| MOBILE | 35 | $10,847.94 |
| ATM | 32 | $1,884.95 |
| CHECK | 29 | $6,284.99 |
| WIRE | 25 | $82,874.54 |

Insight: **CARD produces the most break count**, while **WIRE concentrates the largest dollar exposure**.

## 1.10 Engineering choices & trade-offs

| Choice | Why |
|--------|-----|
| SQLite + SQL views | Easy portfolio deploy, transparent rule logic, no cloud DB required |
| Synthetic but schema-realistic data | Avoids PII while remaining interview-defensible |
| Streamlit | Fast interactive UI + free hosting path |
| Deterministic seed (42) | Reproducible demos and screenshots |
| Rule-based (not ML-first) | Explainability preferred for reconciliation controls |

## 1.11 How to run

```bash
pip install -r requirements.txt
python src/generate_data.py
streamlit run app.py
```

Optional: use the sidebar **Regenerate synthetic data** button to rebuild the dataset in-app.

## 1.12 Portfolio positioning

This project demonstrates:

- data modeling for dual-ledger finance systems
- SQL-based data quality / control design
- analytical KPI design for operations
- product thinking via exception workflow UX
- end-to-end delivery (data → rules → dashboard)

---

# 2. Case Study 1 — High-Value Wire Break Concentration

## 2.1 Business context

Treasury and payments operations care less about raw break counts and more about **dollar exposure**. A small number of wire breaks can dominate risk even when card breaks are more frequent.

## 2.2 Objective

Identify whether wire activity creates disproportionate financial exposure and what action an ops lead should take first.

## 2.3 Approach

1. Run full reconciliation rule set (R1–R9)
2. Aggregate breaks by channel (missing + amount mismatch views)
3. Rank accounts by exposure amount
4. Inspect high-value break rule (R9) and amount mismatches (R3)
5. Prioritize open exceptions with high priority score

## 2.4 Evidence from the platform

### Channel pattern
- CARD leads **issue count** (126)
- WIRE is lower count (25) but leads **amount concentration** (~$82.9k in the channel break metric)

### Top account exposure (examples)
| Account | Breaks | Exposure | Region | Product | Risk |
|---------|-------:|---------:|--------|---------|------|
| ACC10004 | 6 | $17,922.74 | West | CREDIT_CARD | Medium |
| ACC10038 | 8 | $10,305.77 | South | CREDIT_CARD | Low |
| ACC10021 | 4 | $9,953.88 | West | CHECKING | Medium |

### Sample amount mismatch (R3)
| txn_id | account | channel | internal | external | abs_diff |
|--------|---------|---------|---------:|---------:|---------:|
| TXN000196 | ACC10076 | WIRE | 3,085.56 | 3,051.59 | 33.97 |
| TXN000199 | ACC10062 | ONLINE | 352.31 | 323.67 | 28.64 |

These flow into **R9 High Value Breaks** when thresholds are met (amount diff ≥ $25 or missing item ≥ $1,000).

## 2.5 Findings

1. **Count ≠ risk.** Card rails create many small operational noise items; wires create fewer but higher-value breaks.
2. Exposure is account-concentrated: a handful of accounts explain a large share of total exposure.
3. Multi-currency rows (GBP/EUR samples) show realistic FX/settlement drift patterns that pure single-currency demos miss.
4. Total platform exposure in the baseline snapshot is about **$138.9k**, mostly from missing-side residuals.

## 2.6 Recommended actions

| Priority | Action | Owner |
|----------|--------|-------|
| P1 | Queue all Open R9 + WIRE breaks first | Payments Ops |
| P2 | Investigate top 10 accounts by exposure | Reconciliation Lead |
| P3 | Add wire-specific SLA: value-date tolerance 0 days, amount tolerance $0.00 | Controls |
| P4 | Separate FX conversion residuals into a dedicated rule in a future iteration | Data Engineering |

## 2.7 Outcome (demo narrative)

Using the workbench filters (`severity=Critical/High`, `channel=WIRE`, `workflow=Open`), an analyst can reduce a 670-finding haystack into a focused high-risk queue in seconds, export CSV evidence, and hand off to settlement partners.

### Skills demonstrated
- Dual-ledger join logic
- Exposure analytics
- Severity-based triage design
- Channel risk storytelling for stakeholders

---

# 3. Case Study 2 — Lifecycle & Timing Breaks (Date + Status Drift)

## 3.1 Business context

Not all breaks are monetary. Many customer and GL issues come from **timing and lifecycle mismatches**:

- core shows POSTED while settlement still PENDING
- value date lags booking date differently across systems
- reversed items remain active on one side

These create false suspense balances and delayed customer notifications.

## 3.2 Objective

Quantify non-amount breaks, measure match-quality degradation, and propose operational tolerances.

## 3.3 Approach

1. Execute R4 (date mismatch) and R5 (status mismatch)
2. Score all overlapping pairs with the match-quality model
3. Compare Perfect vs imperfect bands
4. Review daily break trend to see whether timing issues cluster on certain days
5. Prioritize aged open exceptions

## 3.4 Evidence from the platform

### Timing / lifecycle rule volumes
| Rule | Issues |
|------|-------:|
| Date Mismatch (R4) | 70 |
| Status Mismatch (R5) | 52 |
| Fee Mismatch (R6) | 40 |

### Match quality distribution (overlapping txn_ids)
| Band | Count |
|------|------:|
| Perfect | 4,130 |
| Good | 160 |
| Fair | 88 |
| Poor | 2 |
| **Average score** | **98.4** |

Interpretation: most overlapping transactions reconcile cleanly, but ~250 pairs are imperfect. Those imperfect pairs are exactly where date/status/fee/amount rules fire.

### Clean-match definition used by the platform
A pair is “clean” only if **all** are true:
- amount equal
- value_date equal
- status equal
- fee equal

This is stricter than amount-only matching and better reflects production control standards.

## 3.5 Findings

1. **90.87% match rate** still leaves meaningful operational work: 670 total findings and 417 open exceptions.
2. Date and status drift are material secondary break classes (122 combined issues), not edge noise.
3. A high average match score (98.4) can coexist with material residual exposure if missing-side items are large.
4. Aging + severity scoring surfaces stale pending/reversed mismatches before they age into audit findings.

## 3.6 Recommended actions

| Priority | Action | Rationale |
|----------|--------|-----------|
| P1 | Define explicit value-date tolerance by rail (e.g., ACH +1 day allowed, WIRE 0 day) | Removes false positives |
| P2 | Auto-close status pairs `POSTED` vs `SETTLED` after T+1 if amount/date match | Reduces queue bloat |
| P3 | Keep REVERSED mismatches as Critical regardless of amount | Prevents silent un-winds |
| P4 | Monitor daily trend chart for spikes after batch windows | Detect feed delays early |

## 3.7 Outcome (demo narrative)

On the **Match Quality** tab, analysts inspect imperfect pairs and export evidence. On the **Exception Workbench**, filters for Medium severity + Investigating/Open isolate timing breaks from monetary criticals, enabling parallel workstreams:

- Team A: amount/missing (Case Study 1)
- Team B: date/status lifecycle (Case Study 2)

### Skills demonstrated
- Multi-condition match scoring
- Data quality rule design beyond amount equality
- Workflow separation for ops teams
- KPI design (match rate + score + open exceptions)

---

# 4. Cross-case synthesis

| Dimension | Case Study 1 | Case Study 2 |
|-----------|--------------|--------------|
| Primary risk | Dollar exposure | Process/timing integrity |
| Key rules | R1, R2, R3, R9 | R4, R5, R6 + match score |
| Main lens | Channel + account exposure | Match bands + aging |
| Business user | Treasury / Payments Ops | Ops Control / Customer Support ops |
| Dashboard home | Overview + Workbench | Match Quality + Workbench |

Together, the two cases show the platform is not only a break counter — it supports **risk-based prioritization** and **process-quality monitoring**.

---

# 5. Limitations & future enhancements

Current limitations (intentional for portfolio scope):

- Synthetic data (no production connectivity)
- Workflow status is simulated, not a persistent ticket system
- Tolerances are fixed thresholds, not rail-specific configs
- No user authentication / audit log UI

Strong next iterations:

1. Configurable tolerance matrix by channel/currency
2. Fuzzy matching on reference/counterparty when `txn_id` is absent
3. Writer API to mark exceptions resolved with notes
4. dbt models instead of inline SQL views for warehouse-style portfolios
5. Alerting (email/Slack) when daily critical exposure exceeds threshold

---

# 6. Conclusion

The Banking Data Reconciliation Platform provides an end-to-end, portfolio-ready demonstration of financial data controls:

- realistic dual-ledger data model
- transparent SQL validation rules
- quantitative exposure and match-quality analytics
- interactive exception management UX

The two case studies prove complementary value:

1. **Find the money risk fast** (wire/high-value concentration)
2. **Keep process integrity clean** (date/status lifecycle quality)

**Author:** Prathusha Pasam

---

*Document generated for portfolio use with the project baseline synthetic run.*
