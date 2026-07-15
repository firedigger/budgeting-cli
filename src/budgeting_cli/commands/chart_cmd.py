from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional

import typer

from budgeting_cli import db
from budgeting_cli.config import IncomeConfig, load_income_config


chart_app = typer.Typer(add_completion=False, no_args_is_help=True)
CHARTS_DIR_NAME = "charts"


@dataclass(frozen=True)
class MonthRange:
    start: date
    end: date


@dataclass(frozen=True)
class TotalChartData:
    month: str
    previous_month: str
    days_in_month: int
    days_in_previous_month: int
    current_cents: tuple[Decimal, ...]
    previous_cents: tuple[Decimal, ...]
    monthly_income_cents: Decimal


def _shift_month(month_start: date, delta: int) -> date:
    index = month_start.year * 12 + month_start.month - 1 + delta
    return date(index // 12, index % 12 + 1, 1)


def _month_range(month: str) -> MonthRange:
    try:
        year_text, month_text = month.split("-", 1)
        start = date(int(year_text), int(month_text), 1)
    except (TypeError, ValueError) as exc:
        raise ValueError("Month must use YYYY-MM format") from exc
    return MonthRange(start=start, end=_shift_month(start, 1))


def _daily_total_spending(
    conn,
    *,
    start: date,
    end: date,
) -> dict[date, Decimal]:
    rows = conn.execute(
        """
        SELECT booking_date, SUM(ABS(amount_cents)) AS spend_cents
        FROM transactions
        WHERE booking_date >= ? AND booking_date < ?
          AND amount_cents < 0
          AND ignored=0
        GROUP BY booking_date
        ORDER BY booking_date
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    return {
        date.fromisoformat(str(row["booking_date"])): Decimal(
            int(row["spend_cents"] or 0)
        )
        for row in rows
    }


def _has_reportable_transactions(
    conn,
    *,
    start: date,
    end: date,
) -> bool:
    row = conn.execute(
        """
        SELECT EXISTS(
            SELECT 1
            FROM transactions
            WHERE booking_date >= ? AND booking_date < ?
              AND amount_cents < 0
              AND ignored=0
        ) AS found
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchone()
    return bool(row["found"])


def _cumulative_daily(
    daily: dict[date, Decimal],
    *,
    start: date,
    days: int,
) -> tuple[Decimal, ...]:
    total = Decimal("0")
    values: list[Decimal] = []
    for offset in range(days):
        total += daily.get(start + timedelta(days=offset), Decimal("0"))
        values.append(total)
    return tuple(values)


def build_total_chart_data(
    conn,
    *,
    month: str,
    income: IncomeConfig,
    today: date | None = None,
) -> TotalChartData:
    selected = _month_range(month)
    previous_start = _shift_month(selected.start, -1)
    previous = MonthRange(start=previous_start, end=selected.start)
    today = today or date.today()

    if not _has_reportable_transactions(
        conn,
        start=selected.start,
        end=selected.end,
    ):
        latest = db.get_most_recent_booking_date(conn)
        suffix = f" Latest transaction in the database: {latest}." if latest else ""
        raise ValueError(
            f"No reportable transactions found for {month}.{suffix}"
        )

    days = (selected.end - selected.start).days
    previous_days = (previous.end - previous.start).days
    if today < selected.start:
        visible_days = 0
    elif today >= selected.end:
        visible_days = days
    else:
        visible_days = today.day

    current = _cumulative_daily(
        _daily_total_spending(conn, start=selected.start, end=selected.end),
        start=selected.start,
        days=days,
    )
    previous_values = _cumulative_daily(
        _daily_total_spending(conn, start=previous.start, end=previous.end),
        start=previous.start,
        days=previous_days,
    )
    return TotalChartData(
        month=month,
        previous_month=previous.start.strftime("%Y-%m"),
        days_in_month=days,
        days_in_previous_month=previous_days,
        current_cents=current[:visible_days],
        previous_cents=previous_values,
        monthly_income_cents=Decimal(
            income.alex_monthly_cents + income.luiza_monthly_cents
        ),
    )


def _month_label(month: str) -> str:
    return _month_range(month).start.strftime("%B %Y")


def _render_total_chart(data: TotalChartData, output_path: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.ticker import FuncFormatter, MaxNLocator
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Chart generation requires matplotlib. Run: python -m pip install -r requirements.txt"
        ) from exc

    figure, axis = plt.subplots(figsize=(10, 6), dpi=150)

    current_days = range(1, len(data.current_cents) + 1)
    previous_days = range(1, len(data.previous_cents) + 1)

    axis.plot(
        current_days,
        [float(value / 100) for value in data.current_cents],
        marker="o",
        markersize=3,
        linewidth=2,
        label=_month_label(data.month),
    )
    axis.plot(
        previous_days,
        [float(value / 100) for value in data.previous_cents],
        marker="o",
        markersize=3,
        linewidth=2,
        color="0.6",
        label=_month_label(data.previous_month),
    )
    axis.axhline(
        y=float(data.monthly_income_cents / 100),
        color="tab:green",
        linestyle="--",
        linewidth=2,
        label="Total monthly income",
    )

    axis.set_title(f"Total cumulative expenses — {_month_label(data.month)}")
    axis.set_xlabel("Day of month")
    axis.set_ylabel("Cumulative spending (EUR)")
    axis.set_xlim(1, max(data.days_in_month, data.days_in_previous_month))
    axis.set_ylim(bottom=0)
    axis.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=16))
    axis.yaxis.set_major_formatter(
        FuncFormatter(lambda value, _position: f"{value:,.0f} EUR")
    )
    axis.grid(True, alpha=0.3)
    axis.legend()

    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path)
    plt.close(figure)


def generate_month_chart(
    month: str,
    *,
    output_dir: Path | None = None,
    today: date | None = None,
) -> Path:
    _month_range(month)
    conn = db.connect()
    try:
        data = build_total_chart_data(
            conn,
            month=month,
            income=load_income_config(),
            today=today,
        )
    finally:
        conn.close()

    directory = output_dir or Path.cwd() / CHARTS_DIR_NAME
    output_path = directory / f"total-spending-{month}.png"
    _render_total_chart(data, output_path)
    return output_path.resolve()


@chart_app.callback(invoke_without_command=True)
def chart_month(
    month: str = typer.Option(..., "--month", help="Month in YYYY-MM format"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir"),
) -> None:
    """Generate a plain Matplotlib chart for total monthly expenses."""

    try:
        path = generate_month_chart(month, output_dir=output_dir)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(path)
