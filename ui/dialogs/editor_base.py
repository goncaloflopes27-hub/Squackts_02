from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QWidget,
)

from ui.components import ConfirmationDialog, ErrorText
from ui.theme import app_stylesheet


class EditorDialog(QDialog):
    """Shared lifecycle: preserve errors, prevent duplicate writes and protect edits."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(app_stylesheet())
        self._saving = False
        self._saved = False
        self._submission_error: str | None = None
        self._baseline: tuple[object, ...] = ()
        self._save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self._save_shortcut.activated.connect(self._save_from_keyboard)

    def _save_from_keyboard(self) -> None:
        actions = getattr(self, "form_actions", None)
        if actions is not None and actions.confirm_button.isEnabled():
            actions.confirm_button.click()

    def _fit_to_screen(self, available: QRect | None = None) -> None:
        screen = self.screen()
        if available is None and screen is not None:
            available = screen.availableGeometry()
        if available is not None:
            self.resize(min(self.width(), max(320, available.width() - 24)), min(self.height(), max(320, available.height() - 48)))

    def showEvent(self, event: QShowEvent) -> None:
        self._fit_to_screen()
        super().showEvent(event)

    def _submit(self, operation: Callable[[], None], error: ErrorText, button: QPushButton, label: str) -> bool:
        """A failure anywhere in submission must leave a recoverable editor."""
        if self._saving or self._saved:
            return False
        self._saving = True
        button.setEnabled(False)
        button.setText("A guardar…")
        try:
            operation()
        except Exception as failure:
            logging.getLogger("squackts.ui").exception("Falha ao guardar em %s", type(self).__name__)
            if isinstance(failure, sqlite3.OperationalError) and "locked" in str(failure).lower():
                message = "A base de dados está ocupada. Aguarde e tente guardar novamente."
            elif isinstance(failure, sqlite3.Error):
                message = "Não foi possível guardar na base de dados. Os campos foram preservados; tente novamente."
            elif isinstance(failure, OverflowError):
                message = "Um valor excede o limite suportado. Reveja os montantes e as quantidades."
            elif isinstance(failure, (ValueError, OSError)):
                message = str(failure)
            else:
                message = "Ocorreu um erro inesperado ao guardar. Os campos foram preservados; consulte os logs em Sistema."
            self._submission_error = message
            error.set_error(message)
            self._reveal_error(error)
            return False
        finally:
            self._saving = False
            button.setText(label)
            button.setEnabled(True)
            validate = getattr(self, "_validate_form", None)
            if callable(validate):
                validate()
        button.setText("Guardado ✓")
        self._submission_error = ""
        error.set_error(None)
        return True

    def _reveal_error(self, widget: QWidget) -> None:
        widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        widget.setFocus(Qt.FocusReason.OtherFocusReason)
        for scroll in self.findChildren(QScrollArea):
            if scroll.isAncestorOf(widget):
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(lambda area=scroll: area.ensureWidgetVisible(widget, 12, 24))
                timer.timeout.connect(timer.deleteLater)
                timer.start(0)
                break

    def _snapshot(self) -> tuple[object, ...]:
        fields: list[object] = []
        for widget in self.findChildren(QWidget):
            if isinstance(widget, QCheckBox):
                fields.append(widget.isChecked())
            elif isinstance(widget, QLineEdit):
                fields.append(widget.text())
            elif isinstance(widget, QTextEdit):
                fields.append(widget.toPlainText())
            elif isinstance(widget, QComboBox):
                fields.append(widget.currentText())
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                fields.append(widget.value())
        items = getattr(self, "items_buffer", [])
        fields.append(repr(items))
        return tuple(fields)

    def _mark_clean(self) -> None:
        self._baseline = self._snapshot()

    def reject(self) -> None:
        if self._saving:
            return
        if self._baseline and self._snapshot() != self._baseline:
            dialog = ConfirmationDialog(
                "Alterações por guardar", "Sair e descartar as alterações deste formulário?", self
            )
            if not dialog.exec():
                return
        super().reject()

    def _accept_saved(self) -> None:
        self._saved = True
        self._mark_clean()
        QDialog.accept(self)
