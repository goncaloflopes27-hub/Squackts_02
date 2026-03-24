from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from service_container import ServiceContainer, bootstrap_infrastructure
from ui.main_window import MainWindow


def main() -> int:
    container: ServiceContainer = bootstrap_infrastructure()
    app = QApplication(sys.argv)
    window = MainWindow(container)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
