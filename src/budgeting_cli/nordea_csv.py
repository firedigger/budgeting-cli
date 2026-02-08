from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from budgeting_cli.fingerprint import fingerprint_fields
from budgeting_cli.text_norm import normalize_vendor_key


@dataclass(frozen=True)
class NordeaRow:
    booking_date: date
    booking_date_raw: str
    status: str  # 'booked' | 'reserved'

    amount_cents: int
    currency: str

    sender: str
    recipient: str
    name: str
    title: str
    message: str
    reference_number: str
    balance: str

    vendor_key: str
    fingerprint: str


_EXPECTED_HEADERS = [
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


def _parse_booking_date(raw: str, import_day: date) -> tuple[date, str, str]:
    raw_stripped = raw.strip()
    if raw_stripped.casefold() == "reserved":
        return import_day, "Reserved", "reserved"
    parsed = datetime.strptime(raw_stripped, "%Y/%m/%d").date()
    return parsed, raw_stripped, "booked"


def _clean_row(values: list[str]) -> list[str]:
    if values and values[-1] == "":
        values = values[:-1]
    return values


def read_nordea_rows(csv_path: Path, *, import_day: date | None = None) -> list[NordeaRow]:
    import_day = date.today() if import_day is None else import_day

    with _open_text(csv_path) as f:
        reader = csv.reader(f, delimiter=";")
        try:
            raw_headers = next(reader)
        except StopIteration:
            return []

        headers = [h.strip() for h in _clean_row(raw_headers)]
        if headers[: len(_EXPECTED_HEADERS)] != _EXPECTED_HEADERS:
            raise ValueError(
                "Unexpected CSV headers. Expected Nordea export with columns: "
                + ", ".join(_EXPECTED_HEADERS)
            )

        rows: list[NordeaRow] = []
        for raw_values in reader:
            values = _clean_row(raw_values)
            if not values or all(v.strip() == "" for v in values):
                continue
            if len(values) < len(_EXPECTED_HEADERS):
                values = values + ([""] * (len(_EXPECTED_HEADERS) - len(values)))

            (
                booking_date_raw,
                amount,
                sender,
                recipient,
                name,
                title,
                message,
                reference_number,
                balance,
                currency,
            ) = (values + ([""] * 10))[:10]

            booking_date, booking_date_raw_norm, status = _parse_booking_date(booking_date_raw, import_day)
            amount_cents = _parse_amount_to_cents(amount)

            sender = sender.strip()
            recipient = recipient.strip()
            name = name.strip()
            title = title.strip()
            message = message.strip()
            reference_number = reference_number.strip()
            balance = balance.strip()
            currency = currency.strip() or "EUR"

            vendor_source = name or title or recipient or sender or "(unknown)"
            vendor_key = normalize_vendor_key(vendor_source)

            fp = fingerprint_fields(
                booking_date_raw_norm,
                str(amount_cents),
                currency,
                sender,
                recipient,
                name,
                title,
                message,
                reference_number,
            )

            rows.append(
                NordeaRow(
                    booking_date=booking_date,
                    booking_date_raw=booking_date_raw_norm,
                    status=status,
                    amount_cents=amount_cents,
                    currency=currency,
                    sender=sender,
                    recipient=recipient,
                    name=name,
                    title=title,
                    message=message,
                    reference_number=reference_number,
                    balance=balance,
                    vendor_key=vendor_key,
                    fingerprint=fp,
                )
            )

        return rows
