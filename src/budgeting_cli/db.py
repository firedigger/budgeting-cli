from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DB_FILENAME = "budgeting.sqlite"


def default_db_path() -> Path:
    return Path.cwd() / DB_FILENAME


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = default_db_path() if db_path is None else db_path
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS vendor_rules (
            vendor_key TEXT PRIMARY KEY,
            category TEXT NOT NULL CHECK(category IN ('shared','alex','luiza')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ignore_vendor_rules (
            vendor_key TEXT PRIMARY KEY,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS vendor_amount_rules (
            vendor_key TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            currency TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('shared','alex','luiza')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (vendor_key, amount_cents, currency)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY,
            fingerprint TEXT NOT NULL UNIQUE,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            booking_date TEXT NOT NULL,
            booking_date_raw TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('booked','reserved')),

            amount_cents INTEGER NOT NULL,
            currency TEXT NOT NULL,

            sender TEXT,
            recipient TEXT,
            name TEXT,
            title TEXT,
            message TEXT,
            reference_number TEXT,
            balance TEXT,

            vendor_key TEXT NOT NULL,
            category TEXT CHECK(category IN ('shared','alex','luiza','unsorted')),
            ignored INTEGER NOT NULL DEFAULT 0 CHECK(ignored IN (0,1))
        );
        """
    )

    # Lightweight migrations for existing DBs.
    # - Add transactions.ignored column if missing.
    cols = [row["name"] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()]
    if "ignored" not in cols:
        conn.execute(
            "ALTER TABLE transactions ADD COLUMN ignored INTEGER NOT NULL DEFAULT 0 CHECK(ignored IN (0,1))"
        )

    # Indexes (create after migrations so referenced columns exist).
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_transactions_booking_date ON transactions(booking_date);
        CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);
        CREATE INDEX IF NOT EXISTS idx_transactions_vendor_key ON transactions(vendor_key);
        CREATE INDEX IF NOT EXISTS idx_transactions_ignored ON transactions(ignored);
        """
    )


@dataclass(frozen=True)
class VendorRule:
    vendor_key: str
    category: str  # 'shared' | 'alex' | 'luiza'


@dataclass(frozen=True)
class VendorAmountRule:
    vendor_key: str
    amount_cents: int
    currency: str
    category: str  # 'shared' | 'alex' | 'luiza'


def load_vendor_rules(conn: sqlite3.Connection) -> dict[str, VendorRule]:
    rows = conn.execute("SELECT vendor_key, category FROM vendor_rules").fetchall()
    return {row["vendor_key"]: VendorRule(row["vendor_key"], row["category"]) for row in rows}


def load_ignore_vendor_rules(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT vendor_key FROM ignore_vendor_rules").fetchall()
    return {str(r["vendor_key"]) for r in rows}


def load_vendor_amount_rules(conn: sqlite3.Connection) -> dict[tuple[str, int, str], VendorAmountRule]:
    rows = conn.execute(
        "SELECT vendor_key, amount_cents, currency, category FROM vendor_amount_rules"
    ).fetchall()
    rules: dict[tuple[str, int, str], VendorAmountRule] = {}
    for row in rows:
        key = (row["vendor_key"], int(row["amount_cents"]), row["currency"])
        rules[key] = VendorAmountRule(
            vendor_key=row["vendor_key"],
            amount_cents=int(row["amount_cents"]),
            currency=row["currency"],
            category=row["category"],
        )
    return rules


def upsert_vendor_rule(conn: sqlite3.Connection, vendor_key: str, category: str) -> None:
    conn.execute(
        """
        INSERT INTO vendor_rules(vendor_key, category)
        VALUES(?, ?)
        ON CONFLICT(vendor_key) DO UPDATE SET category=excluded.category
        """,
        (vendor_key, category),
    )


def upsert_ignore_vendor_rule(conn: sqlite3.Connection, vendor_key: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO ignore_vendor_rules(vendor_key)
        VALUES(?)
        """,
        (vendor_key,),
    )


def upsert_vendor_amount_rule(
    conn: sqlite3.Connection, vendor_key: str, amount_cents: int, currency: str, category: str
) -> None:
    conn.execute(
        """
        INSERT INTO vendor_amount_rules(vendor_key, amount_cents, currency, category)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(vendor_key, amount_cents, currency) DO UPDATE SET category=excluded.category
        """,
        (vendor_key, amount_cents, currency, category),
    )


def mark_unsorted(conn: sqlite3.Connection, transaction_ids: Iterable[int]) -> None:
    ids = list(transaction_ids)
    if not ids:
        return
    placeholders = ",".join(["?"] * len(ids))
    conn.execute(
        f"UPDATE transactions SET category='unsorted' WHERE id IN ({placeholders}) AND category IS NULL",
        ids,
    )


def set_category(conn: sqlite3.Connection, transaction_id: int, category: str) -> None:
    conn.execute(
        "UPDATE transactions SET category=? WHERE id=?",
        (category, transaction_id),
    )


def set_ignored(conn: sqlite3.Connection, transaction_id: int, ignored: bool) -> None:
    conn.execute(
        "UPDATE transactions SET ignored=? WHERE id=?",
        (1 if ignored else 0, transaction_id),
    )


def update_transaction_state(
    conn: sqlite3.Connection,
    *,
    transaction_id: int,
    category: str | None,
    ignored: bool,
) -> None:
    conn.execute(
        "UPDATE transactions SET category=?, ignored=? WHERE id=?",
        (category, 1 if ignored else 0, transaction_id),
    )
