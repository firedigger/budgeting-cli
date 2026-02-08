from __future__ import annotations

import hashlib


def fingerprint_fields(*fields: str) -> str:
    joined = "\u001f".join(fields)
    return hashlib.sha256(joined.encode("utf-8", errors="replace")).hexdigest()
