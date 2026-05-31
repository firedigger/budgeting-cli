from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ImportedRow:
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
