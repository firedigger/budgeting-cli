from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import questionary
from questionary import Choice
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


console = Console()


def format_eur(cents: int) -> str:
    euros = cents / 100
    return f"{euros:,.2f} EUR".replace(",", " ")


def clear_screen() -> None:
    console.clear()


@dataclass(frozen=True)
class CategorizeChoice:
    category: str | None
    remember_mode: str  # 'none' | 'vendor' | 'vendor_amount'
    stop: bool = False
    skip: bool = False
    defer_unsorted: bool = False
    remember_ignore_vendor: bool = False


def prompt_category_one_question() -> CategorizeChoice:
    choices = [
        Choice(
            "Shared (remember vendor)",
            value=CategorizeChoice("shared", "vendor"),
        ),
        Choice(
            "Shared (remember vendor + amount)",
            value=CategorizeChoice("shared", "vendor_amount"),
        ),
        Choice(
            "Shared (ask next time)",
            value=CategorizeChoice("shared", "none"),
        ),
        Choice(
            "Alex (remember vendor)",
            value=CategorizeChoice("alex", "vendor"),
        ),
        Choice(
            "Alex (remember vendor + amount)",
            value=CategorizeChoice("alex", "vendor_amount"),
        ),
        Choice(
            "Alex (ask next time)",
            value=CategorizeChoice("alex", "none"),
        ),
        Choice(
            "Luiza (remember vendor)",
            value=CategorizeChoice("luiza", "vendor"),
        ),
        Choice(
            "Luiza (remember vendor + amount)",
            value=CategorizeChoice("luiza", "vendor_amount"),
        ),
        Choice(
            "Luiza (ask next time)",
            value=CategorizeChoice("luiza", "none"),
        ),
        Choice(
            "Skip this transaction (ignore in reports)",
            value=CategorizeChoice(None, "none", skip=True),
        ),
        Choice(
            "Skip this transaction (ignore in reports) + remember vendor",
            value=CategorizeChoice(None, "none", skip=True, remember_ignore_vendor=True),
        ),
        Choice(
            "Skip for now (move to unsorted, keep going)",
            value=CategorizeChoice(None, "none", defer_unsorted=True),
        ),
        Choice(
            "Back to menu / stop now (rest -> unsorted)",
            value=CategorizeChoice(None, "none", stop=True),
        ),
    ]
    return questionary.select(
        "Pick category + remember?",
        choices=choices,
        use_shortcuts=True,
    ).ask()


def render_transaction_panel(*, booking_date: date, status: str, amount_cents: int, currency: str, name: str, title: str, message: str, reference_number: str) -> None:
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_row("Date", f"{booking_date.isoformat()} ({status})")
    table.add_row("Amount", f"{format_eur(abs(amount_cents))} ({currency})")
    if name:
        table.add_row("Name", name)
    if title and title != name:
        table.add_row("Title", title)
    if message:
        table.add_row("Message", message)
    if reference_number:
        table.add_row("Ref", reference_number)

    console.print(Panel.fit(table, title="Transaction", border_style="cyan"))
