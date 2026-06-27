from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import typer
from rich.table import Table

from budgeting_cli.config import IncomeConfig, load_income_config
from budgeting_cli import db
from budgeting_cli.ui import console, format_eur


report_app = typer.Typer(add_completion=False, no_args_is_help=True)


@dataclass(frozen=True)
class MonthRange:
    start: date
    end: date


@dataclass(frozen=True)
class PersonalBalance:
    name: str
    income_cents: Decimal
    expense_share_cents: Decimal
    balance_cents: Decimal
    only_own_balance_cents: Decimal


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


def _format_eur_decimal(cents: Decimal | int) -> str:
    euros = (Decimal(cents) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{euros:,.2f} EUR".replace(",", " ")


def _monthly_income_factor(start: date, end: date) -> Decimal:
    if start >= end:
        return Decimal("0")

    factor = Decimal("0")
    month_start = date(start.year, start.month, 1)
    while month_start < end:
        month_end = _shift_month(month_start, 1)
        overlap_start = max(start, month_start)
        overlap_end = min(end, month_end)
        if overlap_start < overlap_end:
            overlap_days = (overlap_end - overlap_start).days
            month_days = (month_end - month_start).days
            factor += Decimal(overlap_days) / Decimal(month_days)
        month_start = month_end
    return factor


def _date_bounds_for_report(
    conn, *, start: Optional[date], end: Optional[date]
) -> tuple[date, date] | None:
    where = "WHERE amount_cents < 0 AND ignored=0"
    params: tuple[str, ...] = ()
    if start is not None and end is not None:
        where += " AND booking_date >= ? AND booking_date < ?"
        params = (start.isoformat(), end.isoformat())

    row = conn.execute(
        f"""
        SELECT MIN(booking_date) AS first_date,
               MAX(booking_date) AS last_date
        FROM transactions
        {where}
        """,
        params,
    ).fetchone()
    if not row or row["first_date"] is None or row["last_date"] is None:
        return None
    first = date.fromisoformat(str(row["first_date"]))
    last_exclusive = date.fromisoformat(str(row["last_date"])) + timedelta(days=1)
    return first, last_exclusive


def _effective_period_label(bounds: tuple[date, date], *, unit: str) -> str:
    first, last_exclusive = bounds
    last_inclusive = last_exclusive - timedelta(days=1)
    if unit == "month":
        first_label = first.strftime("%Y-%m")
        last_label = last_inclusive.strftime("%Y-%m")
    else:
        first_label = first.isoformat()
        last_label = last_inclusive.isoformat()

    if first_label == last_label:
        return first_label
    return f"{first_label}..{last_label}"


def _title_with_effective_period(
    title: str,
    *,
    start: Optional[date],
    end: Optional[date],
    bounds: tuple[date, date] | None,
    unit: str | None,
) -> str:
    if unit is None or bounds is None or start is None or end is None:
        return title
    if bounds == (start, end):
        return title

    label = _effective_period_label(bounds, unit=unit)
    if "(" in title and title.endswith(")"):
        prefix = title[: title.rfind("(")].rstrip()
        return f"{prefix} ({label})"
    return f"{title} ({label})"


def calculate_personal_balances(
    totals: dict[str, int],
    income: IncomeConfig,
    *,
    income_factor: Decimal = Decimal("1"),
) -> list[PersonalBalance]:
    shared_half_cents = Decimal(abs(totals["shared"])) / Decimal("2")
    alex_own_expense_cents = Decimal(abs(totals["alex"]))
    luiza_own_expense_cents = Decimal(abs(totals["luiza"]))
    alex_expense_share_cents = alex_own_expense_cents + shared_half_cents
    luiza_expense_share_cents = luiza_own_expense_cents + shared_half_cents
    alex_income_cents = Decimal(income.alex_monthly_cents) * income_factor
    luiza_income_cents = Decimal(income.luiza_monthly_cents) * income_factor

    return [
        PersonalBalance(
            name="Alex",
            income_cents=alex_income_cents,
            expense_share_cents=alex_expense_share_cents,
            balance_cents=alex_income_cents - alex_expense_share_cents,
            only_own_balance_cents=alex_income_cents - alex_own_expense_cents,
        ),
        PersonalBalance(
            name="Luiza",
            income_cents=luiza_income_cents,
            expense_share_cents=luiza_expense_share_cents,
            balance_cents=luiza_income_cents - luiza_expense_share_cents,
            only_own_balance_cents=luiza_income_cents - luiza_own_expense_cents,
        ),
    ]


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


def run_report_range(
    *,
    title: str,
    start: Optional[date],
    end: Optional[date],
    effective_period_unit: str | None = None,
) -> Table:
    """Report spend by category.

    - start/end are inclusive/exclusive (>= start, < end)
    - if start/end are None, reports across all time
    """

    conn = db.connect()
    try:
        income = load_income_config()
        totals = get_expense_totals_by_category(conn, start=start, end=end)

        ordered = sorted(totals.items(), key=lambda kv: abs(kv[1]), reverse=True)
        total_spend_cents = sum(abs(v) for v in totals.values())
        bounds = _date_bounds_for_report(conn, start=start, end=end)
        shown_title = _title_with_effective_period(
            title,
            start=start,
            end=end,
            bounds=bounds,
            unit=effective_period_unit,
        )

        table = Table(title=shown_title)
        table.add_column("Category")
        table.add_column("Spend", justify="right")
        table.add_column("Pct", justify="right")
        table.add_column("Income", justify="right")
        table.add_column("Balance", justify="right")
        table.add_column("Only own", justify="right")

        income_factor = (
            _monthly_income_factor(bounds[0], bounds[1])
            if bounds is not None
            else Decimal("0")
        )
        balances = {
            row.name.lower(): row
            for row in calculate_personal_balances(totals, income, income_factor=income_factor)
        }

        for cat, total_cents in ordered:
            spend_cents = abs(total_cents)
            if total_spend_cents > 0:
                pct = (spend_cents / total_spend_cents) * 100
                pct_str = f"{pct:.1f}%"
            else:
                pct_str = "—"
            balance = balances.get(cat)
            income_str = _format_eur_decimal(balance.income_cents) if balance else "—"
            balance_str = _format_eur_decimal(balance.balance_cents) if balance else "—"
            only_own_str = _format_eur_decimal(balance.only_own_balance_cents) if balance else "—"
            table.add_row(cat, format_eur(spend_cents), pct_str, income_str, balance_str, only_own_str)

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
        effective_period_unit="day",
    )


