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


@report_app.callback(invoke_without_command=True)
def report_month(month: str = typer.Option(..., "--month")) -> None:
    """Show expenses-only distribution by category for a month."""
    run_report_month(month)
