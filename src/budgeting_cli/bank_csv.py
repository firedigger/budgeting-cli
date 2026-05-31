from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Literal

from budgeting_cli.entrydate_csv import EXPECTED_HEADERS as ENTRYDATE_HEADERS
from budgeting_cli.entrydate_csv import read_entrydate_rows
from budgeting_cli.imported_row import ImportedRow
from budgeting_cli.nordea_csv import _EXPECTED_HEADERS as NORDEA_HEADERS
from budgeting_cli.nordea_csv import read_nordea_rows


BankProvider = Literal["nordea", "entrydate"]


def _open_text(path: Path):
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return path.open("r", encoding=enc, newline="")
        except UnicodeDecodeError:
            continue
    return path.open("r", encoding="utf-8", errors="replace", newline="")


def read_headers(csv_path: Path) -> list[str]:
    with _open_text(csv_path) as f:
        reader = csv.reader(f, delimiter=";")
        try:
            raw_headers = next(reader)
        except StopIteration:
            return []
    if raw_headers and raw_headers[-1] == "":
        raw_headers = raw_headers[:-1]
    return [h.strip() for h in raw_headers]


def detect_provider(csv_path: Path) -> BankProvider:
    headers = read_headers(csv_path)
    if headers[: len(NORDEA_HEADERS)] == NORDEA_HEADERS:
        return "nordea"
    if headers[: len(ENTRYDATE_HEADERS)] == ENTRYDATE_HEADERS:
        return "entrydate"

    shown = ", ".join(headers) if headers else "(empty file)"
    raise ValueError(f"Unknown CSV format. Headers found: {shown}")


def read_bank_rows(csv_path: Path, *, import_day: date | None = None) -> list[ImportedRow]:
    provider = detect_provider(csv_path)
    if provider == "nordea":
        return read_nordea_rows(csv_path, import_day=import_day)
    if provider == "entrydate":
        return read_entrydate_rows(csv_path, import_day=import_day)

    raise AssertionError(f"Unhandled bank provider: {provider}")
