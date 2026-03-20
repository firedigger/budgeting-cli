from __future__ import annotations

from pathlib import Path

from budgeting_cli import db


def test_get_most_recent_booking_date(tmp_path: Path) -> None:
    import os

    os.chdir(tmp_path)
    conn = db.connect()
    try:
        assert db.get_most_recent_booking_date(conn) is None

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
                "fp2",
                "2026-02-03",
                "2026/02/03",
                "booked",
                -2000,
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

        assert db.get_most_recent_booking_date(conn) == "2026-02-03"
    finally:
        conn.close()
