from __future__ import annotations

from datetime import date
from pathlib import Path

from budgeting_cli.nordea_csv import read_nordea_rows


def _write_reserved_csv(path: Path) -> None:
    path.write_text(
        "".join(
            [
                "Booking date;Amount;Sender;Recipient;Name;Title;Message;Reference number;Balance;Currency;\n",
                "Reserved;-1,00;A;B;Vendor;Vendor;msg;ref;0;EUR;\n",
            ]
        ),
        encoding="utf-8",
    )


def test_reserved_row_fingerprint_is_stable_across_import_day(tmp_path: Path) -> None:
    csv_path = tmp_path / "reserved.csv"
    _write_reserved_csv(csv_path)

    rows_day1 = read_nordea_rows(csv_path, import_day=date(2026, 2, 1))
    rows_day2 = read_nordea_rows(csv_path, import_day=date(2026, 2, 6))

    assert len(rows_day1) == 1
    assert len(rows_day2) == 1

    assert rows_day1[0].fingerprint == rows_day2[0].fingerprint
    # booking_date will differ (it is set to import_day for Reserved), but fingerprint must not.
    assert rows_day1[0].booking_date != rows_day2[0].booking_date
