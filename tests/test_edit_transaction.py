from __future__ import annotations

import sqlite3
from pathlib import Path

from budgeting_cli import db


def test_update_transaction_state_sets_skip_and_unsorted(tmp_path: Path) -> None:
    # Use a temp cwd DB.
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
                "2026-01-10",
                "2026/01/10",
                "booked",
                -1000,
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
        tx_id = int(conn.execute("SELECT id FROM transactions WHERE fingerprint='fp1'").fetchone()[0])

        db.update_transaction_state(conn, transaction_id=tx_id, category=None, ignored=True)
        conn.commit()
        row = conn.execute(
            "SELECT category, ignored FROM transactions WHERE id=?",
            (tx_id,),
        ).fetchone()
        assert row[0] is None
        assert int(row[1]) == 1

        db.update_transaction_state(conn, transaction_id=tx_id, category="unsorted", ignored=False)
        conn.commit()
        row = conn.execute(
            "SELECT category, ignored FROM transactions WHERE id=?",
            (tx_id,),
        ).fetchone()
        assert row[0] == "unsorted"
        assert int(row[1]) == 0
    finally:
        conn.close()
