from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import tomllib


CONFIG_FILE_NAME = "budgeting.toml"


@dataclass(frozen=True)
class IncomeConfig:
    alex_monthly_cents: int = 0
    luiza_monthly_cents: int = 0


def _eur_to_cents(value: object, *, key: str) -> int:
    try:
        euros = Decimal(str(value))
    except (InvalidOperation, ValueError) as e:
        raise ValueError(f"{key} must be a EUR amount, for example 3000.00") from e

    cents = (euros * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def load_income_config(config_path: Path | None = None) -> IncomeConfig:
    path = config_path or Path.cwd() / CONFIG_FILE_NAME
    if not path.exists():
        return IncomeConfig()

    with path.open("rb") as f:
        raw = tomllib.load(f)

    income = raw.get("income", {})
    if not isinstance(income, dict):
        raise ValueError("[income] in budgeting.toml must be a table")

    return IncomeConfig(
        alex_monthly_cents=_eur_to_cents(income.get("alex_monthly_eur", 0), key="alex_monthly_eur"),
        luiza_monthly_cents=_eur_to_cents(income.get("luiza_monthly_eur", 0), key="luiza_monthly_eur"),
    )
