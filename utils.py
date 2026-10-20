from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, DecimalException
from pathlib import Path
from typing import Any

CENT_FACTOR = Decimal("100")
MAX_SQLITE_INTEGER = 9_223_372_036_854_775_807
MAX_ITEM_QUANTITY = 999_999


def checked_cents(value: int) -> int:
    if not 0 <= value <= MAX_SQLITE_INTEGER:
        raise ValueError("O total monetário excede o limite suportado")
    return value


def item_quantity(raw: object) -> int:
    try:
        value = Decimal(str(raw))
        if not value.is_finite() or value != value.to_integral_value() or not 1 <= value <= MAX_ITEM_QUANTITY:
            raise ValueError(f"A quantidade deve ser um inteiro entre 1 e {MAX_ITEM_QUANTITY}")
        return int(value)
    except DecimalException as exc:
        raise ValueError("Quantidade inválida") from exc


def format_currency(value: float | Decimal | str | int) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",") + " €"


def money_to_cents(raw: object) -> int:
    try:
        value = Decimal(str(raw))
        if not value.is_finite():
            raise ValueError("Valor monetário inválido")
        cents = (value * CENT_FACTOR).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if abs(cents) > MAX_SQLITE_INTEGER:
            raise ValueError("Valor monetário fora do limite suportado")
        return int(cents)
    except DecimalException as exc:
        raise ValueError("Valor monetário inválido") from exc


def cents_to_money(cents: int | str | float) -> Decimal:
    return (Decimal(int(cents)) / CENT_FACTOR).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_dirs(paths: tuple[Path, ...]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def to_json(payload: dict[str, Any] | None) -> str:
    return json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":"))
