"""Visible, logged reporting for exceptions escaping a Qt callback."""
from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from types import TracebackType

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox


def install_exception_handler(application: QApplication, log_path: Path) -> Callable[[], None]:
    previous = sys.excepthook
    notices: list[QMessageBox] = []

    def report(kind: type[BaseException], error: BaseException, traceback: TracebackType | None) -> None:
        if not issubclass(kind, Exception):
            previous(kind, error, traceback)
            return
        logging.getLogger("squackts.ui").critical("Erro num callback da interface", exc_info=(kind, error, traceback))
        if notices:
            return
        notice = QMessageBox(application.activeWindow())
        notice.setWindowTitle("SquackTS — erro na operação")
        notice.setIcon(QMessageBox.Icon.Critical)
        notice.setText("A operação encontrou um erro. Confirme os dados antes de continuar.")
        notice.setInformativeText(f"Os detalhes foram registados em:\n{log_path}")
        notice.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        notices.append(notice)
        notice.finished.connect(lambda _result: notices.remove(notice))
        notice.open()

    sys.excepthook = report

    def restore() -> None:
        sys.excepthook = previous
        for notice in list(notices):
            notice.close()

    return restore
