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
SEV_COLOR = {"Critical": "#ef4444", "High": "#f97316", "Medium": "#eab308", "Low": "#22c55e"}

st.set_page_config(
    page_title="Banking Reconciliation | Prathusha Pasam",
    page_icon="🏦",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1rem;}
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


def ensure_data(force: bool = False) -> None:
    if force or not DB_PATH.exists():
        generate_data()


@st.cache_data(show_spinner=False)
def get_results(_version: int = 2):
    ensure_data(force=False)
    return run_reconciliation(DB_PATH)


@st.cache_data(show_spinner=False)
def get_ledgers(_version: int = 2):
    ensure_data(force=False)
    return load_ledgers(DB_PATH)


def money(v: float) -> str:
    return f"${v:,.2f}"


def main() -> None:
    st.sidebar.title("Controls")
    st.sidebar.caption("Prathusha Pasam · Portfolio")
    if st.sidebar.button("Regenerate synthetic data"):
        st.cache_data.clear()
        ensure_data(force=True)
        st.sidebar.success("Data regenerated")
        st.rerun()

    result = get_results()
    accounts, internal, external = get_ledgers()

    severities = st.sidebar.multiselect(
        "Severity", ["Critical", "High", "Medium", "Low"],
        default=["Critical", "High", "Medium"],
    )
    statuses = st.sidebar.multiselect(
        "Workflow status", ["Open", "Investigating", "Resolved"],
        default=["Open", "Investigating"],
    )
    channels = ["All"] + sorted(internal["channel"].dropna().unique().tolist())
    channel = st.sidebar.selectbox("Channel filter", channels)
    regions = ["All"] + sorted(accounts["region"].dropna().unique().tolist())
    region = st.sidebar.selectbox("Region filter", regions)

    st.title("🏦 Banking Data Reconciliation Platform")
    st.caption(
        "Built by **Prathusha Pasam** · Core ledger vs settlement feed · SQL validation · Exception workbench"
    )

    k = result.kpis
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Accounts", f"{k['accounts']:,}")
    m2.metric("Internal txns", f"{k['internal_records']:,}")
    m3.metric("External txns", f"{k['external_records']:,}")
    m4.metric("Clean matches", f"{k['matched_clean']:,}")
    m5.metric("Match rate", f"{k['match_rate_pct']}%")
    m6.metric("Open exceptions", f"{k['open_exceptions']:,}")

    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Total issues", f"{k['total_issues']:,}")
    e2.metric("Amount exposure", money(k["amount_exposure"]))
    e3.metric("Missing exposure", money(k["missing_exposure"]))
    e4.metric("Avg match score", f"{k['avg_match_score']}/100")

    tab_overview, tab_rules, tab_workbench, tab_quality, tab_explore, tab_about = st.tabs(
        ["Overview", "Validation Rules", "Exception Workbench", "Match Quality", "Explore Data", "About"]
    )

    with tab_overview:
        c1, c2 = st.columns([1.2, 1])
        with c1:
            st.subheader("Issues by rule")
            fig = px.bar(
                result.summary, x="rule_name", y="issue_count", color="severity",
                color_discrete_map=SEV_COLOR, text="issue_count",
            )
            fig.update_layout(xaxis_title="", yaxis_title="Issues", height=390, margin=dict(t=20))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("Severity mix")
            sev = result.summary.groupby("severity", as_index=False)["issue_count"].sum()
            fig2 = px.pie(
                sev, names="severity", values="issue_count", hole=0.45,
                color="severity", color_discrete_map=SEV_COLOR,
            )
            fig2.update_layout(height=390, margin=dict(t=20))
            st.plotly_chart(fig2, use_container_width=True)

        c3, c4 = st.columns(2)
        with c3:
            st.subheader("Breaks by channel")
            fig3 = px.bar(result.channel_breaks, x="channel", y="issues", text="issues", color="amount_sum")
            fig3.update_layout(height=360, margin=dict(t=20))
            st.plotly_chart(fig3, use_container_width=True)
        with c4:
            st.subheader("Breaks by region")
            fig4 = px.bar(result.region_breaks, x="region", y="issues", text="issues", color="issues")
            fig4.update_layout(height=360, margin=dict(t=20))
            st.plotly_chart(fig4, use_container_width=True)

        st.subheader("Daily break trend")
        if not result.daily_trend.empty:
            trend = result.daily_trend.copy()
            trend["break_date"] = pd.to_datetime(trend["break_date"])
            fig5 = px.area(trend, x="break_date", y="issues", color="break_type")
            fig5.update_layout(height=360, margin=dict(t=20))
            st.plotly_chart(fig5, use_container_width=True)

        st.subheader("Top account exposure")
        st.dataframe(result.account_exposure.head(20), use_container_width=True, hide_index=True)
        st.subheader("Rule catalog summary")
        st.dataframe(result.summary, use_container_width=True, hide_index=True)

    with tab_rules:
        labels = {f"{r['id']} · {r['name']} ({r['severity']})": r["id"] for r in RULES}
        choice = st.selectbox("Select validation rule", list(labels.keys()))
        rid = labels[choice]
        meta = next(r for r in RULES if r["id"] == rid)
        st.info(f"**{meta['severity']}** — {meta['description']}")
        df = result.details[rid]
        st.write(f"{len(df):,} finding(s)")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download findings CSV", df.to_csv(index=False).encode("utf-8"),
            file_name=f"{rid.lower()}_findings.csv", mime="text/csv",
        )

    with tab_workbench:
        st.subheader("Exception queue")
        ex = result.exceptions.copy()
        if not ex.empty:
            if severities:
                ex = ex[ex["severity"].isin(severities)]
            if statuses:
                ex = ex[ex["workflow_status"].isin(statuses)]
            if channel != "All" and "channel" in ex.columns:
                ex = ex[ex["channel"] == channel]
            if region != "All" and "region" in ex.columns:
                ex = ex[ex["region"] == region]
            ex = ex.sort_values("priority_score", ascending=False)

            k1, k2, k3 = st.columns(3)
            k1.metric("Queued rows", f"{len(ex):,}")
            k2.metric("Open", f"{int((ex['workflow_status']=='Open').sum()):,}")
            k3.metric("Investigating", f"{int((ex['workflow_status']=='Investigating').sum()):,}")

            wc = ex.groupby("workflow_status", as_index=False).size()
            st.plotly_chart(px.pie(wc, names="workflow_status", values="size", hole=0.4), use_container_width=True)

            show_cols = [
                c for c in [
                    "priority_score", "rule_id", "severity", "workflow_status", "age_days",
                    "txn_id", "account_id", "customer_name", "booking_date", "channel", "region",
                    "amount", "abs_diff", "status", "description",
                ] if c in ex.columns
            ]
            st.dataframe(ex[show_cols].head(500), use_container_width=True, hide_index=True)
            st.download_button(
                "Download exception queue CSV", ex.to_csv(index=False).encode("utf-8"),
                file_name="exception_queue.csv", mime="text/csv",
            )
        else:
            st.success("No exceptions found.")

    with tab_quality:
        st.subheader("Pairwise match quality (overlapping txn_ids)")
        q = result.match_quality
        if q.empty:
            st.warning("No overlapping transactions.")
        else:
            band = q.groupby("match_band", as_index=False, observed=False).size()
            b1, b2 = st.columns(2)
            with b1:
                figq = px.histogram(q, x="match_score", nbins=20, color_discrete_sequence=["#38bdf8"])
                figq.update_layout(height=360, margin=dict(t=20), title="Match score distribution")
                st.plotly_chart(figq, use_container_width=True)
            with b2:
                figb = px.bar(band, x="match_band", y="size", text="size", color="match_band")
                figb.update_layout(height=360, margin=dict(t=20), title="Match bands")
                st.plotly_chart(figb, use_container_width=True)

            imperfect = q[q["match_score"] < 100].sort_values("match_score")
            st.write(f"Imperfect matches: {len(imperfect):,}")
            st.dataframe(imperfect.head(300), use_container_width=True, hide_index=True)
            st.download_button(
                "Download match quality CSV", q.to_csv(index=False).encode("utf-8"),
                file_name="match_quality.csv", mime="text/csv",
            )

    with tab_explore:
        src = st.radio("Dataset", ["Internal ledger", "External ledger", "Accounts"], horizontal=True)
        if src == "Accounts":
            df = accounts.copy()
        elif src == "Internal ledger":
            df = internal.copy()
        else:
            df = external.copy()

        f1, f2, f3, f4 = st.columns(4)
        if "account_id" in df.columns:
            accs = ["All"] + sorted(df["account_id"].astype(str).unique().tolist())
            acc = f1.selectbox("Account", accs, key="ex_acc")
            if acc != "All":
                df = df[df["account_id"] == acc]
        if "channel" in df.columns:
            chs = ["All"] + sorted(df["channel"].dropna().unique().tolist())
            ch = f2.selectbox("Channel", chs, key="ex_ch")
            if ch != "All":
                df = df[df["channel"] == ch]
        if "category" in df.columns:
            cats = ["All"] + sorted(df["category"].dropna().unique().tolist())
            cat = f3.selectbox("Category", cats, key="ex_cat")
            if cat != "All":
                df = df[df["category"] == cat]
        if "product_type" in df.columns:
            prods = ["All"] + sorted(df["product_type"].dropna().unique().tolist())
            prod = f4.selectbox("Product", prods, key="ex_prod")
            if prod != "All":
                df = df[df["product_type"] == prod]
        elif "txn_type" in df.columns:
            tps = ["All"] + sorted(df["txn_type"].dropna().unique().tolist())
            tp = f4.selectbox("Txn type", tps, key="ex_tp")
            if tp != "All":
                df = df[df["txn_type"] == tp]

        st.write(f"{len(df):,} rows")
        st.dataframe(df.head(1000), use_container_width=True, hide_index=True)

        if {"booking_date", "amount"}.issubset(df.columns):
            daily = (
                df.assign(booking_date=pd.to_datetime(df["booking_date"]))
                .groupby("booking_date", as_index=False)["amount"].sum()
            )
            st.plotly_chart(
                px.line(daily, x="booking_date", y="amount", title="Daily amount volume"),
                use_container_width=True,
            )
            if "category" in df.columns:
                cat_sum = (
                    df.groupby("category", as_index=False)["amount"].sum()
                    .sort_values("amount", ascending=False)
                )
                st.plotly_chart(
                    px.bar(cat_sum, x="category", y="amount", title="Amount by category"),
                    use_container_width=True,
                )

        st.download_button(
            "Download filtered rows", df.to_csv(index=False).encode("utf-8"),
            file_name="filtered_extract.csv", mime="text/csv",
        )

    with tab_about:
        st.markdown(
            """
            ### Project
            Portfolio platform that reconciles a **core banking ledger** against an
            **external settlement feed** using SQL validation rules and Python analytics.

            ### Data design
            Synthetic data modeled after public banking dataset patterns
            (PKDD'99-style accounts + Kaggle-style transaction fields):
            accounts, branches/regions, products, booking/value dates, fees,
            merchants, categories, channels, and lifecycle statuses.

            ### Detection coverage
            - Missing on either side
            - Amount / fee / date / status mismatches
            - Duplicate business keys
            - High-value breaks
            - Account-level exposure
            - Match quality scoring (0–100)
            - Exception workflow queue (Open / Investigating / Resolved)

            ### Tech stack
            Python · pandas · SQLite · Streamlit · Plotly

            ### Author
            **Prathusha Pasam**
            """
        )

    st.markdown("---")
    st.caption("© Prathusha Pasam · Banking Data Reconciliation Platform")


if __name__ == "__main__":
    main()
