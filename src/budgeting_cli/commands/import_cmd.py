from __future__ import annotations

from datetime import date
from pathlib import Path

import sqlite3
import typer

from budgeting_cli import db
from budgeting_cli.nordea_csv import NordeaRow, read_nordea_rows
from budgeting_cli.ui import clear_screen, console, prompt_category_one_question, render_transaction_panel


import_app = typer.Typer(add_completion=False, no_args_is_help=True)


def _insert_rows(conn: sqlite3.Connection, rows: list[NordeaRow], vendor_rules: dict[str, db.VendorRule]) -> list[int]:
    inserted_ids: list[int] = []
    for r in rows:
        rule = vendor_rules.get(r.vendor_key)
        category = rule.category if rule else None
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO transactions(
                fingerprint, booking_date, booking_date_raw, status,
                amount_cents, currency,
                sender, recipient, name, title, message, reference_number, balance,
                vendor_key, category
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r.fingerprint,
                r.booking_date.isoformat(),
                r.booking_date_raw,
                r.status,
                r.amount_cents,
                r.currency,
                r.sender,
                r.recipient,
                r.name,
                r.title,
                r.message,
                r.reference_number,
                r.balance,
                r.vendor_key,
                category,
            ),
        )
        if cur.rowcount == 1:
            inserted_ids.append(int(cur.lastrowid))
    return inserted_ids


def run_import(csv_path: Path) -> None:
    conn = db.connect()
    try:
        vendor_rules = db.load_vendor_rules(conn)
        vendor_amount_rules = db.load_vendor_amount_rules(conn)
        ignore_vendor_rules = db.load_ignore_vendor_rules(conn)
        rows = read_nordea_rows(csv_path, import_day=date.today())
        # Expenses-only: ignore income/refunds completely (do not store).
        rows = [r for r in rows if r.amount_cents < 0]

        inserted_ids: list[int] = []
        for r in rows:
            if r.vendor_key in ignore_vendor_rules:
                ignored = 1
                category = None
            else:
                ignored = 0
            amount_key = (r.vendor_key, r.amount_cents, r.currency)
            amount_rule = vendor_amount_rules.get(amount_key)
            vendor_rule = vendor_rules.get(r.vendor_key)
            if ignored == 0:
                category = (amount_rule.category if amount_rule else None) or (
                    vendor_rule.category if vendor_rule else None
                )

            cur = conn.execute(
                """
                INSERT OR IGNORE INTO transactions(
                    fingerprint, booking_date, booking_date_raw, status,
                    amount_cents, currency,
                    sender, recipient, name, title, message, reference_number, balance,
                    vendor_key, category, ignored
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r.fingerprint,
                    r.booking_date.isoformat(),
                    r.booking_date_raw,
                    r.status,
                    r.amount_cents,
                    r.currency,
                    r.sender,
                    r.recipient,
                    r.name,
                    r.title,
                    r.message,
                    r.reference_number,
                    r.balance,
                    r.vendor_key,
                    category,
                    ignored,
                ),
            )
            if cur.rowcount == 1:
                inserted_ids.append(int(cur.lastrowid))
        conn.commit()

        if not inserted_ids:
            console.print("No new transactions.")
            return

        console.print(f"Imported {len(inserted_ids)} new transactions.")

        # Only prompt for new, uncategorized rows.
        placeholders = ",".join(["?"] * len(inserted_ids))
        to_sort = conn.execute(
            f"""
            SELECT id, booking_date, status, amount_cents, currency, name, title, message, reference_number, vendor_key
            FROM transactions
            WHERE id IN ({placeholders}) AND category IS NULL AND ignored=0
            ORDER BY (amount_cents < 0) DESC, ABS(amount_cents) DESC
            """,
            inserted_ids,
        ).fetchall()

        remaining_ids = [int(r["id"]) for r in to_sort]

        for row in to_sort:
            tx_id = int(row["id"])
            vendor_key = str(row["vendor_key"])
            amount_cents = int(row["amount_cents"])
            currency = str(row["currency"])

            # If a rule was added earlier in this run, apply it.
            amount_rule_key = (vendor_key, amount_cents, currency)
            if amount_rule_key in vendor_amount_rules:
                db.set_category(conn, tx_id, vendor_amount_rules[amount_rule_key].category)
                conn.commit()
                remaining_ids.remove(tx_id)
                continue

            if vendor_key in vendor_rules:
                db.set_category(conn, tx_id, vendor_rules[vendor_key].category)
                conn.commit()
                remaining_ids.remove(tx_id)
                continue

            clear_screen()
            render_transaction_panel(
                booking_date=date.fromisoformat(str(row["booking_date"])),
                status=str(row["status"]),
                amount_cents=int(row["amount_cents"]),
                currency=str(row["currency"]),
                name=str(row["name"] or ""),
                title=str(row["title"] or ""),
                message=str(row["message"] or ""),
                reference_number=str(row["reference_number"] or ""),
            )

            choice = prompt_category_one_question()
            if choice is None:
                raise typer.Abort()

            if choice.stop:
                db.mark_unsorted(conn, remaining_ids)
                conn.commit()
                console.print(f"Stopped. Marked {len(remaining_ids)} as unsorted.")
                return

            if choice.skip:
                db.set_ignored(conn, tx_id, True)
                if choice.remember_ignore_vendor:
                    db.upsert_ignore_vendor_rule(conn, vendor_key)
                    ignore_vendor_rules.add(vendor_key)
                conn.commit()
                remaining_ids.remove(tx_id)
                continue

            if choice.defer_unsorted:
                db.set_category(conn, tx_id, "unsorted")
                conn.commit()
                remaining_ids.remove(tx_id)
                continue

            assert choice.category in ("shared", "alex", "luiza")
            db.set_category(conn, tx_id, choice.category)

            if choice.remember_mode == "vendor":
                db.upsert_vendor_rule(conn, vendor_key, choice.category)
                vendor_rules[vendor_key] = db.VendorRule(vendor_key=vendor_key, category=choice.category)
            elif choice.remember_mode == "vendor_amount":
                db.upsert_vendor_amount_rule(conn, vendor_key, amount_cents, currency, choice.category)
                vendor_amount_rules[(vendor_key, amount_cents, currency)] = db.VendorAmountRule(
                    vendor_key=vendor_key,
                    amount_cents=amount_cents,
                    currency=currency,
                    category=choice.category,
                )

            conn.commit()
            remaining_ids.remove(tx_id)

        console.print("Done.")

        # Backup the DB after a successful import run.
        # (No backup on early exit / abort, since the run didn't fully complete.)
        try:
            db.backup_database(conn)
        except Exception as e:  # noqa: BLE001
            console.print(f"[yellow]Warning: could not create DB backup: {e}[/yellow]")
    finally:
        conn.close()


@import_app.callback(invoke_without_command=True)
def import_csv(csv_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True)) -> None:
    """Import a Nordea CSV export and categorize new transactions."""
    run_import(csv_path)
