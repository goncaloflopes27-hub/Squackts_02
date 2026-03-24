from __future__ import annotations

from repositories.orders import OrderRepository
from repositories.settings import SettingsRepository

PROD_PRINT_ON_DEMAND = "print_on_demand"
PROD_STOCK_FISICO = "stock_fisico"
PROD_MISTO = "misto"


def normalize_production_type(raw_value: str) -> str:
    value = raw_value.strip().lower()
    if value in {PROD_PRINT_ON_DEMAND, PROD_STOCK_FISICO, PROD_MISTO}:
        return value
    return PROD_PRINT_ON_DEMAND


def next_order_number(now: str, settings: SettingsRepository, orders: OrderRepository) -> str:
    year = now[:4]
    key = f"orders.sequence.{year}"
    seq_settings = settings.get_int(key, default=0)
    seq_db = orders.get_max_sequence_for_year(year)
    seq = max(seq_settings, seq_db) + 1
    settings.set_int(key, seq)
    return f"ENC-{year}-{seq:04d}"
