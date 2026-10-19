from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from sqlite3 import Connection

import config
from config import AppPaths
from data_paths import migrate_legacy_data
from db import connect
from repositories import ClientRepository, LogRepository, OrderRepository, ProductRepository, SettingsRepository
from schema import apply_schema
from services import BackupService, ClientService, DashboardService, OrderService, ProductionService, ProductService
from services.backup_jobs import BackupJobs
from services.events import ChangeEvents
from services.image_service import ImageService
from services.inventory_service import InventoryService
from services.preferences_service import PreferencesService
from utils import ensure_dirs


@dataclass(slots=True)
class ServiceContainer:
    conn: Connection
    db_path: Path
    backups_dir: Path
    images_dir: Path
    logs_dir: Path
    products: ProductService
    clients: ClientService
    orders: OrderService
    production: ProductionService
    dashboard: DashboardService
    backup: BackupService
    logs: LogRepository
    settings: SettingsRepository
    events: ChangeEvents = field(default_factory=ChangeEvents)
    images: ImageService | None = None
    inventory: InventoryService | None = None
    preferences: PreferencesService | None = None
    backup_jobs: BackupJobs | None = None

    def close(self) -> None:
        if self.backup_jobs is not None:
            self.backup_jobs.shutdown(wait=True)
        self.conn.close()


def bootstrap_infrastructure(paths: AppPaths | None = None, *, migrate_legacy: bool = True) -> ServiceContainer:
    selected = paths or config.PATHS
    if migrate_legacy:
        migrate_legacy_data(selected)
    ensure_dirs((selected.data_dir, selected.backups_dir, selected.images_dir, selected.logs_dir))
    conn = connect(selected.db_path)
    try:
        apply_schema(conn)
        events = ChangeEvents()
        logs = LogRepository(conn)
        products = ProductRepository(conn)
        clients = ClientRepository(conn)
        orders = OrderRepository(conn)
        settings = SettingsRepository(conn)
        images = ImageService(selected.images_dir)
        inventory = InventoryService(conn, events=events)
        product_service = ProductService(conn, products, logs, events=events, images=images, inventory=inventory)
        client_service = ClientService(conn, clients, logs, events=events)
        order_service = OrderService(conn, orders, products, clients, logs, settings, events=events)
        return ServiceContainer(
            conn=conn,
            db_path=selected.db_path,
            backups_dir=selected.backups_dir,
            images_dir=selected.images_dir,
            logs_dir=selected.logs_dir,
            products=product_service,
            clients=client_service,
            orders=order_service,
            production=ProductionService(conn, orders, logs, order_service=order_service),
            dashboard=DashboardService(conn),
            backup=BackupService(conn, logs, selected.db_path, selected.backups_dir, selected.images_dir, selected.logs_dir),
            logs=logs,
            settings=settings,
            events=events,
            images=images,
            inventory=inventory,
            preferences=PreferencesService(conn, settings, logs, events),
            backup_jobs=BackupJobs(selected),
        )
    except Exception:
        conn.close()
        raise
