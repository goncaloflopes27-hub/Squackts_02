from __future__ import annotations

import logging
import sys
import traceback
from typing import Any

from PySide6.QtWidgets import QApplication

from config import PATHS
from service_container import ServiceContainer, bootstrap_infrastructure
from ui.main_window import MainWindow
from utils import configure_logging

logger = logging.getLogger(__name__)


def _handle_unhandled_exception(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
    logger.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
    traceback.print_exception(exc_type, exc, tb)


def main() -> int:
    configure_logging(PATHS.log_file_path)
    sys.excepthook = _handle_unhandled_exception
    logger.info("Application bootstrap started")

    container: ServiceContainer = bootstrap_infrastructure()
    app = QApplication(sys.argv)
    app.aboutToQuit.connect(lambda: logger.info("Application shutdown"))
    window = MainWindow(container)
    window.show()
    logger.info("Main window initialized")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
