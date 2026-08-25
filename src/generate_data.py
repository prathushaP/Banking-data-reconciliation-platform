"""Generate synthetic banking datasets for reconciliation demos.

Schema loosely inspired by public banking/transaction datasets such as:
- PKDD'99 Financial Dataset (accounts, transactions, districts)
- Kaggle-style bank transaction CSVs (amount, type, merchant, channel)

No real customer data is used.
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

BRANCHES = [
    ("BR01", "Austin", "TX", "South"),
    ("BR02", "Dallas", "TX", "South"),
    ("BR03", "Chicago", "IL", "Midwest"),
    ("BR04", "New York", "NY", "Northeast"),
    ("BR05", "Seattle", "WA", "West"),
    ("BR06", "Denver", "CO", "West"),
    ("BR07", "Atlanta", "GA", "South"),
    ("BR08", "Boston", "MA", "Northeast"),
]
PRODUCTS = ["CHECKING", "SAVINGS", "CREDIT_CARD", "MONEY_MARKET"]
CHANNELS = ["ACH", "WIRE", "CARD", "CHECK", "ATM", "ONLINE", "MOBILE"]
TXN_TYPES = ["CREDIT", "DEBIT"]
STATUSES = ["POSTED", "PENDING", "SETTLED", "REVERSED"]
CURRENCIES = ["USD", "USD", "USD", "USD", "EUR", "GBP"]
CATEGORIES = [
    "Payroll", "Retail", "Grocery", "Travel", "Utilities", "Healthcare",
    "Transfer", "ATM Withdrawal", "Fee", "Interest", "Subscription", "Restaurant",
]
MERCHANTS = [
    "ACME Payroll", "Whole Foods", "Amazon", "Uber", "Delta Air", "City Power",
    "CVS Pharmacy", "Internal Transfer", "ATM Network", "Netflix", "Starbucks",
    "Home Depot", "Chase Settlement", "Fedwire Hub", "Stripe Payout",
]


def build_accounts(n: int = 80) -> pd.DataFrame:
    rows = []
    for i in range(n):
        branch = BRANCHES[i % len(BRANCHES)]
        rows.append(
            {
                "account_id": f"ACC{10000 + i}",
                "customer_name": f"Customer {i + 1:03d}",
                "branch_id": branch[0],
                "city": branch[1],
                "state": branch[2],
                "region": branch[3],
                "product_type": str(RNG.choice(PRODUCTS)),
                "currency": str(RNG.choice(CURRENCIES)),
                "open_date": str(
                    pd.Timestamp("2018-01-01")
                    + pd.Timedelta(days=int(RNG.integers(0, 2000)))
                )[:10],
                "risk_segment": str(RNG.choice(["Low", "Medium", "High"], p=[0.6, 0.3, 0.1])),
            }
        )
    return pd.DataFrame(rows)


def _sample_amount(channel: str, category: str) -> float:
    if category in {"Fee", "Interest"}:
        return round(float(RNG.uniform(1, 45)), 2)
    if channel == "WIRE":
        return round(float(RNG.lognormal(8.2, 0.7)), 2)
    if channel == "ATM":
        return round(float(RNG.choice([20, 40, 60, 80, 100, 200])), 2)
    if channel == "CARD":
        return round(float(RNG.lognormal(3.8, 0.9)), 2)
    return round(float(RNG.lognormal(5.5, 1.0)), 2)


def build_base_transactions(accounts: pd.DataFrame, n: int = 4500) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=240, freq="D")
    acc_ids = accounts["account_id"].tolist()
    rows = []
    for i in range(n):
        account_id = str(RNG.choice(acc_ids))
        channel = str(RNG.choice(CHANNELS, p=[0.22, 0.08, 0.30, 0.08, 0.08, 0.14, 0.10]))
        category = str(RNG.choice(CATEGORIES))
        txn_type = (
            "CREDIT"
            if category in {"Payroll", "Interest", "Transfer"} and RNG.random() < 0.7
            else str(RNG.choice(TXN_TYPES, p=[0.42, 0.58]))
        )
        booking = dates[int(RNG.integers(0, len(dates)))]
        value_date = booking + pd.Timedelta(days=int(RNG.choice([0, 0, 0, 1, 1, 2])))
        amount = _sample_amount(channel, category)
        fee = (
            round(float(RNG.choice([0, 0, 0, 0, 1.5, 2.5, 15, 25])), 2)
            if channel in {"WIRE", "ATM"}
            else 0.0
        )
        status = str(RNG.choice(STATUSES, p=[0.78, 0.08, 0.11, 0.03]))
        currency = accounts.loc[accounts["account_id"] == account_id, "currency"].iloc[0]
        rows.append(
            {
                "txn_id": f"TXN{i + 1:06d}",
                "account_id": account_id,
                "booking_date": booking.strftime("%Y-%m-%d"),
                "value_date": value_date.strftime("%Y-%m-%d"),
                "amount": amount,
                "fee_amount": fee,
                "currency": currency,
                "txn_type": txn_type,
                "channel": channel,
                "category": category,
                "merchant": str(RNG.choice(MERCHANTS)),
                "status": status,
                "reference": f"REF{int(RNG.integers(100000, 999999))}",
                "counterparty": f"CP{int(RNG.integers(1000, 9999))}",
                "description": f"{category} via {channel}",
            }
        )
    return pd.DataFrame(rows)


def inject_issues(base: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    internal = base.copy()
    external = base.copy()

    drop_ext = internal.sample(120, random_state=1)["txn_id"].tolist()
    external = external[~external["txn_id"].isin(drop_ext)].copy()

    extra = base.sample(80, random_state=2).copy()
    extra["txn_id"] = [f"EXT{i + 1:06d}" for i in range(len(extra))]
    extra["description"] = "External-only settlement residual"
    extra["merchant"] = "Clearing House"
    external = pd.concat([external, extra], ignore_index=True)

    mismatch_ids = internal.sample(90, random_state=3)["txn_id"].tolist()
    mask = external["txn_id"].isin(mismatch_ids)
    n = int(mask.sum())
    external.loc[mask, "amount"] = (
        external.loc[mask, "amount"].to_numpy()
        + RNG.choice([-1, 1], size=n) * RNG.uniform(0.3, 40, size=n)
    ).round(2)

    date_ids = internal.sample(70, random_state=6)["txn_id"].tolist()
    dmask = external["txn_id"].isin(date_ids)
    shifted = pd.to_datetime(external.loc[dmask, "value_date"]) + pd.to_timedelta(
        RNG.choice([1, 2, 3], size=int(dmask.sum())), unit="D"
    )
    external.loc[dmask, "value_date"] = shifted.dt.strftime("%Y-%m-%d").to_numpy()

    status_ids = internal.sample(55, random_state=7)["txn_id"].tolist()
    smask = external["txn_id"].isin(status_ids)
    external.loc[smask, "status"] = [
        str(RNG.choice(["PENDING", "SETTLED", "REVERSED"])) for _ in range(int(smask.sum()))
    ]

    fee_ids = internal.sample(40, random_state=8)["txn_id"].tolist()
    fmask = external["txn_id"].isin(fee_ids)
    external.loc[fmask, "fee_amount"] = (
        external.loc[fmask, "fee_amount"].to_numpy() + RNG.uniform(0.5, 12, size=int(fmask.sum()))
    ).round(2)

    dups_i = internal.sample(45, random_state=4).copy()
    dups_i["txn_id"] = [f"DUP{i + 1:06d}" for i in range(len(dups_i))]
    dups_i["description"] = dups_i["description"] + " [REPOST]"
    internal = pd.concat([internal, dups_i], ignore_index=True)

    dups_e = external.sample(35, random_state=5).copy()
    dups_e["txn_id"] = [f"EDUP{i + 1:06d}" for i in range(len(dups_e))]
    dups_e["description"] = dups_e["description"] + " [REPOST]"
    external = pd.concat([external, dups_e], ignore_index=True)

    internal["source_system"] = "CORE_BANKING"
    external["source_system"] = "SETTLEMENT_FEED"
    return internal.reset_index(drop=True), external.reset_index(drop=True)


def save_all(accounts: pd.DataFrame, internal: pd.DataFrame, external: pd.DataFrame) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    accounts.to_csv(DATA_DIR / "accounts.csv", index=False)
    internal.to_csv(DATA_DIR / "internal_ledger.csv", index=False)
    external.to_csv(DATA_DIR / "external_ledger.csv", index=False)

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    accounts.to_sql("accounts", conn, if_exists="replace", index=False)
    internal.to_sql("internal_ledger", conn, if_exists="replace", index=False)
    external.to_sql("external_ledger", conn, if_exists="replace", index=False)

    conn.executescript(
        """
        DROP VIEW IF EXISTS v_missing_external;
        DROP VIEW IF EXISTS v_missing_internal;
        DROP VIEW IF EXISTS v_amount_mismatch;
        DROP VIEW IF EXISTS v_date_mismatch;
        DROP VIEW IF EXISTS v_status_mismatch;
        DROP VIEW IF EXISTS v_fee_mismatch;
        DROP VIEW IF EXISTS v_internal_duplicates;
        DROP VIEW IF EXISTS v_external_duplicates;
        DROP VIEW IF EXISTS v_high_value_breaks;
        DROP VIEW IF EXISTS v_account_exposure;
        DROP VIEW IF EXISTS v_matched_clean;
        DROP VIEW IF EXISTS v_daily_break_trend;

        CREATE VIEW v_missing_external AS
        SELECT i.*, a.customer_name, a.branch_id, a.region, a.product_type, a.risk_segment
        FROM internal_ledger i
        LEFT JOIN external_ledger e ON i.txn_id = e.txn_id
        LEFT JOIN accounts a ON i.account_id = a.account_id
        WHERE e.txn_id IS NULL;

        CREATE VIEW v_missing_internal AS
        SELECT e.*, a.customer_name, a.branch_id, a.region, a.product_type, a.risk_segment
        FROM external_ledger e
        LEFT JOIN internal_ledger i ON e.txn_id = i.txn_id
        LEFT JOIN accounts a ON e.account_id = a.account_id
        WHERE i.txn_id IS NULL;

        CREATE VIEW v_amount_mismatch AS
        SELECT
            i.txn_id, i.account_id, i.booking_date, i.channel, i.category, i.currency,
            i.amount AS internal_amount, e.amount AS external_amount,
            ROUND(i.amount - e.amount, 2) AS amount_diff,
            ROUND(ABS(i.amount - e.amount), 2) AS abs_diff,
            a.customer_name, a.region, a.risk_segment
        FROM internal_ledger i
        INNER JOIN external_ledger e ON i.txn_id = e.txn_id
        LEFT JOIN accounts a ON i.account_id = a.account_id
        WHERE ROUND(i.amount - e.amount, 2) != 0;

        CREATE VIEW v_date_mismatch AS
        SELECT
            i.txn_id, i.account_id, i.booking_date,
            i.value_date AS internal_value_date,
            e.value_date AS external_value_date,
            CAST(julianday(e.value_date) - julianday(i.value_date) AS INT) AS day_drift,
            i.channel, i.amount, a.region, a.risk_segment
        FROM internal_ledger i
        INNER JOIN external_ledger e ON i.txn_id = e.txn_id
        LEFT JOIN accounts a ON i.account_id = a.account_id
        WHERE i.value_date != e.value_date;

        CREATE VIEW v_status_mismatch AS
        SELECT
            i.txn_id, i.account_id, i.booking_date, i.amount, i.channel,
            i.status AS internal_status, e.status AS external_status,
            a.customer_name, a.region
        FROM internal_ledger i
        INNER JOIN external_ledger e ON i.txn_id = e.txn_id
        LEFT JOIN accounts a ON i.account_id = a.account_id
        WHERE i.status != e.status;

        CREATE VIEW v_fee_mismatch AS
        SELECT
            i.txn_id, i.account_id, i.booking_date, i.channel,
            i.fee_amount AS internal_fee, e.fee_amount AS external_fee,
            ROUND(i.fee_amount - e.fee_amount, 2) AS fee_diff,
            i.amount, a.region
        FROM internal_ledger i
        INNER JOIN external_ledger e ON i.txn_id = e.txn_id
        LEFT JOIN accounts a ON i.account_id = a.account_id
        WHERE ROUND(i.fee_amount - e.fee_amount, 2) != 0;

        CREATE VIEW v_internal_duplicates AS
        SELECT account_id, booking_date, amount, txn_type, channel, merchant,
               COUNT(*) AS dup_count, ROUND(SUM(amount), 2) AS total_amount
        FROM internal_ledger
        GROUP BY account_id, booking_date, amount, txn_type, channel, merchant
        HAVING COUNT(*) > 1;

        CREATE VIEW v_external_duplicates AS
        SELECT account_id, booking_date, amount, txn_type, channel, merchant,
               COUNT(*) AS dup_count, ROUND(SUM(amount), 2) AS total_amount
        FROM external_ledger
        GROUP BY account_id, booking_date, amount, txn_type, channel, merchant
        HAVING COUNT(*) > 1;

        CREATE VIEW v_high_value_breaks AS
        SELECT * FROM v_amount_mismatch WHERE abs_diff >= 25
        UNION ALL
        SELECT
            txn_id, account_id, booking_date, channel, category, currency,
            amount AS internal_amount, NULL AS external_amount,
            amount AS amount_diff, amount AS abs_diff,
            customer_name, region, risk_segment
        FROM v_missing_external WHERE amount >= 1000
        UNION ALL
        SELECT
            txn_id, account_id, booking_date, channel, category, currency,
            NULL AS internal_amount, amount AS external_amount,
            amount AS amount_diff, amount AS abs_diff,
            customer_name, region, risk_segment
        FROM v_missing_internal WHERE amount >= 1000;

        CREATE VIEW v_matched_clean AS
        SELECT i.txn_id, i.account_id, i.booking_date, i.amount, i.channel, i.category, i.status
        FROM internal_ledger i
        INNER JOIN external_ledger e ON i.txn_id = e.txn_id
        WHERE ROUND(i.amount - e.amount, 2) = 0
          AND i.value_date = e.value_date
          AND i.status = e.status
          AND ROUND(i.fee_amount - e.fee_amount, 2) = 0;

        CREATE VIEW v_account_exposure AS
        SELECT
            account_id,
            COUNT(*) AS break_count,
            ROUND(SUM(abs_diff), 2) AS exposure_amount
        FROM (
            SELECT account_id, abs_diff FROM v_amount_mismatch
            UNION ALL
            SELECT account_id, amount AS abs_diff FROM v_missing_external
            UNION ALL
            SELECT account_id, amount AS abs_diff FROM v_missing_internal
        )
        GROUP BY account_id;

        CREATE VIEW v_daily_break_trend AS
        SELECT booking_date AS break_date, 'Amount Mismatch' AS break_type, COUNT(*) AS issues
        FROM v_amount_mismatch GROUP BY booking_date
        UNION ALL
        SELECT booking_date, 'Missing External', COUNT(*) FROM v_missing_external GROUP BY booking_date
        UNION ALL
        SELECT booking_date, 'Missing Internal', COUNT(*) FROM v_missing_internal GROUP BY booking_date
        UNION ALL
        SELECT booking_date, 'Date Mismatch', COUNT(*) FROM v_date_mismatch GROUP BY booking_date
        UNION ALL
        SELECT booking_date, 'Status Mismatch', COUNT(*) FROM v_status_mismatch GROUP BY booking_date;
        """
    )
    conn.commit()
    conn.close()
    return DB_PATH


def main() -> None:
    accounts = build_accounts()
    base = build_base_transactions(accounts)
    internal, external = inject_issues(base)
    path = save_all(accounts, internal, external)
    print(f"Generated datasets -> {DATA_DIR}")
    print(f"SQLite DB -> {path}")
    print(f"Accounts: {len(accounts)} | Internal: {len(internal)} | External: {len(external)}")


if __name__ == "__main__":
    main()
