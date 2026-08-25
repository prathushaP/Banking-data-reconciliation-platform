"""SQL + Python reconciliation engine with scoring and analytics.
Author: Prathusha Pasam
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "banking.db"

RULES = [
    {"id": "R1", "name": "Missing in External", "severity": "High",
     "description": "Core banking txn_id not found in settlement feed.", "view": "v_missing_external"},
    {"id": "R2", "name": "Missing in Internal", "severity": "High",
     "description": "Settlement residual with no core banking match.", "view": "v_missing_internal"},
    {"id": "R3", "name": "Amount Mismatch", "severity": "Critical",
     "description": "Shared txn_id with different principal amounts.", "view": "v_amount_mismatch"},
    {"id": "R4", "name": "Date Mismatch", "severity": "Medium",
     "description": "Value-date drift between core and settlement.", "view": "v_date_mismatch"},
    {"id": "R5", "name": "Status Mismatch", "severity": "Medium",
     "description": "Lifecycle status differs across systems.", "view": "v_status_mismatch"},
    {"id": "R6", "name": "Fee Mismatch", "severity": "Medium",
     "description": "Wire/ATM fee amounts do not align.", "view": "v_fee_mismatch"},
    {"id": "R7", "name": "Internal Duplicates", "severity": "Medium",
     "description": "Duplicate business-key groups in core ledger.", "view": "v_internal_duplicates"},
    {"id": "R8", "name": "External Duplicates", "severity": "Medium",
     "description": "Duplicate business-key groups in settlement feed.", "view": "v_external_duplicates"},
    {"id": "R9", "name": "High Value Breaks", "severity": "Critical",
     "description": "High-value missing items or amount breaks (>= $25 / $1000).", "view": "v_high_value_breaks"},
]

SEVERITY_WEIGHT = {"Critical": 5, "High": 3, "Medium": 2, "Low": 1}


@dataclass
class ReconResult:
    summary: pd.DataFrame
    details: dict[str, pd.DataFrame]
    kpis: dict[str, float | int]
    account_exposure: pd.DataFrame
    daily_trend: pd.DataFrame
    channel_breaks: pd.DataFrame
    region_breaks: pd.DataFrame
    match_quality: pd.DataFrame
    exceptions: pd.DataFrame


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}. Run: python src/generate_data.py")
    return sqlite3.connect(db_path)


def _assign_workflow(df: pd.DataFrame, rule_id: str, severity: str) -> pd.DataFrame:
    if df.empty:
        out = df.copy()
        for col in ["rule_id", "severity", "workflow_status", "age_days", "priority_score"]:
            out[col] = pd.Series(dtype="object" if col != "age_days" and col != "priority_score" else "float")
        return out
    out = df.copy()
    out["rule_id"] = rule_id
    out["severity"] = severity
    keys = out.get("txn_id", pd.Series(range(len(out)), index=out.index)).astype(str)
    bucket = keys.map(lambda x: sum(ord(c) for c in x) % 100)
    out["workflow_status"] = np.where(bucket < 55, "Open", np.where(bucket < 80, "Investigating", "Resolved"))
    if "booking_date" in out.columns:
        ages = (pd.Timestamp("2024-08-31") - pd.to_datetime(out["booking_date"])).dt.days
        out["age_days"] = ages.clip(lower=0)
    else:
        out["age_days"] = 0
    out["priority_score"] = out["age_days"].fillna(0) * SEVERITY_WEIGHT.get(severity, 1)
    if "amount" in out.columns:
        out["priority_score"] = out["priority_score"] + pd.to_numeric(out["amount"], errors="coerce").fillna(0) / 100
    elif "abs_diff" in out.columns:
        out["priority_score"] = out["priority_score"] + pd.to_numeric(out["abs_diff"], errors="coerce").fillna(0) / 50
    return out


def run_reconciliation(db_path: Path = DB_PATH) -> ReconResult:
    conn = get_connection(db_path)
    details: dict[str, pd.DataFrame] = {}
    rows = []
    exception_frames = []

    for rule in RULES:
        df = pd.read_sql_query(f"SELECT * FROM {rule['view']}", conn)
        details[rule["id"]] = df
        rows.append({
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "severity": rule["severity"],
            "description": rule["description"],
            "issue_count": len(df),
        })
        if rule["id"] not in {"R7", "R8"}:
            exception_frames.append(_assign_workflow(df, rule["id"], rule["severity"]))

    internal_n = int(pd.read_sql_query("SELECT COUNT(*) AS n FROM internal_ledger", conn)["n"][0])
    external_n = int(pd.read_sql_query("SELECT COUNT(*) AS n FROM external_ledger", conn)["n"][0])
    accounts_n = int(pd.read_sql_query("SELECT COUNT(*) AS n FROM accounts", conn)["n"][0])
    matched = int(pd.read_sql_query("SELECT COUNT(*) AS n FROM v_matched_clean", conn)["n"][0])
    amount_exp = float(pd.read_sql_query("SELECT COALESCE(SUM(abs_diff),0) AS s FROM v_amount_mismatch", conn)["s"][0])
    missing_exp = float(pd.read_sql_query(
        """
        SELECT COALESCE(SUM(amount),0) AS s FROM (
          SELECT amount FROM v_missing_external
          UNION ALL
          SELECT amount FROM v_missing_internal
        )
        """,
        conn,
    )["s"][0])

    account_exposure = pd.read_sql_query(
        """
        SELECT ae.*, a.customer_name, a.region, a.product_type, a.risk_segment, a.branch_id
        FROM v_account_exposure ae
        LEFT JOIN accounts a ON ae.account_id = a.account_id
        ORDER BY exposure_amount DESC
        """,
        conn,
    )
    daily_trend = pd.read_sql_query("SELECT * FROM v_daily_break_trend ORDER BY break_date", conn)
    channel_breaks = pd.read_sql_query(
        """
        SELECT channel, COUNT(*) AS issues, ROUND(SUM(amount),2) AS amount_sum
        FROM (
            SELECT channel, amount FROM v_missing_external
            UNION ALL
            SELECT channel, amount FROM v_missing_internal
            UNION ALL
            SELECT channel, abs_diff AS amount FROM v_amount_mismatch
        )
        GROUP BY channel
        ORDER BY issues DESC
        """,
        conn,
    )
    region_breaks = pd.read_sql_query(
        """
        SELECT region, COUNT(*) AS issues
        FROM (
            SELECT region FROM v_missing_external
            UNION ALL
            SELECT region FROM v_missing_internal
            UNION ALL
            SELECT region FROM v_amount_mismatch
            UNION ALL
            SELECT region FROM v_date_mismatch
        )
        WHERE region IS NOT NULL
        GROUP BY region
        ORDER BY issues DESC
        """,
        conn,
    )
    quality = pd.read_sql_query(
        """
        SELECT
            i.txn_id, i.account_id, i.booking_date, i.channel,
            i.amount AS internal_amount, e.amount AS external_amount,
            i.value_date AS internal_value_date, e.value_date AS external_value_date,
            i.status AS internal_status, e.status AS external_status,
            i.fee_amount AS internal_fee, e.fee_amount AS external_fee,
            CASE WHEN ROUND(i.amount - e.amount, 2) = 0 THEN 40 ELSE 0 END +
            CASE WHEN i.value_date = e.value_date THEN 20 ELSE 0 END +
            CASE WHEN i.status = e.status THEN 20 ELSE 0 END +
            CASE WHEN ROUND(i.fee_amount - e.fee_amount, 2) = 0 THEN 20 ELSE 0 END
            AS match_score
        FROM internal_ledger i
        INNER JOIN external_ledger e ON i.txn_id = e.txn_id
        """,
        conn,
    )
    conn.close()

    if not quality.empty:
        quality["match_band"] = pd.cut(
            quality["match_score"], bins=[-0.1, 59, 79, 99, 100],
            labels=["Poor", "Fair", "Good", "Perfect"],
        )

    summary = pd.DataFrame(rows)
    total_issues = int(summary["issue_count"].sum())
    exceptions = pd.concat(exception_frames, ignore_index=True, sort=False) if exception_frames else pd.DataFrame()
    open_n = int((exceptions["workflow_status"] == "Open").sum()) if not exceptions.empty else 0

    kpis = {
        "accounts": accounts_n,
        "internal_records": internal_n,
        "external_records": external_n,
        "matched_clean": matched,
        "total_issues": total_issues,
        "match_rate_pct": round(100 * matched / max(internal_n, 1), 2),
        "amount_exposure": round(amount_exp, 2),
        "missing_exposure": round(missing_exp, 2),
        "total_exposure": round(amount_exp + missing_exp, 2),
        "open_exceptions": open_n,
        "avg_match_score": round(float(quality["match_score"].mean()), 1) if not quality.empty else 0,
    }
    return ReconResult(
        summary=summary, details=details, kpis=kpis, account_exposure=account_exposure,
        daily_trend=daily_trend, channel_breaks=channel_breaks, region_breaks=region_breaks,
        match_quality=quality, exceptions=exceptions,
    )


def load_ledgers(db_path: Path = DB_PATH) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    conn = get_connection(db_path)
    accounts = pd.read_sql_query("SELECT * FROM accounts", conn)
    internal = pd.read_sql_query("SELECT * FROM internal_ledger", conn)
    external = pd.read_sql_query("SELECT * FROM external_ledger", conn)
    conn.close()
    return accounts, internal, external
