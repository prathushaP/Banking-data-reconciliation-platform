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
def get_results(_version: int = 3):
    ensure_data(force=False)
    return run_reconciliation(DB_PATH)


@st.cache_data(show_spinner=False)
def get_ledgers(_version: int = 3):
    ensure_data(force=False)
    return load_ledgers(DB_PATH)


def money(v: float) -> str:
    return f"${v:,.2f}"


def apply_exception_filters(
    ex: pd.DataFrame,
    severities: list[str],
    statuses: list[str],
    channel: str,
    region: str,
) -> pd.DataFrame:
    if ex.empty:
        return ex
    out = ex.copy()
    if severities and "severity" in out.columns:
        out = out[out["severity"].isin(severities)]
    if statuses and "workflow_status" in out.columns:
        out = out[out["workflow_status"].isin(statuses)]
    if channel != "All" and "channel" in out.columns:
        out = out[out["channel"] == channel]
    if region != "All" and "region" in out.columns:
        out = out[out["region"] == region]
    if "priority_score" in out.columns:
        out = out.sort_values("priority_score", ascending=False)
    return out


def filter_ledger(
    df: pd.DataFrame,
    channel: str,
    region: str,
    accounts: pd.DataFrame,
) -> pd.DataFrame:
    out = df.copy()
    if channel != "All" and "channel" in out.columns:
        out = out[out["channel"] == channel]
    if region != "All":
        region_accounts = set(accounts.loc[accounts["region"] == region, "account_id"].astype(str))
        if "account_id" in out.columns:
            out = out[out["account_id"].astype(str).isin(region_accounts)]
        elif "region" in out.columns:
            out = out[out["region"] == region]
    return out


