from __future__ import annotations

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.theme import COLORS, SPACING
from ui.widgets.cards import InfoRow
from ui.widgets.common import _caption, clear_layout
from ui.widgets.controls import DangerButton, ElevatedCard, PrimaryButton, SecondaryButton


class ConfirmationDialog(QDialog):
    def __init__(self, title: str, message: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(420, 180)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.md)
        layout.addWidget(QLabel(message))
        buttons = QHBoxLayout()
        cancel = SecondaryButton("Cancelar")
        confirm = DangerButton("Confirmar")
        cancel.clicked.connect(self.reject)
        confirm.clicked.connect(self.accept)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)


class ErrorText(QLabel):
    def __init__(self) -> None:
        super().__init__("")
        self.setStyleSheet(f"color:{COLORS.danger}; font-size:12px;")
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setAccessibleName("Mensagem de validação")
        self.hide()

    def set_error(self, message: str | None) -> None:
        if message:
            self.setText(message)
            self.show()
        else:
            self.setText("")
            self.hide()


class LabeledInput(QWidget):
    def __init__(self, label: str, placeholder: str = "", required: bool = False) -> None:
        super().__init__()
        self.input = QLineEdit()
        self.input.setPlaceholderText(placeholder)
        self.error = ErrorText()
        self._normal_style = self.input.styleSheet()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        suffix = " *" if required else ""
        caption = QLabel(f"{label}{suffix}")
        caption.setBuddy(self.input)
        self.input.setAccessibleName(label)
        layout.addWidget(caption)
        layout.addWidget(self.input)
        layout.addWidget(self.error)

    def text(self) -> str:
        return self.input.text().strip()

    def set_text(self, value: str) -> None:
        self.input.setText(value)

    def set_error(self, message: str | None) -> None:
        self.error.set_error(message)
        if message:
            self.input.setStyleSheet(f"border:1px solid {COLORS.danger};")
        else:
            self.input.setStyleSheet(self._normal_style)


class LabeledTextArea(QWidget):
    def __init__(self, label: str, placeholder: str = "") -> None:
        super().__init__()
        self.input = QTextEdit()
        self.input.setPlaceholderText(placeholder)
        self.input.setFixedHeight(92)
        self.error = ErrorText()
        self._normal_style = self.input.styleSheet()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(_caption(label, self.input))
        layout.addWidget(self.input)
        layout.addWidget(self.error)

    def text(self) -> str:
        return self.input.toPlainText().strip()

    def set_error(self, message: str | None) -> None:
        self.error.set_error(message)
        self.input.setStyleSheet(f"border:1px solid {COLORS.danger};" if message else self._normal_style)


class LabeledComboBox(QWidget):
    def __init__(self, label: str, options: list[str]) -> None:
        super().__init__()
        self.input = QComboBox()
        self.input.addItems(options)
        self.error = ErrorText()
        self._normal_style = self.input.styleSheet()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(_caption(label, self.input))
        layout.addWidget(self.input)
        layout.addWidget(self.error)

    def value(self) -> str:
        return self.input.currentText()

    def set_error(self, message: str | None) -> None:
        self.error.set_error(message)
        self.input.setStyleSheet(f"border:1px solid {COLORS.danger};" if message else self._normal_style)


class LabeledSpinBox(QWidget):
    def __init__(self, label: str, minimum: int = 0, maximum: int = 9999) -> None:
        super().__init__()
        self.input = QSpinBox()
        self.input.setRange(minimum, maximum)
        self.error = ErrorText()
        self._normal_style = self.input.styleSheet()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(_caption(label, self.input))
        layout.addWidget(self.input)
        layout.addWidget(self.error)

    def value(self) -> int:
        return self.input.value()

    def set_error(self, message: str | None) -> None:
        self.error.set_error(message)
        self.input.setStyleSheet(f"border:1px solid {COLORS.danger};" if message else self._normal_style)


class LabeledMoneyField(QWidget):
    def __init__(self, label: str) -> None:
        super().__init__()
        self.input = QDoubleSpinBox()
        self.input.setLocale(QLocale(QLocale.Language.Portuguese, QLocale.Country.Portugal))
        self.input.setRange(0.0, 999999.0)
        self.input.setDecimals(2)
        self.input.setSuffix(" €")
        self.input.setSingleStep(1.0)
        self.error = ErrorText()
        self._normal_style = self.input.styleSheet()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(_caption(label, self.input))
        layout.addWidget(self.input)
        layout.addWidget(self.error)

    def value(self) -> float:
        return float(self.input.value())

    def set_value(self, value: float) -> None:
        self.input.setValue(value)

    def set_error(self, message: str | None) -> None:
        self.error.set_error(message)
        self.input.setStyleSheet(f"border:1px solid {COLORS.danger};" if message else self._normal_style)


class FormRow(QWidget):
    def __init__(self, *widgets: QWidget) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING.sm)
        for widget in widgets:
            layout.addWidget(widget)


class DividerLabel(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setStyleSheet(f"font-size:13px; font-weight:700; color:{COLORS.text_secondary}; margin-top:8px;")


class ModalHeader(QWidget):
    def __init__(self, title: str, subtitle: str | None = None) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size:22px; font-weight:760;")
        layout.addWidget(title_label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setStyleSheet(f"color:{COLORS.text_secondary};")
            layout.addWidget(sub)


class SummaryCard(ElevatedCard):
    def __init__(self, title: str, rows: list[tuple[str, str]]) -> None:
        super().__init__(title)
        self.body_layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        self.set_rows(rows)

    def set_rows(self, rows: list[tuple[str, str]]) -> None:
        clear_layout(self.body_layout, start_index=1)
        for key, value in rows:
            self.body_layout.addWidget(InfoRow(key, value))


class FormActions(QWidget):
    def __init__(self, cancel_text: str = "Cancelar", confirm_text: str = "Guardar") -> None:
        super().__init__()
        self.cancel_button = SecondaryButton(cancel_text)
        self.confirm_button = PrimaryButton(confirm_text)
        self.confirm_button.setDefault(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, SPACING.sm, 0, 0)
        layout.addStretch(1)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.confirm_button)