def run_report_monthly_breakdown(*, months: int = 12, today: Optional[date] = None) -> Table:
    conn = db.connect()
    try:
        income = load_income_config()
        rows = get_monthly_expense_totals_by_category(conn, months=months, today=today)
        rows = filter_zero_total_months(rows)

        table = Table(title=f"Monthly expenses by category (past {months} months)")
        table.add_column("Month")
        table.add_column("Shared", justify="right")
        table.add_column("Alex", justify="right")
        table.add_column("Luiza", justify="right")
        table.add_column("Unsorted", justify="right")
        table.add_column("Total", justify="right")
        table.add_column("Alex balance", justify="right")
        table.add_column("Alex only own", justify="right")
        table.add_column("Luiza balance", justify="right")
        table.add_column("Luiza only own", justify="right")

        if not rows:
            console.print(f"No expenses in the past {months} months.")
            return table

        for month, totals in rows:
            shared = abs(totals["shared"])
            alex = abs(totals["alex"])
            luiza = abs(totals["luiza"])
            unsorted = abs(totals["unsorted"])
            total = shared + alex + luiza + unsorted
            alex_balance, luiza_balance = calculate_personal_balances(totals, income)
            table.add_row(
                month,
                format_eur(shared),
                format_eur(alex),
                format_eur(luiza),
                format_eur(unsorted),
                format_eur(total),
                _format_eur_decimal(alex_balance.balance_cents),
                _format_eur_decimal(alex_balance.only_own_balance_cents),
                _format_eur_decimal(luiza_balance.balance_cents),
                _format_eur_decimal(luiza_balance.only_own_balance_cents),
            )

        console.print(table)
        return table
    finally:
        conn.close()


@report_app.callback(invoke_without_command=True)
def report_month(month: str = typer.Option(..., "--month")) -> None:
    """Show expenses-only distribution by category for a month."""
    run_report_month(month)
