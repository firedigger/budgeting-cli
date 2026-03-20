from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import typer
from rich.table import Table

from budgeting_cli import db
from budgeting_cli.ui import console, format_eur


report_app = typer.Typer(add_completion=False, no_args_is_help=True)


@dataclass(frozen=True)
class MonthRange:
    start: date
    end: date


def _month_range(yyyy_mm: str) -> MonthRange:
    try:
        year_str, month_str = yyyy_mm.split("-", 1)
        y = int(year_str)
        m = int(month_str)
    except Exception as e:
        raise typer.BadParameter("Expected --month in YYYY-MM format") from e

    if not (1 <= m <= 12):
        raise typer.BadParameter("Month must be 1..12")

    start = date(y, m, 1)
    if m == 12:
        end = date(y + 1, 1, 1)
    else:
        end = date(y, m + 1, 1)
    # end is exclusive
    return MonthRange(start=start, end=end)


def _shift_month(d: date, month_delta: int) -> date:
    month_index = (d.year * 12 + (d.month - 1)) + month_delta
    year = month_index // 12
    month = (month_index % 12) + 1
    return date(year, month, 1)


def get_expense_totals_by_category(
    conn, *, start: Optional[date], end: Optional[date]
) -> dict[str, int]:
    """Return expense totals by category.

    Values are signed cents (typically negative) as stored in the DB.
    Categories are always present: shared/alex/luiza/unsorted.
    """

    if start is None or end is None:
        rows = conn.execute(
            """
            SELECT COALESCE(category, 'unsorted') AS category, SUM(amount_cents) AS total_cents
            FROM transactions
            WHERE amount_cents < 0
              AND ignored=0
            GROUP BY COALESCE(category, 'unsorted')
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT COALESCE(category, 'unsorted') AS category, SUM(amount_cents) AS total_cents
            FROM transactions
            WHERE booking_date >= ? AND booking_date < ?
              AND amount_cents < 0
              AND ignored=0
            GROUP BY COALESCE(category, 'unsorted')
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()

    totals = {row["category"]: int(row["total_cents"] or 0) for row in rows}
    for cat in ("shared", "alex", "luiza", "unsorted"):
        totals.setdefault(cat, 0)
    return totals


def get_monthly_expense_totals_by_category(
    conn,
    *,
    months: int,
    today: Optional[date] = None,
) -> list[tuple[str, dict[str, int]]]:
    if months <= 0:
        raise ValueError("months must be positive")

    today = today or date.today()
    current_month = date(today.year, today.month, 1)
    start = _shift_month(current_month, -(months - 1))
    end = _shift_month(current_month, 1)

    rows = conn.execute(
        """
        SELECT substr(booking_date, 1, 7) AS month,
               COALESCE(category, 'unsorted') AS category,
               SUM(amount_cents) AS total_cents
        FROM transactions
        WHERE booking_date >= ? AND booking_date < ?
          AND amount_cents < 0
          AND ignored=0
        GROUP BY substr(booking_date, 1, 7), COALESCE(category, 'unsorted')
        ORDER BY month ASC
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()

    totals_by_month: dict[str, dict[str, int]] = {}
    for row in rows:
        month = str(row["month"])
        category = str(row["category"])
        month_totals = totals_by_month.setdefault(month, {})
        month_totals[category] = int(row["total_cents"] or 0)

    result: list[tuple[str, dict[str, int]]] = []
    for offset in range(months):
        month_start = _shift_month(start, offset)
        month_label = month_start.strftime("%Y-%m")
        totals = totals_by_month.get(month_label, {})
        normalized = {cat: totals.get(cat, 0) for cat in ("shared", "alex", "luiza", "unsorted")}
        result.append((month_label, normalized))
    return result


def filter_zero_total_months(
    rows: list[tuple[str, dict[str, int]]],
) -> list[tuple[str, dict[str, int]]]:
    filtered: list[tuple[str, dict[str, int]]] = []
    for month, totals in rows:
        total = sum(abs(value) for value in totals.values())
        if total > 0:
            filtered.append((month, totals))
    return filtered


def run_report_range(*, title: str, start: Optional[date], end: Optional[date]) -> Table:
    """Report spend by category.

    - start/end are inclusive/exclusive (>= start, < end)
    - if start/end are None, reports across all time
    """

    conn = db.connect()
    try:
        totals = get_expense_totals_by_category(conn, start=start, end=end)

        ordered = sorted(totals.items(), key=lambda kv: abs(kv[1]), reverse=True)
        total_spend_cents = sum(abs(v) for v in totals.values())

        table = Table(title=title)
        table.add_column("Category")
        table.add_column("Spend", justify="right")
        table.add_column("Pct", justify="right")

        for cat, total_cents in ordered:
            spend_cents = abs(total_cents)
            if total_spend_cents > 0:
                pct = (spend_cents / total_spend_cents) * 100
                pct_str = f"{pct:.1f}%"
            else:
                pct_str = "—"
            table.add_row(cat, format_eur(spend_cents), pct_str)

        console.print(table)
        return table
    finally:
        conn.close()


def run_report_month(month: str) -> Table:
    r = _month_range(month)
    return run_report_range(
        title=f"Expenses by category ({month})",
        start=r.start,
        end=r.end,
    )


def run_report_monthly_breakdown(*, months: int = 12, today: Optional[date] = None) -> Table:
    conn = db.connect()
    try:
        rows = get_monthly_expense_totals_by_category(conn, months=months, today=today)
        rows = filter_zero_total_months(rows)

        table = Table(title=f"Monthly expenses by category (past {months} months)")
        table.add_column("Month")
        table.add_column("Shared", justify="right")
        table.add_column("Alex", justify="right")
        table.add_column("Luiza", justify="right")
        table.add_column("Unsorted", justify="right")
        table.add_column("Total", justify="right")

        if not rows:
            console.print(f"No expenses in the past {months} months.")
            return table

        for month, totals in rows:
            shared = abs(totals["shared"])
            alex = abs(totals["alex"])
            luiza = abs(totals["luiza"])
            unsorted = abs(totals["unsorted"])
            total = shared + alex + luiza + unsorted
            table.add_row(
                month,
                format_eur(shared),
                format_eur(alex),
                format_eur(luiza),
                format_eur(unsorted),
                format_eur(total),
            )

        console.print(table)
        return table
    finally:
        conn.close()


@report_app.callback(invoke_without_command=True)
def report_month(month: str = typer.Option(..., "--month")) -> None:
    """Show expenses-only distribution by category for a month."""
    run_report_month(month)
