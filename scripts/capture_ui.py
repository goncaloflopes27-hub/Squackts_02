"""Capture the real desktop pages with disposable demo data at a chosen size."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/screenshots"))
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication

    from config import APP_DISPLAY_VERSION, AppPaths
    from scripts.demo import seed_demo
    from service_container import bootstrap_infrastructure
    from ui.main_window import MainWindow
    from ui.smoke import SmokeProbe
    qt = QApplication([])
    qt.setApplicationVersion(APP_DISPLAY_VERSION)
    with TemporaryDirectory(prefix="squackts-visual-") as directory:
        home = Path(directory)
        seed_demo(home)
        container = bootstrap_infrastructure(AppPaths.from_home(home), migrate_legacy=False)
        try:
            window = MainWindow(container, available_geometry=QRect(0, 0, args.width + 24, args.height + 48))
            window.resize(args.width, args.height)
            window.show()
            probe = SmokeProbe(window, qt, args.output)
            probe.start()
            status = qt.exec()
            return status or int(bool(probe.failures))
        finally:
            container.close()


if __name__ == "__main__":
    raise SystemExit(main())
