from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, DecimalException
from pathlib import Path
from typing import Any

CENT_FACTOR = Decimal("100")


def format_currency(value: float | Decimal | str | int) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",") + " €"


def money_to_cents(raw: object) -> int:
    try:
        value = Decimal(str(raw))
        if not value.is_finite():
            raise ValueError("Valor monetário inválido")
        cents = (value * CENT_FACTOR).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if abs(cents) > 9_223_372_036_854_775_807:
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
