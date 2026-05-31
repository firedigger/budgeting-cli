from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from budgeting_cli.fingerprint import fingerprint_fields
from budgeting_cli.imported_row import ImportedRow
from budgeting_cli.text_norm import normalize_vendor_key


EXPECTED_HEADERS = [
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


def _open_text(path: Path):
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return path.open("r", encoding=enc, newline="")
        except UnicodeDecodeError:
            continue
    return path.open("r", encoding="utf-8", errors="replace", newline="")


def _parse_amount_to_cents(value: str) -> int:
    s = value.strip().replace(" ", "")
    s = s.replace(",", ".")
    d = Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(d * 100)


def _parse_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def _amount_header_currency(header: str) -> str:
    parts = header.strip().split()
    return (parts[-1] if len(parts) > 1 else "EUR").upper()


def _clean_message(value: str) -> str:
    value = value.strip()
    prefix = "Message:"
    if value.casefold().startswith(prefix.casefold()):
        return value[len(prefix) :].strip()
    return value


def read_entrydate_rows(csv_path: Path, *, import_day: date | None = None) -> list[ImportedRow]:
    _ = import_day

    with _open_text(csv_path) as f:
        reader = csv.DictReader(f, delimiter=";")
        headers = [h.strip() for h in (reader.fieldnames or [])]
        if headers[: len(EXPECTED_HEADERS)] != EXPECTED_HEADERS:
            raise ValueError(
                "Unexpected CSV headers. Expected EntryDate export with columns: "
                + ", ".join(EXPECTED_HEADERS)
            )

        currency = _amount_header_currency(headers[2])
        rows: list[ImportedRow] = []
        for raw_row in reader:
            row = {str(k).strip(): (v or "").strip() for k, v in raw_row.items() if k is not None}
            if not row or all(v == "" for v in row.values()):
                continue

            entry_date_raw = row["EntryDate"]
            value_date_raw = row["ValueDate"]
            amount_raw = row["Amount EUR"]
            code = row["Code"]
            description = row["Description"]
            recipient_payer = row["Recipient/Payer"]
            recipient_account_number = row["Recipient account number"]
            recipient_bank = row["Recipient Bank"]
            reference = row["Reference"]
            message = _clean_message(row["Message"])
            filing_id = row["Filing id"]

            amount_cents = _parse_amount_to_cents(amount_raw)
            booking_date = _parse_date(entry_date_raw)

            vendor_source = recipient_payer or description or message or "(unknown)"
            vendor_key = normalize_vendor_key(vendor_source)

            fp = fingerprint_fields(
                "entrydate-v1",
                entry_date_raw,
                value_date_raw,
                str(amount_cents),
                currency,
                code,
                description,
                recipient_payer,
                recipient_account_number,
                recipient_bank,
                reference,
                message,
                filing_id,
            )

            rows.append(
                ImportedRow(
                    booking_date=booking_date,
                    booking_date_raw=entry_date_raw,
                    status="booked",
                    amount_cents=amount_cents,
                    currency=currency,
                    sender="",
                    recipient=recipient_payer,
                    name=recipient_payer,
                    title=description,
                    message=message,
                    reference_number=filing_id or reference,
                    balance="",
                    vendor_key=vendor_key,
                    fingerprint=fp,
                )
            )

        return rows
