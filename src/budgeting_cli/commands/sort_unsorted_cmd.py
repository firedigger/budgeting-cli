from __future__ import annotations

from datetime import date

import typer

from budgeting_cli import db
from budgeting_cli.ui import clear_screen, console, prompt_category_one_question, render_transaction_panel


sort_unsorted_app = typer.Typer(add_completion=False, no_args_is_help=True)


def run_sort_unsorted() -> None:
    conn = db.connect()
    try:
        vendor_rules = db.load_vendor_rules(conn)
        vendor_amount_rules = db.load_vendor_amount_rules(conn)
        ignore_vendor_rules = db.load_ignore_vendor_rules(conn)

        rows = conn.execute(
            """
            SELECT id, booking_date, status, amount_cents, currency, name, title, message, reference_number, vendor_key
            FROM transactions
            WHERE category='unsorted' AND ignored=0
            ORDER BY (amount_cents < 0) DESC, ABS(amount_cents) DESC
            """
        ).fetchall()

        if not rows:
            console.print("No unsorted transactions.")
            return

        remaining_ids = [int(r["id"]) for r in rows]

        for row in rows:
            tx_id = int(row["id"])
            vendor_key = str(row["vendor_key"])
            amount_cents = int(row["amount_cents"])
            currency = str(row["currency"])

            if vendor_key in ignore_vendor_rules:
                db.set_ignored(conn, tx_id, True)
                conn.commit()
                remaining_ids.remove(tx_id)
                continue

            amount_rule = vendor_amount_rules.get((vendor_key, amount_cents, currency))
            if amount_rule is not None:
                db.set_category(conn, tx_id, amount_rule.category)
                conn.commit()
                remaining_ids.remove(tx_id)
                continue

            rule = vendor_rules.get(vendor_key)
            if rule is not None:
                db.set_category(conn, tx_id, rule.category)
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
                console.print(f"Stopped. Left {len(remaining_ids)} unsorted.")
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
                # Already unsorted; keep it there but continue.
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
    finally:
        conn.close()


@sort_unsorted_app.callback(invoke_without_command=True)
def sort_unsorted() -> None:
    """Play the sorting game over saved unsorted transactions."""
    run_sort_unsorted()
