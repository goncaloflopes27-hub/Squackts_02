from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection

from config import PATHS, required_directories
from db import connect
from repositories import (
    ClientRepository,
    DashboardRepository,
    LogRepository,
    OrderRepository,
    ProductRepository,
    SettingsRepository,
)
from schema import apply_schema
from services import BackupService, ClientService, DashboardService, OrderService, ProductionService, ProductService
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


def bootstrap_infrastructure() -> ServiceContainer:
    ensure_dirs(required_directories())
    conn = connect(PATHS.db_path)
    apply_schema(conn)

    logs_repo = LogRepository(conn)
    products_repo = ProductRepository(conn)
    clients_repo = ClientRepository(conn)
    orders_repo = OrderRepository(conn)
    settings_repo = SettingsRepository(conn)
    dashboard_repo = DashboardRepository(conn)

    products_service = ProductService(conn, products_repo, logs_repo)
    clients_service = ClientService(conn, clients_repo, logs_repo)
    orders_service = OrderService(conn, orders_repo, products_repo, clients_repo, logs_repo, settings_repo)
    production_service = ProductionService(conn, orders_repo, logs_repo)
    dashboard_service = DashboardService(dashboard_repo)
    backup_service = BackupService(
        conn=conn,
        logs=logs_repo,
        settings=settings_repo,
        db_path=PATHS.db_path,
        backups_dir=PATHS.backups_dir,
        images_dir=PATHS.images_dir,
        logs_dir=PATHS.logs_dir,
    )

    return ServiceContainer(
        conn=conn,
        db_path=PATHS.db_path,
        backups_dir=PATHS.backups_dir,
        images_dir=PATHS.images_dir,
        logs_dir=PATHS.logs_dir,
        products=products_service,
        clients=clients_service,
        orders=orders_service,
        production=production_service,
        dashboard=dashboard_service,
        backup=backup_service,
        logs=logs_repo,
        settings=settings_repo,
    )
