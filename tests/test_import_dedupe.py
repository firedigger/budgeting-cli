from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from budgeting_cli.commands import import_cmd
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


def _db_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT id, fingerprint, booking_date, amount_cents, vendor_key, category, ignored FROM transactions ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


def test_reimport_same_file_no_effect_including_unsorted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    csv_path = tmp_path / "nordea.csv"
    _write_nordea_csv(
        csv_path,
        rows=[
            {
                "Booking date": "2026/01/10",
                "Amount": "-10,00",
                "Sender": "A",
                "Recipient": "B",
                "Name": "Vendor One",
                "Title": "Vendor One",
                "Message": "m1",
                "Reference number": "ref1",
                "Balance": "0",
                "Currency": "EUR",
            },
            {
                "Booking date": "2026/01/11",
                "Amount": "-20,00",
                "Sender": "A",
                "Recipient": "B",
                "Name": "Vendor Two",
                "Title": "Vendor Two",
                "Message": "m2",
                "Reference number": "ref2",
                "Balance": "0",
                "Currency": "EUR",
            },
        ],
    )

    # Stop immediately so everything imported this run becomes unsorted.
    monkeypatch.setattr(
        import_cmd,
        "prompt_category_one_question",
        lambda: CategorizeChoice(None, "none", stop=True),
    )

    import_cmd.run_import(csv_path)

    db_path = tmp_path / "budgeting.sqlite"
    rows1 = _db_rows(db_path)
    assert len(rows1) == 2
    assert all(r["category"] == "unsorted" for r in rows1)

    # Re-importing the same file should not insert anything new or change existing rows.
    import_cmd.run_import(csv_path)
    rows2 = _db_rows(db_path)
    assert [dict(r) for r in rows2] == [dict(r) for r in rows1]
