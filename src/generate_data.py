"""Generate synthetic banking datasets for reconciliation demos.
Inspired by public transaction schemas (e.g. Kaggle banking/transaction CSVs).
Author: Prathusha Pasam
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "banking.db"

ACCOUNTS = [f"ACC{1000 + i}" for i in range(25)]
CHANNELS = ["ACH", "WIRE", "CARD", "CHECK", "ATM"]
TYPES = ["CREDIT", "DEBIT"]


def _base_transactions(n: int = 800) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=120, freq="D").strftime("%Y-%m-%d").tolist()
    rows = []
    for i in range(n):
        amt = round(float(RNG.uniform(10, 5000)), 2)
        rows.append(
            {
                "txn_id": f"TXN{i + 1:05d}",
                "account_id": str(RNG.choice(ACCOUNTS)),
                "txn_date": str(RNG.choice(dates)),
                "amount": amt,
                "txn_type": str(RNG.choice(TYPES)),
                "channel": str(RNG.choice(CHANNELS)),
                "description": f"Payment {i + 1}",
            }
        )
    return pd.DataFrame(rows)


def build_ledgers(base: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create internal vs external ledgers with intentional issues."""
    internal = base.copy()
    external = base.copy()

    # Missing in external (present only internally)
    drop_ext = internal.sample(40, random_state=1)["txn_id"].tolist()
    external = external[~external["txn_id"].isin(drop_ext)]

    # Missing in internal (present only externally)
    extra = base.sample(25, random_state=2).copy()
    extra["txn_id"] = [f"EXT{i + 1:05d}" for i in range(len(extra))]
    extra["description"] = "External-only settlement"
    external = pd.concat([external, extra], ignore_index=True)

    # Amount mismatches
    mismatch_ids = internal.sample(35, random_state=3)["txn_id"].tolist()
    mask = external["txn_id"].isin(mismatch_ids)
    external.loc[mask, "amount"] = (
        external.loc[mask, "amount"] + RNG.choice([-1, 1], size=mask.sum()) * RNG.uniform(0.5, 25, size=mask.sum())
    ).round(2)

    # Duplicates in internal
    dups = internal.sample(20, random_state=4)
    dups["txn_id"] = [f"DUP{i + 1:05d}" for i in range(len(dups))]
    internal = pd.concat([internal, dups], ignore_index=True)

    # Duplicates in external
    dups_e = external.sample(15, random_state=5)
    dups_e["txn_id"] = [f"EDUP{i + 1:05d}" for i in range(len(dups_e))]
    external = pd.concat([external, dups_e], ignore_index=True)

    internal["source"] = "internal"
    external["source"] = "external"
    return internal.reset_index(drop=True), external.reset_index(drop=True)


def save_all(internal: pd.DataFrame, external: pd.DataFrame) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    internal.to_csv(DATA_DIR / "internal_ledger.csv", index=False)
    external.to_csv(DATA_DIR / "external_ledger.csv", index=False)

    conn = sqlite3.connect(DB_PATH)
    internal.to_sql("internal_ledger", conn, if_exists="replace", index=False)
    external.to_sql("external_ledger", conn, if_exists="replace", index=False)
    conn.executescript(
        """
        CREATE VIEW IF NOT EXISTS v_missing_external AS
        SELECT i.*
        FROM internal_ledger i
        LEFT JOIN external_ledger e ON i.txn_id = e.txn_id
        WHERE e.txn_id IS NULL;

        CREATE VIEW IF NOT EXISTS v_missing_internal AS
        SELECT e.*
        FROM external_ledger e
        LEFT JOIN internal_ledger i ON e.txn_id = i.txn_id
        WHERE i.txn_id IS NULL;

        CREATE VIEW IF NOT EXISTS v_amount_mismatch AS
        SELECT
            i.txn_id,
            i.account_id,
            i.txn_date,
            i.amount AS internal_amount,
            e.amount AS external_amount,
            ROUND(i.amount - e.amount, 2) AS amount_diff,
            i.txn_type,
            i.channel
        FROM internal_ledger i
        INNER JOIN external_ledger e ON i.txn_id = e.txn_id
        WHERE ROUND(i.amount - e.amount, 2) != 0;

        CREATE VIEW IF NOT EXISTS v_internal_duplicates AS
        SELECT account_id, txn_date, amount, txn_type, channel, COUNT(*) AS dup_count
        FROM internal_ledger
        GROUP BY account_id, txn_date, amount, txn_type, channel
        HAVING COUNT(*) > 1;

        CREATE VIEW IF NOT EXISTS v_external_duplicates AS
        SELECT account_id, txn_date, amount, txn_type, channel, COUNT(*) AS dup_count
        FROM external_ledger
        GROUP BY account_id, txn_date, amount, txn_type, channel
        HAVING COUNT(*) > 1;
        """
    )
    conn.commit()
    conn.close()
    return DB_PATH


def main() -> None:
    base = _base_transactions()
    internal, external = build_ledgers(base)
    path = save_all(internal, external)
    print(f"Generated datasets -> {DATA_DIR}")
    print(f"SQLite DB -> {path}")
    print(f"Internal rows: {len(internal)} | External rows: {len(external)}")


if __name__ == "__main__":
    main()
