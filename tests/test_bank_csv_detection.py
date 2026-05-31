from __future__ import annotations

from pathlib import Path

import pytest

from budgeting_cli.bank_csv import detect_provider


def test_detects_nordea_headers(tmp_path: Path) -> None:
    csv_path = tmp_path / "nordea.csv"
    csv_path.write_text(
        "Booking date;Amount;Sender;Recipient;Name;Title;Message;Reference number;Balance;Currency;\n",
        encoding="utf-8",
    )

    assert detect_provider(csv_path) == "nordea"


def test_detects_entrydate_headers(tmp_path: Path) -> None:
    csv_path = tmp_path / "entrydate.csv"
    csv_path.write_text(
        '"EntryDate";"ValueDate";"Amount EUR";"Code";"Description";"Recipient/Payer";'
        '"Recipient account number";"Recipient Bank";"Reference";"Message";"Filing id"\n',
        encoding="utf-8",
    )

    assert detect_provider(csv_path) == "entrydate"


def test_unknown_headers_are_reported(tmp_path: Path) -> None:
    csv_path = tmp_path / "unknown.csv"
    csv_path.write_text("Date;Value;Thing\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unknown CSV format"):
        detect_provider(csv_path)
