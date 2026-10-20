from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from sqlite3 import Row

from services.order_domain import VALID_STATES


@dataclass(frozen=True, slots=True)
class OrderQuery:
    """Bounded order search; dates are inclusive ISO calendar dates."""

    search: str = ""
    state: str = "todas"
    paid: int | None = None
    date_from: str = ""
    date_to: str = ""
    limit: int = 100
    offset: int = 0
    client_id: int | None = None

    def __post_init__(self) -> None:
        validate_page(self.limit, self.offset)
        if self.state != "todas" and self.state not in VALID_STATES:
            raise ValueError("Estado inválido")
        if self.paid not in (None, 0, 1):
            raise ValueError("Filtro de pagamento inválido")
        if self.client_id is not None and self.client_id <= 0:
            raise ValueError("Cliente inválido")
        for raw in (self.date_from, self.date_to):
            if raw:
                try:
                    parsed = date.fromisoformat(raw)
                except ValueError as exc:
                    raise ValueError("Data de filtro inválida; use AAAA-MM-DD") from exc
                if parsed.isoformat() != raw:
                    raise ValueError("Data de filtro inválida; use AAAA-MM-DD")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("A data inicial não pode ser posterior à data final")
        if self.date_to:
            try:
                date.fromisoformat(self.date_to) + timedelta(days=1)
            except OverflowError as exc:
                raise ValueError("Data final fora do intervalo suportado") from exc

    @property
    def date_to_exclusive(self) -> str:
        if not self.date_to:
            return ""
        return (date.fromisoformat(self.date_to) + timedelta(days=1)).isoformat()


@dataclass(frozen=True, slots=True)
class OrderPage:
    rows: list[Row]
    total: int


def validate_page(limit: int, offset: int) -> None:
    if not 1 <= limit <= 500:
        raise ValueError("O tamanho da página deve estar entre 1 e 500")
    if offset < 0:
        raise ValueError("A posição da página não pode ser negativa")
