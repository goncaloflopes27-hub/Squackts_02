from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QWidget,
)

from ui.components import ConfirmationDialog
from ui.theme import app_stylesheet


class EditorDialog(QDialog):
    """Shared lifecycle: preserve errors, prevent duplicate writes and protect edits."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(app_stylesheet())
        self._saving = False
        self._baseline: tuple[object, ...] = ()

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
        self._mark_clean()
        QDialog.accept(self)
