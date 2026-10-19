from __future__ import annotations

import sys
import traceback
from pathlib import Path
from types import TracebackType

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.pages.dashboard_page import DashboardPage


class SmokeProbe(QObject):
    """Exercise actual widget ownership, event-loop updates and page rendering."""

    def __init__(self, window: MainWindow, application: QApplication, screenshots: Path | None = None) -> None:
        super().__init__(window)
        self.window = window
        self.application = application
        self.screenshots = screenshots
        self.failures: list[str] = []
        self.pages = iter(window.page_map)
        self.page_key = ""
        self._old_hook = sys.excepthook
        self._dashboard_refreshes = 0

    def start(self) -> None:
        sys.excepthook = self._exception
        if self.screenshots is not None:
            self.screenshots.mkdir(parents=True, exist_ok=True)
        QTimer.singleShot(100, self._next_page)
        QTimer.singleShot(30_000, self._timeout)

    def _exception(self, kind: type[BaseException], error: BaseException, tb: TracebackType | None) -> None:
        traceback.print_exception(kind, error, tb)
        self.failures.append(str(error))
        sys.excepthook = self._old_hook
        self.application.exit(1)

    def _timeout(self) -> None:
        if not self.failures:
            self.failures.append("Tempo limite da verificação da aplicação")
        self.application.exit(1)

    def _next_page(self) -> None:
        page = next(self.pages, None)
        if page is None:
            self.window.navigate("dashboard")
            QTimer.singleShot(100, self._refresh_dashboard)
            return
        self.page_key = page
        self.window.navigate(page)
        QTimer.singleShot(400, self._verify_page)

    def _verify_page(self) -> None:
        current = self.window.page_refs[self.page_key]
        if self.window.stack.currentWidget() is not current:
            # The adaptive shell may wrap pages in a QScrollArea.
            wrapper = self.window.stack.currentWidget()
            if wrapper is None or not wrapper.isAncestorOf(current):
                raise AssertionError(f"Página de navegação incorreta: {self.page_key}")
        loading_error = getattr(current, "_loading_error", None)
        if loading_error:
            raise AssertionError(str(loading_error))
        pixmap = self.window.grab()
        if pixmap.isNull():
            raise AssertionError(f"Falha ao renderizar {self.page_key}")
        if self.screenshots is not None:
            if not pixmap.save(str(self.screenshots / f"{self.page_key}.png")):
                raise RuntimeError("Não foi possível guardar a captura")
        print(f"PASS: {self.page_key}", flush=True)
        self._next_page()

    def _refresh_dashboard(self) -> None:
        page = self.window.page_refs["dashboard"]
        assert isinstance(page, DashboardPage)
        page.refresh()
        self._dashboard_refreshes += 1
        if self._dashboard_refreshes < 3:
            QTimer.singleShot(100, self._refresh_dashboard)
            return
        sys.excepthook = self._old_hook
        print("PASS: arranque, seis páginas, renderização e refresh repetido", flush=True)
        self.window.close()
