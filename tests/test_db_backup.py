from __future__ import annotations

import sqlite3
from pathlib import Path

from budgeting_cli import db


def test_backup_database_creates_bak_file(tmp_path: Path) -> None:
    import os

    os.chdir(tmp_path)
    conn = db.connect()
    try:
        conn.execute(
            """
            INSERT INTO transactions(
              fingerprint, booking_date, booking_date_raw, status,
              amount_cents, currency,
              sender, recipient, name, title, message, reference_number, balance,
              vendor_key, category, ignored
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "fp1",
                "2026-03-01",
                "2026/03/01",
                "booked",
                -1234,
                "EUR",
                "A",
                "B",
                "Vendor",
                "Vendor",
                "m",
                "ref",
                "0",
                "vendor",
                "shared",
                0,
            ),
        )
        conn.commit()

        bak_path = db.backup_database(conn)
        assert bak_path.exists()

        with sqlite3.connect(bak_path) as bak_conn:
            row = bak_conn.execute("SELECT COUNT(*) FROM transactions").fetchone()
            assert int(row[0]) == 1
    finally:
        conn.close()
