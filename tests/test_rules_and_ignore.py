from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from budgeting_cli.commands import import_cmd
from budgeting_cli.commands.report_cmd import get_expense_totals_by_category
from budgeting_cli.ui import CategorizeChoice


def _write_nordea_csv(path: Path, rows: list[dict[str, str]]) -> None:
    headers = [
        "Booking date",
        "Amount",
        "Sender",
        "Recipient",
        "Name",
        "Title",
        "Message",
        "Reference number",
        "Balance",
        "Currency",
    ]

    lines = [";".join(headers) + ";\n"]
    for r in rows:
        line = ";".join(
            [
                r.get("Booking date", ""),
                r.get("Amount", ""),
                r.get("Sender", ""),
                r.get("Recipient", ""),
                r.get("Name", ""),
                r.get("Title", ""),
                r.get("Message", ""),
                r.get("Reference number", ""),
                r.get("Balance", ""),
                r.get("Currency", "EUR"),
            ]
        )
        lines.append(line + ";\n")

    path.write_text("".join(lines), encoding="utf-8")


def _fetch_all(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT booking_date, amount_cents, vendor_key, category, ignored FROM transactions ORDER BY booking_date, amount_cents"
    ).fetchall()


def test_vendor_rule_applies_to_future_transactions_without_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    csv1 = tmp_path / "one.csv"
    _write_nordea_csv(
        csv1,
        [
            {
                "Booking date": "2026/01/10",
                "Amount": "-10,00",
                "Sender": "A",
                "Recipient": "B",
                "Name": "Netflix",
                "Title": "Netflix",
                "Message": "m1",
                "Reference number": "ref1",
                "Balance": "0",
                "Currency": "EUR",
            }
        ],
    )

    monkeypatch.setattr(
        import_cmd,
        "prompt_category_one_question",
        lambda: CategorizeChoice("shared", "vendor"),
    )
    import_cmd.run_import(csv1)

    # Second import: same vendor, different amount should be categorized on insert from vendor rule.
    csv2 = tmp_path / "two.csv"
    _write_nordea_csv(
        csv2,
        [
            {
                "Booking date": "2026/01/11",
                "Amount": "-20,00",
                "Sender": "A",
                "Recipient": "B",
                "Name": "Netflix",
                "Title": "Netflix",
                "Message": "m2",
                "Reference number": "ref2",
                "Balance": "0",
                "Currency": "EUR",
            }
        ],
    )

    def _should_not_prompt():
        raise AssertionError("prompt should not be called when vendor rule applies")

    monkeypatch.setattr(import_cmd, "prompt_category_one_question", _should_not_prompt)
    import_cmd.run_import(csv2)

    conn = sqlite3.connect(tmp_path / "budgeting.sqlite")
    conn.row_factory = sqlite3.Row
    try:
        rows = _fetch_all(conn)
        assert len(rows) == 2
        assert all(r["category"] == "shared" for r in rows)
        assert all(r["ignored"] == 0 for r in rows)
    finally:
        conn.close()


def test_vendor_amount_rule_only_matches_same_amount(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    csv1 = tmp_path / "seed.csv"
    _write_nordea_csv(
        csv1,
        [
            {
                "Booking date": "2026/01/10",
                "Amount": "-9,99",
                "Sender": "A",
                "Recipient": "B",
                "Name": "Spotify",
                "Title": "Spotify",
                "Message": "m1",
                "Reference number": "ref1",
                "Balance": "0",
                "Currency": "EUR",
            }
        ],
    )

    monkeypatch.setattr(
        import_cmd,
        "prompt_category_one_question",
        lambda: CategorizeChoice("alex", "vendor_amount"),
    )
    import_cmd.run_import(csv1)

    csv2 = tmp_path / "next.csv"
    _write_nordea_csv(
        csv2,
        [
            {
                "Booking date": "2026/01/11",
                "Amount": "-9,99",
                "Sender": "A",
                "Recipient": "B",
                "Name": "Spotify",
                "Title": "Spotify",
                "Message": "m2",
                "Reference number": "ref2",
                "Balance": "0",
                "Currency": "EUR",
            },
            {
                "Booking date": "2026/01/12",
                "Amount": "-12,00",
                "Sender": "A",
                "Recipient": "B",
                "Name": "Spotify",
                "Title": "Spotify",
                "Message": "m3",
                "Reference number": "ref3",
                "Balance": "0",
                "Currency": "EUR",
            },
        ],
    )

    prompt_calls = {"n": 0}

    def _prompt_once_then_category() -> CategorizeChoice:
        prompt_calls["n"] += 1
        return CategorizeChoice("luiza", "none")

    monkeypatch.setattr(import_cmd, "prompt_category_one_question", _prompt_once_then_category)
    import_cmd.run_import(csv2)

    assert prompt_calls["n"] == 1, "Only the different amount should require prompting"

    conn = sqlite3.connect(tmp_path / "budgeting.sqlite")
    conn.row_factory = sqlite3.Row
    try:
        rows = _fetch_all(conn)
        # Seed: alex (-9.99), next: alex (-9.99) auto, and luiza (-12.00) prompted
        assert len(rows) == 3
        alex_rows = [r for r in rows if r["category"] == "alex"]
        luiza_rows = [r for r in rows if r["category"] == "luiza"]
        assert len(alex_rows) == 2
        assert len(luiza_rows) == 1
    finally:
        conn.close()


def test_ignore_vendor_rule_auto_ignores_future_and_excludes_from_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    csv1 = tmp_path / "seed_ignore.csv"
    _write_nordea_csv(
        csv1,
        [
            {
                "Booking date": "2026/01/10",
                "Amount": "-5,00",
                "Sender": "A",
                "Recipient": "B",
                "Name": "Wolt",
                "Title": "Wolt",
                "Message": "m1",
                "Reference number": "ref1",
                "Balance": "0",
                "Currency": "EUR",
            }
        ],
    )

    monkeypatch.setattr(
        import_cmd,
        "prompt_category_one_question",
        lambda: CategorizeChoice(None, "none", skip=True, remember_ignore_vendor=True),
    )
    import_cmd.run_import(csv1)

    csv2 = tmp_path / "future_ignore.csv"
    _write_nordea_csv(
        csv2,
        [
            {
                "Booking date": "2026/01/11",
                "Amount": "-6,00",
                "Sender": "A",
                "Recipient": "B",
                "Name": "Wolt",
                "Title": "Wolt",
                "Message": "m2",
                "Reference number": "ref2",
                "Balance": "0",
                "Currency": "EUR",
            }
        ],
    )

    def _should_not_prompt():
        raise AssertionError("prompt should not be called for auto-ignored vendor")

    monkeypatch.setattr(import_cmd, "prompt_category_one_question", _should_not_prompt)
    import_cmd.run_import(csv2)

    conn = sqlite3.connect(tmp_path / "budgeting.sqlite")
    conn.row_factory = sqlite3.Row
    try:
        rows = _fetch_all(conn)
        assert len(rows) == 2
        assert all(r["ignored"] == 1 for r in rows)

        totals = get_expense_totals_by_category(conn, start=None, end=None)
        # Ignored transactions must not contribute to any category totals.
        assert totals == {"shared": 0, "alex": 0, "luiza": 0, "unsorted": 0}
    finally:
        conn.close()
