"""SQL + Python reconciliation engine.
Author: Prathusha Pasam
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "banking.db"

RULES = [
    {
        "id": "R1",
        "name": "Missing in External",
        "severity": "High",
        "description": "Internal txn_id has no matching external record.",
        "view": "v_missing_external",
    },
    {
        "id": "R2",
        "name": "Missing in Internal",
        "severity": "High",
        "description": "External txn_id has no matching internal record.",
        "view": "v_missing_internal",
    },
    {
        "id": "R3",
        "name": "Amount Mismatch",
        "severity": "Critical",
        "description": "Same txn_id exists in both ledgers but amounts differ.",
        "view": "v_amount_mismatch",
    },
    {
        "id": "R4",
        "name": "Internal Duplicates",
        "severity": "Medium",
        "description": "Duplicate business-key groups in the internal ledger.",
        "view": "v_internal_duplicates",
    },
    {
        "id": "R5",
        "name": "External Duplicates",
        "severity": "Medium",
        "description": "Duplicate business-key groups in the external ledger.",
        "view": "v_external_duplicates",
    },
]


@dataclass
class ReconResult:
    summary: pd.DataFrame
    details: dict[str, pd.DataFrame]
    kpis: dict[str, float | int]


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(
            f"Database not found at {db_path}. Run: python src/generate_data.py"
        )
    return sqlite3.connect(db_path)


def run_reconciliation(db_path: Path = DB_PATH) -> ReconResult:
    conn = get_connection(db_path)
    details: dict[str, pd.DataFrame] = {}
    rows = []

    for rule in RULES:
        df = pd.read_sql_query(f"SELECT * FROM {rule['view']}", conn)
        details[rule["id"]] = df
        rows.append(
            {
                "rule_id": rule["id"],
                "rule_name": rule["name"],
                "severity": rule["severity"],
                "description": rule["description"],
                "issue_count": len(df),
            }
        )

    internal_n = pd.read_sql_query("SELECT COUNT(*) AS n FROM internal_ledger", conn)["n"][0]
    external_n = pd.read_sql_query("SELECT COUNT(*) AS n FROM external_ledger", conn)["n"][0]
    matched = pd.read_sql_query(
        """
        SELECT COUNT(*) AS n
        FROM internal_ledger i
        INNER JOIN external_ledger e ON i.txn_id = e.txn_id
        WHERE ROUND(i.amount - e.amount, 2) = 0
        """,
        conn,
    )["n"][0]
    conn.close()

    summary = pd.DataFrame(rows)
    total_issues = int(summary["issue_count"].sum())
    kpis = {
        "internal_records": int(internal_n),
        "external_records": int(external_n),
        "matched_clean": int(matched),
        "total_issues": total_issues,
        "match_rate_pct": round(100 * matched / max(internal_n, 1), 2),
    }
    return ReconResult(summary=summary, details=details, kpis=kpis)


def load_ledgers(db_path: Path = DB_PATH) -> tuple[pd.DataFrame, pd.DataFrame]:
    conn = get_connection(db_path)
    internal = pd.read_sql_query("SELECT * FROM internal_ledger", conn)
    external = pd.read_sql_query("SELECT * FROM external_ledger", conn)
    conn.close()
    return internal, external
