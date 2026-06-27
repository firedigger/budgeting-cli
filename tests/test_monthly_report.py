from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from budgeting_cli import db
from budgeting_cli.commands.report_cmd import (
    _monthly_income_factor,
    _title_with_effective_period,
    calculate_personal_balances,
    filter_zero_total_months,
    get_monthly_expense_totals_by_category,
    run_report_range,
    run_report_monthly_breakdown,
)
from budgeting_cli.config import IncomeConfig, load_income_config


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


def test_load_income_config_reads_budgeting_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "budgeting.toml"
    config_path.write_text(
        """
        [income]
        alex_monthly_eur = 3100.50
        luiza_monthly_eur = 2900
        """,
        encoding="utf-8",
    )

    income = load_income_config(config_path)

    assert income == IncomeConfig(alex_monthly_cents=310050, luiza_monthly_cents=290000)


def test_personal_balances_split_shared_expenses_and_subtract_personal_expenses() -> None:
    totals = {
        "shared": -100000,
        "alex": -20000,
        "luiza": -30000,
        "unsorted": -99999,
    }
    income = IncomeConfig(alex_monthly_cents=300000, luiza_monthly_cents=250000)

    alex, luiza = calculate_personal_balances(totals, income)

    assert alex.name == "Alex"
    assert alex.income_cents == Decimal("300000")
    assert alex.expense_share_cents == Decimal("70000")
    assert alex.balance_cents == Decimal("230000")
    assert alex.only_own_balance_cents == Decimal("280000")
    assert luiza.name == "Luiza"
    assert luiza.income_cents == Decimal("250000")
    assert luiza.expense_share_cents == Decimal("80000")
    assert luiza.balance_cents == Decimal("170000")
    assert luiza.only_own_balance_cents == Decimal("220000")


def test_monthly_income_factor_prorates_by_days_across_months() -> None:
    factor = _monthly_income_factor(date(2026, 1, 16), date(2026, 2, 16))

    assert factor == Decimal(16) / Decimal(31) + Decimal(15) / Decimal(28)


def test_run_report_monthly_breakdown_adds_personal_balance_columns(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "budgeting.toml").write_text(
        """
        [income]
        alex_monthly_eur = "1000.00"
        luiza_monthly_eur = "900.00"
        """,
        encoding="utf-8",
    )
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
                "fp-balance",
                "2026-03-05",
                "2026/03/05",
                "booked",
                -10000,
                "EUR",
                "A",
                "B",
                "Vendor",
                "Vendor",
                "m",
                "ref",
                "0",
                "vendor-balance",
                "shared",
                0,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    table = run_report_monthly_breakdown(months=1, today=date(2026, 3, 21))

    assert [column.header for column in table.columns][-4:] == [
        "Alex balance",
        "Alex only own",
        "Luiza balance",
        "Luiza only own",
    ]
    assert table.columns[-4]._cells == ["950.00 EUR"]
    assert table.columns[-3]._cells == ["1 000.00 EUR"]
    assert table.columns[-2]._cells == ["850.00 EUR"]
    assert table.columns[-1]._cells == ["900.00 EUR"]


def test_run_report_range_uses_ingested_transaction_span_for_weighted_income(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "budgeting.toml").write_text(
        """
        [income]
        alex_monthly_eur = 1000.00
        luiza_monthly_eur = 900.00
        """,
        encoding="utf-8",
    )
    conn = db.connect()
    try:
        rows = [
            ("fp-shared", "2026-01-16", -10000, "shared"),
            ("fp-alex", "2026-02-15", -2000, "alex"),
            ("fp-luiza", "2026-02-15", -3000, "luiza"),
        ]
        for fingerprint, booking_date, amount_cents, category in rows:
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
                    fingerprint,
                    booking_date,
                    booking_date.replace("-", "/"),
                    "booked",
                    amount_cents,
                    "EUR",
                    "A",
                    "B",
                    "Vendor",
                    "Vendor",
                    "m",
                    "ref",
                    "0",
                    fingerprint,
                    category,
                    0,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    table = run_report_range(
        title="Expenses by category (2026)",
        start=date(2026, 1, 1),
        end=date(2027, 1, 1),
        effective_period_unit="month",
    )

    assert table.title == "Expenses by category (2026-01..2026-02)"
    assert [column.header for column in table.columns] == [
        "Category",
        "Spend",
        "Pct",
        "Income",
        "Balance",
        "Only own",
    ]
    row_by_category = {
        category: (income, balance, only_own)
        for category, income, balance, only_own in zip(
            table.columns[0]._cells,
            table.columns[3]._cells,
            table.columns[4]._cells,
            table.columns[5]._cells,
        )
    }
    assert row_by_category["shared"] == ("—", "—", "—")
    assert row_by_category["alex"] == ("1 051.84 EUR", "981.84 EUR", "1 031.84 EUR")
    assert row_by_category["luiza"] == ("946.66 EUR", "866.66 EUR", "916.66 EUR")


def test_effective_period_title_can_use_dates_for_week_or_month_reports() -> None:
    title = _title_with_effective_period(
        "Expenses by category (2026-01)",
        start=date(2026, 1, 1),
        end=date(2026, 2, 1),
        bounds=(date(2026, 1, 16), date(2026, 1, 21)),
        unit="day",
    )

    assert title == "Expenses by category (2026-01-16..2026-01-20)"
