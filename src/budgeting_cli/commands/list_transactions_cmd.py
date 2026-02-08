from __future__ import annotations

from datetime import date
from typing import Optional

import sqlite3
from rich.table import Table

from budgeting_cli import db
from budgeting_cli.ui import console, format_eur


def _status_expr() -> str:
    # Status shown to the user. "skip" means ignored in reports.
    return "CASE WHEN ignored=1 THEN 'skip' ELSE COALESCE(category, 'unsorted') END"


def fetch_transactions(
    conn: sqlite3.Connection,
    *,
    category: str | None,
    start: Optional[date],
    end: Optional[date],
    search_text: str | None,
) -> list[sqlite3.Row]:
    params: list[str] = []

    where = ["amount_cents < 0"]
    if start is not None and end is not None:
        where.append("booking_date >= ? AND booking_date < ?")
        params.append(start.isoformat())
        params.append(end.isoformat())

    if category is not None:
        where.append(f"{_status_expr()} = ?")
        params.append(category)

    if search_text is not None:
        q = search_text.strip().casefold()
        if q:
            like = f"%{q}%"
            where.append(
                "(" + " OR ".join(
                    [
                        "vendor_key LIKE ?",
                        "LOWER(COALESCE(name,'')) LIKE ?",
                        "LOWER(COALESCE(title,'')) LIKE ?",
                        "LOWER(COALESCE(message,'')) LIKE ?",
                        "LOWER(COALESCE(reference_number,'')) LIKE ?",
                    ]
                ) + ")"
            )
            params.extend([like, like, like, like, like])

    where_sql = " AND ".join(where)

    return conn.execute(
        f"""
        SELECT id, booking_date, status, amount_cents, currency, vendor_key, name, title, message, reference_number,
               {_status_expr()} AS status_label
        FROM transactions
        WHERE {where_sql}
        ORDER BY ABS(amount_cents) DESC, booking_date DESC, id DESC
        """,
        params,
    ).fetchall()


def run_list_transactions_range(
    *,
    category: str | None,
    title: str,
    start: Optional[date],
    end: Optional[date],
    search_text: str | None = None,
) -> Table:
    """List transactions (expenses-only) biggest to smallest.

    - category=None means all categories
    - start/end are inclusive/exclusive (>= start, < end)
    - if start/end are None, lists across all time
    """

    conn = db.connect()
    try:
        rows = fetch_transactions(
            conn,
            category=category,
            start=start,
            end=end,
            search_text=search_text,
        )

        table = Table(title=f"{title} ({len(rows)} tx)")
        table.add_column("Date", no_wrap=True)
        table.add_column("Status", no_wrap=True)
        table.add_column("Spend", justify="right", no_wrap=True)
        table.add_column("Vendor")
        table.add_column("Title")

        for r in rows:
            vendor_key = str(r["vendor_key"] or "")
            name = str(r["name"] or "")
            tx_title = str(r["title"] or "")
            shown_title = name or tx_title
            if not shown_title:
                shown_title = str(r["message"] or "")

            table.add_row(
                str(r["booking_date"]),
                str(r["status_label"]),
                format_eur(abs(int(r["amount_cents"]))),
                vendor_key,
                shown_title,
            )

        console.print(table)
        return table
    finally:
        conn.close()
