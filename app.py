"""Banking Data Reconciliation Platform
Interactive Streamlit dashboard.
Author: Prathusha Pasam
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from generate_data import main as generate_data  # noqa: E402
from reconcile import RULES, load_ledgers, run_reconciliation  # noqa: E402

DB_PATH = ROOT / "data" / "banking.db"

st.set_page_config(
    page_title="Banking Reconciliation | Prathusha Pasam",
    page_icon="🏦",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.2rem;}
    div[data-testid="stMetric"] {
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def ensure_data() -> None:
    if not DB_PATH.exists():
        generate_data()


@st.cache_data(show_spinner=False)
def get_results():
    ensure_data()
    return run_reconciliation(DB_PATH)


def main() -> None:
    st.title("🏦 Banking Data Reconciliation Platform")
    st.caption("Built by **Prathusha Pasam** · SQL + Python validation · Portfolio project")

    result = get_results()
    internal, external = load_ledgers(DB_PATH)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Internal records", f"{result.kpis['internal_records']:,}")
    c2.metric("External records", f"{result.kpis['external_records']:,}")
    c3.metric("Clean matches", f"{result.kpis['matched_clean']:,}")
    c4.metric("Total issues", f"{result.kpis['total_issues']:,}")
    c5.metric("Match rate", f"{result.kpis['match_rate_pct']}%")

    tab_overview, tab_rules, tab_explore, tab_about = st.tabs(
        ["Overview", "Validation Rules", "Explore Data", "About"]
    )

    with tab_overview:
        left, right = st.columns([1.1, 1])
        with left:
            st.subheader("Issues by rule")
            fig = px.bar(
                result.summary,
                x="rule_name",
                y="issue_count",
                color="severity",
                color_discrete_map={
                    "Critical": "#ef4444",
                    "High": "#f97316",
                    "Medium": "#eab308",
                },
                text="issue_count",
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title="Issues",
                showlegend=True,
                margin=dict(l=10, r=10, t=10, b=10),
                height=380,
            )
            st.plotly_chart(fig, use_container_width=True)

        with right:
            st.subheader("Severity mix")
            sev = (
                result.summary.groupby("severity", as_index=False)["issue_count"].sum()
            )
            fig2 = px.pie(sev, names="severity", values="issue_count", hole=0.45)
            fig2.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=380)
            st.plotly_chart(fig2, use_container_width=True)

        st.subheader("Reconciliation summary")
        st.dataframe(result.summary, use_container_width=True, hide_index=True)

    with tab_rules:
        rule_labels = {f"{r['id']} · {r['name']}": r["id"] for r in RULES}
        choice = st.selectbox("Select validation rule", list(rule_labels.keys()))
        rid = rule_labels[choice]
        meta = next(r for r in RULES if r["id"] == rid)
        st.info(f"**{meta['severity']}** — {meta['description']}")
        df = result.details[rid]
        st.write(f"{len(df):,} issue row(s)")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download rule findings (CSV)",
            df.to_csv(index=False).encode("utf-8"),
            file_name=f"{rid.lower()}_findings.csv",
            mime="text/csv",
        )

    with tab_explore:
        src = st.radio("Ledger", ["Internal", "External"], horizontal=True)
        df = internal if src == "Internal" else external
        f1, f2, f3 = st.columns(3)
        accounts = ["All"] + sorted(df["account_id"].unique().tolist())
        channels = ["All"] + sorted(df["channel"].unique().tolist())
        types = ["All"] + sorted(df["txn_type"].unique().tolist())
        acc = f1.selectbox("Account", accounts)
        ch = f2.selectbox("Channel", channels)
        tp = f3.selectbox("Type", types)
        view = df.copy()
        if acc != "All":
            view = view[view["account_id"] == acc]
        if ch != "All":
            view = view[view["channel"] == ch]
        if tp != "All":
            view = view[view["txn_type"] == tp]
        st.dataframe(view, use_container_width=True, hide_index=True)
        daily = (
            view.assign(txn_date=pd.to_datetime(view["txn_date"]))
            .groupby("txn_date", as_index=False)["amount"]
            .sum()
        )
        fig3 = px.line(daily, x="txn_date", y="amount", title="Daily transaction volume")
        st.plotly_chart(fig3, use_container_width=True)

    with tab_about:
        st.markdown(
            """
            ### Project
            Portfolio demo that reconciles an **internal bank ledger** against an
            **external settlement feed**.

            ### What it detects
            - Missing records (either side)
            - Duplicate business-key groups
            - Amount mismatches on shared transaction IDs

            ### Tech stack
            - **Python** + **pandas** for data generation and orchestration
            - **SQLite / SQL views** for deterministic validation rules
            - **Streamlit + Plotly** for the interactive dashboard

            ### Data note
            Synthetic data modeled on common public banking/transaction CSV schemas
            (account id, date, amount, type, channel). No real customer data is used.

            ### Author
            **Prathusha Pasam**
            """
        )

    st.markdown("---")
    st.caption("© Prathusha Pasam · Banking Data Reconciliation Platform")


if __name__ == "__main__":
    main()
