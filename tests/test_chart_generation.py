from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from budgeting_cli import db
from budgeting_cli.commands.chart_cmd import (
    build_total_chart_data,
    generate_month_chart,
)
from budgeting_cli.config import IncomeConfig


def _insert(
    conn,
    fingerprint: str,
    booking_date: str,
    amount_cents: int,
    category: str,
) -> None:
    conn.execute(
        """
        INSERT INTO transactions(
          fingerprint, booking_date, booking_date_raw, status,
          amount_cents, currency, vendor_key, category, ignored
        ) VALUES (?, ?, ?, 'booked', ?, 'EUR', ?, ?, 0)
        """,
        (
            fingerprint,
            booking_date,
            booking_date.replace("-", "/"),
            amount_cents,
            fingerprint,
            category,
        ),
    )


def test_total_chart_uses_all_expense_categories_and_daily_cumulative_values() -> None:
    conn = db.connect(Path(":memory:"))
    try:
        _insert(conn, "april-alex", "2026-04-02", -4000, "alex")
        _insert(conn, "may-alex-1", "2026-05-01", -1000, "alex")
        _insert(conn, "may-shared", "2026-05-08", -9000, "shared")
        _insert(conn, "may-alex-2", "2026-05-10", -2000, "alex")
        conn.commit()

        data = build_total_chart_data(
            conn,
            month="2026-05",
            income=IncomeConfig(
                # Deliberately synthetic fixture values, not user data.
                alex_monthly_cents=11100,
                luiza_monthly_cents=22200,
            ),
            today=date(2026, 7, 16),
        )
    finally:
        conn.close()

    assert data.previous_month == "2026-04"
    assert len(data.current_cents) == 31
    assert len(data.previous_cents) == 30
    assert data.current_cents[0] == Decimal("1000")
    assert data.current_cents[7] == Decimal("10000")
    assert data.current_cents[9] == Decimal("12000")
    assert data.current_cents[-1] == Decimal("12000")
    assert data.previous_cents[-1] == Decimal("4000")
    assert data.monthly_income_cents == Decimal("33300")


def test_empty_selected_month_reports_latest_database_date() -> None:
    conn = db.connect(Path(":memory:"))
    try:
        _insert(conn, "may-alex", "2026-05-31", -1000, "alex")
        conn.commit()

        with pytest.raises(ValueError) as exc_info:
            build_total_chart_data(
                conn,
                month="2026-06",
                income=IncomeConfig(),
                today=date(2026, 7, 16),
            )
    finally:
        conn.close()

    assert str(exc_info.value) == (
        "No reportable transactions found for 2026-06. "
        "Latest transaction in the database: 2026-05-31."
    )


def test_generate_month_chart_writes_plain_total_png(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "budgeting.toml").write_text(
        """
        [income]
        # Deliberately synthetic fixture values, not user data.
        alex_monthly_eur = 111
        luiza_monthly_eur = 222
        """,
        encoding="utf-8",
    )
    conn = db.connect()
    try:
        _insert(conn, "april", "2026-04-12", -18000, "alex")
        _insert(conn, "may-1", "2026-05-03", -4500, "alex")
        _insert(conn, "may-2", "2026-05-11", -12500, "alex")
        conn.commit()
    finally:
        conn.close()

    output = generate_month_chart(
        "2026-05",
        output_dir=tmp_path / "charts",
        today=date(2026, 7, 16),
    )

    assert output == (tmp_path / "charts" / "total-spending-2026-05.png").resolve()
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert output.stat().st_size > 50_000
