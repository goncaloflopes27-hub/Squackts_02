from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

APP_NAME: str = "Squackts POD Manager"
APP_VERSION: str = "0.2.0"
WINDOW_MIN_WIDTH: int = 1280
WINDOW_MIN_HEIGHT: int = 800

BASE_DIR: Path = Path(__file__).resolve().parent
DATA_DIR: Path = BASE_DIR / "data"
BACKUPS_DIR: Path = BASE_DIR / "backups"
IMAGES_DIR: Path = BASE_DIR / "assets" / "images"
LOGS_DIR: Path = BASE_DIR / "logs"

DB_PATH: Path = DATA_DIR / "pod_manager.db"
LOG_FILE_PATH: Path = LOGS_DIR / "app.log"

DEFAULT_BUSY_TIMEOUT_MS: int = 5_000
SCHEMA_USER_VERSION: int = 3


@dataclass(frozen=True)
class AppPaths:
    base_dir: Path = BASE_DIR
    data_dir: Path = DATA_DIR
    backups_dir: Path = BACKUPS_DIR
    images_dir: Path = IMAGES_DIR
    logs_dir: Path = LOGS_DIR
    db_path: Path = DB_PATH
    log_file_path: Path = LOG_FILE_PATH


PATHS = AppPaths()


def required_directories() -> tuple[Path, ...]:
    return (PATHS.data_dir, PATHS.backups_dir, PATHS.images_dir, PATHS.logs_dir)
