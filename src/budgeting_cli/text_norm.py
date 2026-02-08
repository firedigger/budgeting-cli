from __future__ import annotations

import re


_whitespace_re = re.compile(r"\s+")


def normalize_vendor_key(value: str) -> str:
    value = value.strip().casefold()
    value = _whitespace_re.sub(" ", value)
    return value
