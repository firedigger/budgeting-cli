from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from budgeting_cli.commands import import_cmd
from budgeting_cli.entrydate_csv import read_entrydate_rows
from budgeting_cli.ui import CategorizeChoice


def _write_entrydate_csv(path: Path, rows: list[dict[str, str]]) -> None:
    headers = [
        "EntryDate",
        "ValueDate",
        "Amount EUR",
        "Code",
        "Description",
        "Recipient/Payer",
        "Recipient account number",
        "Recipient Bank",
        "Reference",
        "Message",
        "Filing id",
    ]

    lines = ['"' + '";"'.join(headers) + '"\n']
    for row in rows:
        values = [row.get(h, "") for h in headers]
        lines.append('"' + '";"'.join(values) + '"\n')

    path.write_text("".join(lines), encoding="utf-8")


def _db_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            """
            SELECT booking_date, amount_cents, currency, name, title, message,
                   reference_number, vendor_key, category, ignored
            FROM transactions
            ORDER BY booking_date, amount_cents
            """
        ).fetchall()
    finally:
        conn.close()


def test_entrydate_import_expenses_only_and_reimport_dedupes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    csv_path = tmp_path / "entrydate.csv"
    _write_entrydate_csv(
        csv_path,
        [
            {
                "EntryDate": "2026-04-30",
                "ValueDate": "2026-04-30",
                "Amount EUR": "4031,01",
                "Code": "506",
                "Description": "BANK TRANSFER",
                "Recipient/Payer": "Nexetic Oy",
                "Reference": "ref=",
                "Message": "Message: Palkka",
                "Filing id": "20260428/5UTH01/326693",
            },
            {
                "EntryDate": "2026-05-04",
                "ValueDate": "2026-05-04",
                "Amount EUR": "-1,99",
                "Code": "162",
                "Description": "CARD PAYMENT",
                "Recipient/Payer": "Karkkitori Sello    Porvoo",
                "Reference": "ref=",
                "Message": "Message: 401046******5437 OSTOPVM 260502MF",
                "Filing id": "20260504/5EQEO6/289191",
            },
            {
                "EntryDate": "2026-05-01",
                "ValueDate": "2026-05-01",
                "Amount EUR": "-400,00",
                "Code": "163",
                "Description": "ATM WITHDRAWAL",
                "Reference": "ref=",
                "Filing id": "20260501/094054/240005",
            },
        ],
    )

    monkeypatch.setattr(
        import_cmd,
        "prompt_category_one_question",
        lambda: CategorizeChoice(None, "none", stop=True),
    )

    import_cmd.run_import(csv_path)
    rows1 = _db_rows(tmp_path / "budgeting.sqlite")

    assert len(rows1) == 2
    assert [r["amount_cents"] for r in rows1] == [-40000, -199]
    assert [r["category"] for r in rows1] == ["unsorted", "unsorted"]
    assert rows1[0]["vendor_key"] == "atm withdrawal"
    assert rows1[1]["vendor_key"] == "karkkitori sello porvoo"
    assert rows1[1]["message"] == "401046******5437 OSTOPVM 260502MF"
    assert rows1[1]["reference_number"] == "20260504/5EQEO6/289191"

    import_cmd.run_import(csv_path)
    rows2 = _db_rows(tmp_path / "budgeting.sqlite")

    assert [dict(r) for r in rows2] == [dict(r) for r in rows1]


def test_entrydate_fingerprint_distinguishes_same_atm_amounts(tmp_path: Path) -> None:
    csv_path = tmp_path / "entrydate.csv"
    _write_entrydate_csv(
        csv_path,
        [
            {
                "EntryDate": "2026-05-01",
                "ValueDate": "2026-05-01",
                "Amount EUR": "-400,00",
                "Code": "163",
                "Description": "ATM WITHDRAWAL",
                "Reference": "ref=",
                "Filing id": "20260501/094054/240005",
            },
            {
                "EntryDate": "2026-05-01",
                "ValueDate": "2026-05-01",
                "Amount EUR": "-400,00",
                "Code": "163",
                "Description": "ATM WITHDRAWAL",
                "Reference": "ref=",
                "Filing id": "20260501/094054/240006",
            },
        ],
    )

    rows = read_entrydate_rows(csv_path)

    assert len(rows) == 2
    assert rows[0].fingerprint != rows[1].fingerprint
