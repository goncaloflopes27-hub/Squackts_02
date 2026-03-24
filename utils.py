from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

CENT_FACTOR = Decimal("100")


def configure_logging(log_file_path: Path) -> None:
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.FileHandler(log_file_path, encoding="utf-8"), logging.StreamHandler()],
        force=True,
    )


def format_currency(value: float | Decimal | str | int) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"€{amount:,.2f}".replace(",", " ")


def money_to_cents(raw: object) -> int:
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise ValueError("Valor monetário inválido") from exc
    cents = (value * CENT_FACTOR).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def cents_to_money(cents: int | str | float) -> Decimal:
    return (Decimal(int(cents)) / CENT_FACTOR).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_dirs(paths: tuple[Path, ...]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def to_json(payload: dict[str, Any] | None) -> str:
    return json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":"))
