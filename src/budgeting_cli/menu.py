from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import questionary
from rich.console import Console

from budgeting_cli import db
from budgeting_cli.commands.import_cmd import run_import
from budgeting_cli.commands.list_transactions_cmd import fetch_transactions, run_list_transactions_range
from budgeting_cli.commands.report_cmd import run_report_month, run_report_monthly_breakdown, run_report_range
from budgeting_cli.commands.reset_cmd import run_reset
from budgeting_cli.commands.sort_unsorted_cmd import run_sort_unsorted


console = Console()
IMPORTS_DIR_NAME = "imports"


def _pause_to_menu() -> None:
    questionary.text("Press Enter to return to menu", default="").ask()


def _imports_dir() -> Path:
    return Path.cwd() / IMPORTS_DIR_NAME


def _list_csv_files(csv_dir: Path) -> list[Path]:
    return sorted(
        [p for p in csv_dir.iterdir() if p.is_file() and p.suffix.lower() == ".csv"],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _pick_csv_from_imports() -> Path | None:
    csv_dir = _imports_dir()
    csv_dir.mkdir(parents=True, exist_ok=True)
    csv_files = _list_csv_files(csv_dir)
    if not csv_files:
        console.print(f"No CSV files found in `{csv_dir}`.")
        console.print(f"Put your bank export into `{csv_dir}` and try again.")
        return None

    selected = questionary.select(
        "Pick CSV to import:",
        choices=[
            questionary.Choice(
                title=f"{p.name}  ({date.fromtimestamp(p.stat().st_mtime).isoformat()})",
                value=p,
            )
            for p in csv_files
        ]
        + ["Back"],
        use_shortcuts=True,
        use_search_filter=True,
        use_jk_keys=False,
    ).ask()

    if selected is None or selected == "Back":
        return None
    return Path(selected)


def _unsorted_count() -> int:
    conn = db.connect()
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM transactions
            WHERE ignored=0 AND (category='unsorted' OR category IS NULL)
            """
        ).fetchone()
        return int(row["c"] or 0)
    finally:
        conn.close()


def _most_recent_booking_date() -> str | None:
    conn = db.connect()
    try:
        return db.get_most_recent_booking_date(conn)
    finally:
        conn.close()


def _default_month() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def _this_week_range(today: date) -> tuple[date, date]:
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=7)
    return start, end


def _this_month_range(today: date) -> tuple[date, date]:
    start = date(today.year, today.month, 1)
    if today.month == 12:
        end = date(today.year + 1, 1, 1)
    else:
        end = date(today.year, today.month + 1, 1)
    return start, end


def _this_year_range(today: date) -> tuple[date, date]:
    start = date(today.year, 1, 1)
    end = date(today.year + 1, 1, 1)
    return start, end


def _rolling_days_range(today: date, days: int) -> tuple[date, date]:
    end = today + timedelta(days=1)
    start = end - timedelta(days=days)
    return start, end


def _pick_period() -> tuple[str, date | None, date | None]:
    """Return (label, start, end). start/end are inclusive/exclusive, or (None, None) for all time."""
    today = date.today()
    while True:
        choice = questionary.select(
            "Period:",
            choices=[
                "Week",
                "Month",
                "Year",
                "All",
                "Past 7d",
                "Past 14d",
                "Past 30d",
                "Back",
            ],
            use_shortcuts=True,
        ).ask()

        if choice is None or choice == "Back":
            return "Back", None, None

        if choice == "Month":
            month = questionary.text(
                "Month (YYYY-MM):",
                default=_default_month(),
            ).ask()
            if not month:
                continue
            # We still want start/end for listing; re-derive from the same month string.
            from budgeting_cli.commands.report_cmd import _month_range

            mr = _month_range(month)
            return f"{month}", mr.start, mr.end

        if choice == "Week":
            start, end = _this_week_range(today)
            label = f"week {start.isoformat()}..{(end - timedelta(days=1)).isoformat()}"
            return label, start, end

        if choice == "Year":
            start, end = _this_year_range(today)
            return f"{start.year}", start, end

        if choice == "All":
            return "all time", None, None

        if choice == "Past 7d":
            start, end = _rolling_days_range(today, 7)
            return f"past 7 days ending {today.isoformat()}", start, end

        if choice == "Past 14d":
            start, end = _rolling_days_range(today, 14)
            return f"past 14 days ending {today.isoformat()}", start, end

        if choice == "Past 30d":
            start, end = _rolling_days_range(today, 30)
            return f"past 30 days ending {today.isoformat()}", start, end


def _run_report_menu() -> None:
    label, start, end = _pick_period()
    if label == "Back":
        return

    if label.count("-") == 1 and start is not None and end is not None:
        # Month chosen
        run_report_range(
            title=f"Expenses by category ({label})",
            start=start,
            end=end,
        )
        return

    if label == "all time":
        run_report_range(
            title="Expenses by category (all time)",
            start=None,
            end=None,
        )
        return

    run_report_range(
        title=f"Expenses by category ({label})",
        start=start,
        end=end,
    )
    return


def _run_transactions_menu() -> None:
    category_choice = questionary.select(
        "Category:",
        choices=[
            "Shared",
            "Alex",
            "Luiza",
            "Unsorted",
            "Skip (ignored)",
            "All categories",
            "Back",
        ],
        use_shortcuts=True,
    ).ask()

    if category_choice is None or category_choice == "Back":
        return

    cat: str | None
    if category_choice == "All categories":
        cat = None
    elif category_choice == "Shared":
        cat = "shared"
    elif category_choice == "Alex":
        cat = "alex"
    elif category_choice == "Luiza":
        cat = "luiza"
    elif category_choice == "Skip (ignored)":
        cat = "skip"
    else:
        cat = "unsorted"

    label, start, end = _pick_period()
    if label == "Back":
        return

    shown_cat = category_choice
    run_list_transactions_range(
        category=cat,
        title=f"Transactions ({shown_cat}, {label})",
        start=start,
        end=end,
        search_text=None,
    )

    edit_choice = questionary.select(
        "Edit mode?",
        choices=["No", "Yes"],
        use_shortcuts=True,
    ).ask()
    if edit_choice is None or edit_choice == "No":
        return

    conn = db.connect()
    try:
        rows = fetch_transactions(
            conn,
            category=cat,
            start=start,
            end=end,
            search_text=None,
        )
        if not rows:
            console.print("No matching transactions.")
            return

        tx_choice = questionary.select(
            "Pick transaction to edit:",
            choices=[
                questionary.Choice(
                    f"{r['booking_date']} | {abs(int(r['amount_cents']))/100:,.2f} {r['currency']} | {r['status_label']} | {r['vendor_key']}",
                    value=int(r["id"]),
                )
                for r in rows
            ],
            use_shortcuts=True,
            use_search_filter=True,
            use_jk_keys=False,
        ).ask()
        if tx_choice is None:
            return

        new_status = questionary.select(
            "Set new status:",
            choices=[
                "Shared",
                "Alex",
                "Luiza",
                "Unsorted",
                "Skip (ignore in reports)",
                "Cancel",
            ],
            use_shortcuts=True,
        ).ask()
        if new_status is None or new_status == "Cancel":
            return

        if new_status == "Skip (ignore in reports)":
            db.update_transaction_state(conn, transaction_id=int(tx_choice), category=None, ignored=True)
        elif new_status == "Unsorted":
            db.update_transaction_state(conn, transaction_id=int(tx_choice), category="unsorted", ignored=False)
        elif new_status == "Shared":
            db.update_transaction_state(conn, transaction_id=int(tx_choice), category="shared", ignored=False)
        elif new_status == "Alex":
            db.update_transaction_state(conn, transaction_id=int(tx_choice), category="alex", ignored=False)
        else:
            db.update_transaction_state(conn, transaction_id=int(tx_choice), category="luiza", ignored=False)

        conn.commit()
        console.print("Updated.")
    finally:
        conn.close()
    return


def run_menu() -> None:
    clear_before_menu = True
    while True:
        if clear_before_menu:
            console.clear()
        unsorted = _unsorted_count()
        most_recent = _most_recent_booking_date() or "—"
        choice = questionary.select(
            f"What do you want to do?\nMost recent recorded transaction date: {most_recent}",
            choices=[
                "Import new CSV",
                f"Sort unsorted ({unsorted})",
                "Report",
                "Monthly category table (past 12 months)",
                "Transactions (biggest -> smallest)",
                "Reset (wipe all data)",
                "Exit",
            ],
            use_shortcuts=True,
        ).ask()

        if choice is None or choice == "Exit":
            return

        if choice == "Import new CSV":
            csv_path = _pick_csv_from_imports()
            if csv_path is None:
                clear_before_menu = False
                continue
            run_import(csv_path)
            clear_before_menu = True
            continue

        if choice.startswith("Sort unsorted"):
            if unsorted == 0:
                console.print("No unsorted transactions.")
                _pause_to_menu()
                clear_before_menu = True
                continue
            run_sort_unsorted()
            clear_before_menu = True
            continue

        if choice == "Report":
            _run_report_menu()
            clear_before_menu = False
            continue

        if choice == "Monthly category table (past 12 months)":
            run_report_monthly_breakdown(months=12)
            _pause_to_menu()
            clear_before_menu = False
            continue

        if choice == "Transactions (biggest -> smallest)":
            _run_transactions_menu()
            _pause_to_menu()
            clear_before_menu = False
            continue

        if choice == "Reset (wipe all data)":
            run_reset(yes=False, db_path=None)
            _pause_to_menu()
            clear_before_menu = True
            continue
