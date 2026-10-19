from __future__ import annotations

from sqlite3 import Connection, Row

from repositories.clients import ClientRepository
from repositories.logs import LogRepository
from repositories.orders import OrderRepository
from repositories.products import ProductRepository
from repositories.settings import SettingsRepository
from services.order_domain import FINAL_STATES, VALID_STATES
from services.order_queries import OrderPage, validate_page
from services.order_service import OrderService


class ProductionService:
    """Production presentation facade; every lifecycle write uses OrderService."""

    def __init__(
        self,
        conn: Connection,
        orders: OrderRepository,
        logs: LogRepository,
        order_service: OrderService | None = None,
    ) -> None:
        self.conn = conn
        self.orders = orders
        self.logs = logs
        self.order_service = order_service or OrderService(
            conn, orders, ProductRepository(conn), ClientRepository(conn), logs, SettingsRepository(conn)
        )

    def get_production_queue(self, status: str | None = None) -> list[Row]:
        return self.orders.get_queue(status)

    def search_queue(
        self,
        status: str = "todas",
        search: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> OrderPage:
        validate_page(limit, offset)
        if status != "todas" and status not in VALID_STATES:
            raise ValueError("Estado inválido")
        rows, total = self.orders.search_queue(status=status, search=search, limit=limit, offset=offset)
        return OrderPage(rows, total)

    def mark_producing(self, order_id: int) -> None:
        self._ensure_operational(order_id)
        self.order_service.start_production(order_id)

    def mark_produced(self, order_id: int) -> None:
        self._ensure_operational(order_id)
        self.order_service.mark_produced(order_id)

    def mark_ready_to_ship(self, order_id: int) -> None:
        """Compatibility name: this historical action dispatches the order."""
        self._ensure_operational(order_id)
        self.order_service.dispatch_order(order_id)

    def _ensure_operational(self, order_id: int) -> None:
        current = self.order_service.get_order(order_id)
        if current is None:
            raise ValueError("Encomenda não encontrada")
        if str(current["estado"]) in FINAL_STATES:
            raise ValueError(f"Encomendas em estado '{current['estado']}' não permitem transições de produção")
