from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME: str = "SquackTS"
APP_VERSION: str = "0.3.2"
WINDOW_MIN_WIDTH: int = 1280
WINDOW_MIN_HEIGHT: int = 800
BASE_DIR: Path = Path(__file__).resolve().parent


def display_version() -> str:
    try:
        document = json.loads((BASE_DIR / "build-info.json").read_text(encoding="utf-8"))
        if isinstance(document, dict) and document.get("base_version") == APP_VERSION:
            release = str(document.get("release_version", ""))
            if re.fullmatch(re.escape(APP_VERSION) + r"(?:-rc\.\d+)?", release):
                return release
    except (OSError, ValueError):
        pass
    return APP_VERSION


APP_DISPLAY_VERSION: str = display_version()


def application_data_home() -> Path:
    """Keep user data independent of the source tree and application updates."""
    configured = os.environ.get("SQUACKTS_DATA_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        return (Path(local) if local else Path.home() / "AppData" / "Local") / "Squackts"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Squackts"
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else Path.home() / ".local" / "share") / "squackts"


DATA_HOME: Path = application_data_home()
DATA_DIR: Path = DATA_HOME / "data"
BACKUPS_DIR: Path = DATA_HOME / "backups"
IMAGES_DIR: Path = DATA_HOME / "images"
LOGS_DIR: Path = DATA_HOME / "logs"
DB_PATH: Path = DATA_DIR / "pod_manager.db"
LOG_FILE_PATH: Path = LOGS_DIR / "app.log"
DEFAULT_BUSY_TIMEOUT_MS: int = 5_000
SCHEMA_USER_VERSION: int = 7


@dataclass(frozen=True)
class AppPaths:
    base_dir: Path = BASE_DIR
    data_dir: Path = DATA_DIR
    backups_dir: Path = BACKUPS_DIR
    images_dir: Path = IMAGES_DIR
    logs_dir: Path = LOGS_DIR
    db_path: Path = DB_PATH
    log_file_path: Path = LOG_FILE_PATH

    @classmethod
    def from_home(cls, home: Path, *, base_dir: Path = BASE_DIR) -> AppPaths:
        home = home.expanduser().resolve()
        return cls(
            base_dir,
            home / "data",
            home / "backups",
            home / "images",
            home / "logs",
            home / "data" / "pod_manager.db",
            home / "logs" / "app.log",
        )


PATHS = AppPaths()


def required_directories() -> tuple[Path, ...]:
    return (PATHS.data_dir, PATHS.backups_dir, PATHS.images_dir, PATHS.logs_dir)
