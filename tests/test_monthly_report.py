from __future__ import annotations

from datetime import date
from pathlib import Path

from budgeting_cli import db
from budgeting_cli.commands.report_cmd import filter_zero_total_months, get_monthly_expense_totals_by_category


def test_get_monthly_expense_totals_by_category_returns_last_12_months(tmp_path: Path) -> None:
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
                "2025-06-10",
                "2025/06/10",
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
                "vendor-a",
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
                "2026-03-05",
                "2026/03/05",
                "booked",
                -2500,
                "EUR",
                "A",
                "B",
                "Vendor",
                "Vendor",
                "m",
                "ref",
                "0",
                "vendor-b",
                "alex",
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
                "fp3",
                "2026-03-15",
                "2026/03/15",
                "booked",
                -700,
                "EUR",
                "A",
                "B",
                "Vendor",
                "Vendor",
                "m",
                "ref",
                "0",
                "vendor-c",
                None,
                0,
            ),
        )
        conn.commit()

        rows = get_monthly_expense_totals_by_category(conn, months=12, today=date(2026, 3, 21))

        assert len(rows) == 12
        assert rows[0][0] == "2025-04"
        assert rows[-1][0] == "2026-03"

        june_totals = dict(rows)["2025-06"]
        assert june_totals == {
            "shared": -1000,
            "alex": 0,
            "luiza": 0,
            "unsorted": 0,
        }

        march_totals = dict(rows)["2026-03"]
        assert march_totals == {
            "shared": 0,
            "alex": -2500,
            "luiza": 0,
            "unsorted": -700,
        }
    finally:
        conn.close()


def test_filter_zero_total_months_omits_empty_months() -> None:
    rows = [
        (
            "2025-04",
            {"shared": 0, "alex": 0, "luiza": 0, "unsorted": 0},
        ),
        (
            "2025-05",
            {"shared": -1000, "alex": 0, "luiza": 0, "unsorted": 0},
        ),
        (
            "2025-06",
            {"shared": 0, "alex": 0, "luiza": 0, "unsorted": 0},
        ),
        (
            "2025-07",
            {"shared": 0, "alex": -500, "luiza": 0, "unsorted": -200},
        ),
    ]

    filtered = filter_zero_total_months(rows)

    assert filtered == [
        (
            "2025-05",
            {"shared": -1000, "alex": 0, "luiza": 0, "unsorted": 0},
        ),
        (
            "2025-07",
            {"shared": 0, "alex": -500, "luiza": 0, "unsorted": -200},
        ),
    ]