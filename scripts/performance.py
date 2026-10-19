"""Measure a synthetic workload in a temporary directory, never in user data."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from service_container import ServiceContainer


def measure(operation: Callable[[], object], repetitions: int = 5) -> dict[str, float]:
    samples = []
    for _ in range(repetitions):
        started = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - started) * 1_000)
    return {"median_ms": round(statistics.median(samples), 2), "max_ms": round(max(samples), 2)}


def measure_ui(container: ServiceContainer) -> dict[str, object]:
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from ui.main_window import MainWindow
    from ui.pages.orders_page import OrdersPage
    from ui.pages.production_page import ProductionPage

    application = QApplication.instance() or QApplication([])
    assert isinstance(application, QApplication)
    application.setProperty("reduceMotion", True)
    started = time.perf_counter()
    window = MainWindow(container)
    window.show()
    application.processEvents()
    startup_ms = round((time.perf_counter() - started) * 1_000, 2)
    try:
        window.navigate("orders")
        page = window.page_refs["orders"]
        assert isinstance(page, OrdersPage)
        application.processEvents()

        def update() -> None:
            page.refresh()
            application.processEvents()

        def search() -> None:
            page.apply_search("0001")
            application.processEvents()

        def filter_payment() -> None:
            page.payment_filter.setCurrentIndex(1 if page.payment_filter.currentIndex() != 1 else 2)
            application.processEvents()

        result: dict[str, object] = {
            "qt_platform": application.platformName(), "startup_populated_ms": startup_ms,
            "orders_refresh": measure(update, repetitions=3),
            "orders_search": measure(search, repetitions=3),
        }
        page.apply_search("")
        result["orders_payment_filter"] = measure(filter_payment, repetitions=3)
        window.navigate("production")
        production = window.page_refs["production"]
        assert isinstance(production, ProductionPage)

        def refresh_production() -> None:
            production.refresh()
            application.processEvents()

        result["production_refresh"] = measure(refresh_production, repetitions=3)
        return result
    finally:
        window.close()
        application.processEvents()


def benchmark(home: Path, orders: int, *, include_ui: bool = False) -> dict[str, object]:
    started = time.perf_counter()
    from config import AppPaths
    from service_container import bootstrap_infrastructure

    paths = AppPaths.from_home(home)
    container = bootstrap_infrastructure(paths, migrate_legacy=False)
    startup_ms = (time.perf_counter() - started) * 1_000
    try:
        client_id = container.clients.create_client({"nome": "Carga sintética", "email": "performance@example.test", "ativo": 1})
        products = [
            container.products.create_product({
                "nome": f"Produto {index}", "sku": f"PERF-{index}", "preco": "15.00", "custo": "5.00",
                "stock": 0, "stock_minimo": 0, "tipo_producao": "print_on_demand", "ativo": 1,
            }) for index in range(3)
        ]
        seed_started = time.perf_counter()
        for index in range(orders):
            container.orders.create_order({
                "client_id": client_id, "estado": "confirmada", "pago": index % 2, "tracking": "",
                "metodo_pagamento": "manual", "portes": "3.00", "data_prevista": "", "notas": "Teste de carga",
                "items": [{"product_id": product_id, "quantidade": 1 + index % 3} for product_id in products],
            })
        seed_seconds = round(time.perf_counter() - seed_started, 2)
        results: dict[str, object] = {
            "orders": orders, "items_per_order": len(products), "startup_empty_ms": round(startup_ms, 2),
            "seed_seconds": seed_seconds,
            "dashboard": measure(container.dashboard.get_summary),
            "orders_list": measure(container.orders.list_orders),
            "production_queue": measure(container.production.get_production_queue),
        }
        container.close()
        reopen_started = time.perf_counter()
        container = bootstrap_infrastructure(paths, migrate_legacy=False)
        results["startup_populated_ms"] = round((time.perf_counter() - reopen_started) * 1_000, 2)
        if include_ui:
            results["ui"] = measure_ui(container)
        return results
    finally:
        container.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--orders", type=int, default=10_000)
    parser.add_argument("--ui", action="store_true", help="Medir também arranque, pesquisa, filtros e refresh reais do Qt")
    parser.add_argument("--output", type=Path, help="Guardar métricas JSON; a base temporária é sempre eliminada")
    args = parser.parse_args()
    if args.orders < 1:
        parser.error("--orders deve ser positivo")
    with TemporaryDirectory(prefix="squackts-performance-") as directory:
        result = benchmark(Path(directory), args.orders, include_ui=args.ui)
    report = json.dumps(result, ensure_ascii=False, indent=2)
    print(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