def main() -> None:
    st.sidebar.title("Controls")
    st.sidebar.caption("Prathusha Pasam · Portfolio")
    st.sidebar.info(
        "These filters update **Overview, Workbench, Match Quality, and Explore**."
    )

    if st.sidebar.button("Regenerate synthetic data"):
        st.cache_data.clear()
        ensure_data(force=True)
        st.sidebar.success("Data regenerated")
        st.rerun()

    if st.sidebar.button("Reset filters"):
        for key in ["sev_filter", "status_filter", "channel_filter", "region_filter"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    result = get_results()
    accounts, internal, external = get_ledgers()

    severities = st.sidebar.multiselect(
        "Severity",
        ["Critical", "High", "Medium", "Low"],
        default=["Critical", "High", "Medium"],
        key="sev_filter",
    )
    statuses = st.sidebar.multiselect(
        "Workflow status",
        ["Open", "Investigating", "Resolved"],
        default=["Open", "Investigating"],
        key="status_filter",
    )
    channels = ["All"] + sorted(internal["channel"].dropna().unique().tolist())
    channel = st.sidebar.selectbox("Channel filter", channels, key="channel_filter")
    regions = ["All"] + sorted(accounts["region"].dropna().unique().tolist())
    region = st.sidebar.selectbox("Region filter", regions, key="region_filter")

    # Global filtered datasets driven by sidebar controls
    ex_all = result.exceptions.copy() if result.exceptions is not None else pd.DataFrame()
    ex = apply_exception_filters(ex_all, severities, statuses, channel, region)

    internal_f = filter_ledger(internal, channel, region, accounts)
    external_f = filter_ledger(external, channel, region, accounts)
    accounts_f = accounts.copy()
    if region != "All":
        accounts_f = accounts_f[accounts_f["region"] == region]

    # Filtered summary from exception queue (rule counts under active filters)
    if ex.empty:
        summary_f = result.summary.copy()
        summary_f["issue_count"] = 0
    else:
        rule_counts = ex.groupby("rule_id", as_index=False).size().rename(columns={"size": "issue_count"})
        summary_f = result.summary.drop(columns=["issue_count"]).merge(
            rule_counts, on="rule_id", how="left"
        )
        summary_f["issue_count"] = summary_f["issue_count"].fillna(0).astype(int)

    # Channel / region break charts from filtered exceptions
    if not ex.empty and "channel" in ex.columns:
        channel_breaks_f = (
            ex.dropna(subset=["channel"])
            .groupby("channel", as_index=False)
            .agg(issues=("channel", "size"))
        )
        if "amount" in ex.columns:
            channel_breaks_f = channel_breaks_f.merge(
                ex.groupby("channel", as_index=False)["amount"].sum().rename(columns={"amount": "amount_sum"}),
                on="channel",
                how="left",
            )
        else:
            channel_breaks_f["amount_sum"] = 0
        channel_breaks_f = channel_breaks_f.sort_values("issues", ascending=False)
    else:
        channel_breaks_f = pd.DataFrame(columns=["channel", "issues", "amount_sum"])

    if not ex.empty and "region" in ex.columns:
        region_breaks_f = (
            ex.dropna(subset=["region"])
            .groupby("region", as_index=False)
            .size()
            .rename(columns={"size": "issues"})
            .sort_values("issues", ascending=False)
        )
    else:
        region_breaks_f = pd.DataFrame(columns=["region", "issues"])

    # Daily trend from filtered exceptions
    if not ex.empty and "booking_date" in ex.columns and "rule_id" in ex.columns:
        rule_name_map = {r["id"]: r["name"] for r in RULES}
        trend = ex.copy()
        trend["break_type"] = trend["rule_id"].map(rule_name_map).fillna(trend["rule_id"])
        daily_trend_f = (
            trend.groupby(["booking_date", "break_type"], as_index=False)
            .size()
            .rename(columns={"booking_date": "break_date", "size": "issues"})
        )
    else:
        daily_trend_f = pd.DataFrame(columns=["break_date", "break_type", "issues"])

    # Account exposure from filtered exceptions
    if not ex.empty and "account_id" in ex.columns:
        amt = pd.to_numeric(ex["amount"], errors="coerce") if "amount" in ex.columns else 0
        abd = pd.to_numeric(ex["abs_diff"], errors="coerce") if "abs_diff" in ex.columns else 0
        tmp = ex.copy()
        tmp["_exp"] = pd.Series(amt).fillna(0)
        if isinstance(abd, pd.Series):
            tmp["_exp"] = tmp["_exp"].where(tmp["_exp"] > 0, abd.fillna(0))
        account_exposure_f = (
            tmp.groupby("account_id", as_index=False)
            .agg(break_count=("account_id", "size"), exposure_amount=("_exp", "sum"))
            .sort_values("exposure_amount", ascending=False)
        )
        account_exposure_f = account_exposure_f.merge(
            accounts[["account_id", "customer_name", "region", "product_type", "risk_segment", "branch_id"]],
            on="account_id",
            how="left",
        )
    else:
        account_exposure_f = result.account_exposure.iloc[0:0].copy()

    # Match quality filtered by channel/region via ledgers
    q = result.match_quality.copy()
    if not q.empty:
        if channel != "All" and "channel" in q.columns:
            q = q[q["channel"] == channel]
        if region != "All" and "account_id" in q.columns:
            region_accounts = set(accounts.loc[accounts["region"] == region, "account_id"].astype(str))
            q = q[q["account_id"].astype(str).isin(region_accounts)]

    open_n = int((ex["workflow_status"] == "Open").sum()) if not ex.empty and "workflow_status" in ex.columns else 0
    inv_n = int((ex["workflow_status"] == "Investigating").sum()) if not ex.empty and "workflow_status" in ex.columns else 0
    total_issues_f = int(summary_f["issue_count"].sum()) if not summary_f.empty else 0
    amount_exp_f = float(pd.to_numeric(ex.get("abs_diff", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not ex.empty else 0.0
    missing_like = ex[ex["rule_id"].isin(["R1", "R2"])] if not ex.empty and "rule_id" in ex.columns else pd.DataFrame()
    missing_exp_f = float(pd.to_numeric(missing_like.get("amount", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not missing_like.empty else 0.0
    avg_score = round(float(q["match_score"].mean()), 1) if not q.empty else 0.0

    st.title("🏦 Banking Data Reconciliation Platform")
    st.caption(
        "Built by **Prathusha Pasam** · Core ledger vs settlement feed · SQL validation · Exception workbench"
    )

    active = (
        f"**Active filters:** severity={', '.join(severities) or 'None'} · "
        f"status={', '.join(statuses) or 'None'} · channel={channel} · region={region}"
    )
    st.success(active + f" · showing **{len(ex):,}** exception rows")

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Accounts (filtered)", f"{len(accounts_f):,}")
    m2.metric("Internal txns (filtered)", f"{len(internal_f):,}")
    m3.metric("External txns (filtered)", f"{len(external_f):,}")
    m4.metric("Clean matches (all)", f"{result.kpis['matched_clean']:,}")
    m5.metric("Match rate (all)", f"{result.kpis['match_rate_pct']}%")
    m6.metric("Open exceptions (filtered)", f"{open_n:,}")

    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Filtered issues", f"{total_issues_f:,}")
    e2.metric("Amount exposure (filtered)", money(amount_exp_f))
    e3.metric("Missing exposure (filtered)", money(missing_exp_f))
    e4.metric("Avg match score (filtered)", f"{avg_score}/100")

    tab_overview, tab_rules, tab_workbench, tab_quality, tab_explore, tab_about = st.tabs(
        ["Overview", "Validation Rules", "Exception Workbench", "Match Quality", "Explore Data", "About"]
    )

    with tab_overview:
        c1, c2 = st.columns([1.2, 1])
        with c1:
            st.subheader("Issues by rule (filtered)")
            fig = px.bar(
                summary_f, x="rule_name", y="issue_count", color="severity",
                color_discrete_map=SEV_COLOR, text="issue_count",
            )
            fig.update_layout(xaxis_title="", yaxis_title="Issues", height=390, margin=dict(t=20))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("Severity mix (filtered)")
            sev = summary_f.groupby("severity", as_index=False)["issue_count"].sum()
            sev = sev[sev["issue_count"] > 0]
            if sev.empty:
                st.info("No issues for current filters.")
            else:
                fig2 = px.pie(
                    sev, names="severity", values="issue_count", hole=0.45,
                    color="severity", color_discrete_map=SEV_COLOR,
                )
                fig2.update_layout(height=390, margin=dict(t=20))
                st.plotly_chart(fig2, use_container_width=True)

        c3, c4 = st.columns(2)
        with c3:
            st.subheader("Breaks by channel (filtered)")
            if channel_breaks_f.empty:
                st.info("No channel breaks for current filters.")
            else:
                fig3 = px.bar(channel_breaks_f, x="channel", y="issues", text="issues", color="amount_sum")
                fig3.update_layout(height=360, margin=dict(t=20))
                st.plotly_chart(fig3, use_container_width=True)
        with c4:
            st.subheader("Breaks by region (filtered)")
            if region_breaks_f.empty:
                st.info("No region breaks for current filters.")
            else:
                fig4 = px.bar(region_breaks_f, x="region", y="issues", text="issues", color="issues")
                fig4.update_layout(height=360, margin=dict(t=20))
                st.plotly_chart(fig4, use_container_width=True)

        st.subheader("Daily break trend (filtered)")
        if daily_trend_f.empty:
            st.info("No trend data for current filters.")
        else:
            trend_plot = daily_trend_f.copy()
            trend_plot["break_date"] = pd.to_datetime(trend_plot["break_date"])
            fig5 = px.area(trend_plot, x="break_date", y="issues", color="break_type")
            fig5.update_layout(height=360, margin=dict(t=20))
            st.plotly_chart(fig5, use_container_width=True)

        st.subheader("Top account exposure (filtered)")
        st.dataframe(account_exposure_f.head(20), use_container_width=True, hide_index=True)
        st.subheader("Rule catalog summary (filtered)")
        st.dataframe(summary_f, use_container_width=True, hide_index=True)

    with tab_rules:
        labels = {f"{r['id']} · {r['name']} ({r['severity']})": r["id"] for r in RULES}
        choice = st.selectbox("Select validation rule", list(labels.keys()))
        rid = labels[choice]
        meta = next(r for r in RULES if r["id"] == rid)
        st.info(f"**{meta['severity']}** — {meta['description']}")

        # Prefer filtered exception rows for this rule when available
        if not ex.empty and "rule_id" in ex.columns:
            df = ex[ex["rule_id"] == rid].copy()
            st.caption("Showing rows after sidebar filters (from exception queue).")
        else:
            df = result.details[rid]
            # still apply channel/region when columns exist
            if channel != "All" and "channel" in df.columns:
                df = df[df["channel"] == channel]
            if region != "All" and "region" in df.columns:
                df = df[df["region"] == region]
            st.caption("Showing rule detail view with channel/region filters when available.")

        st.write(f"{len(df):,} finding(s)")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download findings CSV", df.to_csv(index=False).encode("utf-8"),
            file_name=f"{rid.lower()}_findings.csv", mime="text/csv",
        )

    with tab_workbench:
        st.subheader("Exception queue (live filtered)")
        if not ex.empty:
            k1, k2, k3 = st.columns(3)
            k1.metric("Queued rows", f"{len(ex):,}")
            k2.metric("Open", f"{open_n:,}")
            k3.metric("Investigating", f"{inv_n:,}")

            if "workflow_status" in ex.columns:
                wc = ex.groupby("workflow_status", as_index=False).size()
                st.plotly_chart(
                    px.pie(wc, names="workflow_status", values="size", hole=0.4),
                    use_container_width=True,
                )

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
            st.warning("No exceptions match the current sidebar controls. Try Reset filters.")

    with tab_quality:
        st.subheader("Pairwise match quality (filtered by channel/region)")
        if q.empty:
            st.warning("No overlapping transactions for current filters.")
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
            df = accounts_f.copy()
        elif src == "Internal ledger":
            df = internal_f.copy()
        else:
            df = external_f.copy()

        st.caption("Starts from sidebar channel/region filters, then local filters below.")

        f1, f2, f3, f4 = st.columns(4)
        if "account_id" in df.columns:
            accs = ["All"] + sorted(df["account_id"].astype(str).unique().tolist())
            acc = f1.selectbox("Account", accs, key="ex_acc")
            if acc != "All":
                df = df[df["account_id"].astype(str) == acc]
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

        if {"booking_date", "amount"}.issubset(df.columns) and not df.empty:
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

            ### Controls
            Sidebar filters are **global**. They update Overview KPIs/charts, Exception
            Workbench, Validation Rules, Match Quality, and Explore Data.

            ### Author
            **Prathusha Pasam**
            """
        )

    st.markdown("---")
    st.caption("© Prathusha Pasam · Banking Data Reconciliation Platform")


if __name__ == "__main__":
    main()
