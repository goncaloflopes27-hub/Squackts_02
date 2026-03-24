from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.animations import Motion, fade_in
from ui.theme import COLORS, RADIUS, SPACING

CONTROL_HEIGHT = 40
_ACTIVE_TOASTS: dict[int, list[ToastMessage]] = {}


def apply_soft_shadow(widget: QWidget, *, blur: float = 28.0, y_offset: int = 8, alpha: int = 72) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    effect.setColor(QColor(10, 15, 30, alpha))
    widget.setGraphicsEffect(effect)


class AppCard(QFrame):
    def __init__(self, title: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AppCard")
        self.setStyleSheet(
            f"QFrame#AppCard {{background:{COLORS.surface}; border:1px solid {COLORS.border}; border-radius:{RADIUS.lg}px;}}"
            f"QFrame#AppCard:hover {{border:1px solid {COLORS.border_strong};}}"
        )
        apply_soft_shadow(self, blur=24.0, y_offset=6, alpha=56)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
        layout.setSpacing(SPACING.sm)
        if title:
            label = QLabel(title)
            label.setStyleSheet(f"font-size:15px; font-weight:650; color:{COLORS.text_primary};")
            layout.addWidget(label)


class ElevatedCard(AppCard):
    def __init__(self, title: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        self.setStyleSheet(
            f"QFrame#AppCard {{background:{COLORS.surface_elevated}; border:1px solid {COLORS.border_strong}; border-radius:{RADIUS.lg}px;}}"
        )
        apply_soft_shadow(self, blur=32.0, y_offset=8, alpha=80)


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 28px; font-weight: 780; letter-spacing: 0.4px;")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setStyleSheet(f"font-size: 13px; color: {COLORS.text_secondary};")
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)


class PanelHeader(QWidget):
    def __init__(self, title: str, subtitle: str | None = None, right_widget: QWidget | None = None) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        left = QVBoxLayout()
        label = QLabel(title)
        label.setStyleSheet("font-size:16px; font-weight:700;")
        left.addWidget(label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setStyleSheet(f"font-size:12px; color:{COLORS.text_secondary};")
            left.addWidget(sub)
        layout.addLayout(left)
        layout.addStretch(1)
        if right_widget:
            layout.addWidget(right_widget)


class _BaseButton(QPushButton):
    def __init__(self, text: str, bg: str, hover: str, border: str, fg: str = COLORS.text_primary) -> None:
        super().__init__(text)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(CONTROL_HEIGHT)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: {bg};
                border: 1px solid {border};
                border-radius: {RADIUS.md}px;
                color: {fg};
                font-weight: 650;
                padding: 9px 14px;
            }}
            QPushButton:hover {{ background: {hover}; border: 1px solid {COLORS.border_strong}; }}
            QPushButton:focus {{ border: 1px solid {COLORS.primary}; }}
            QPushButton:disabled {{ background:{COLORS.surface_alt}; color:{COLORS.text_muted}; border:1px solid {COLORS.border}; }}
            QPushButton:pressed {{ background: {hover}; }}
            """
        )


class PrimaryButton(_BaseButton):
    def __init__(self, text: str) -> None:
        super().__init__(text, COLORS.primary, COLORS.primary_hover, COLORS.primary)


class SecondaryButton(_BaseButton):
    def __init__(self, text: str) -> None:
        super().__init__(text, COLORS.surface_alt, COLORS.surface_elevated, COLORS.border)


class GhostButton(_BaseButton):
    def __init__(self, text: str) -> None:
        super().__init__(text, "transparent", COLORS.surface_alt, COLORS.border)


class DangerButton(_BaseButton):
    def __init__(self, text: str) -> None:
        super().__init__(text, "#7F1D1D", "#991B1B", COLORS.danger)


class IconButton(QToolButton):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.setText(text)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(CONTROL_HEIGHT)
        self.setStyleSheet(
            f"QToolButton {{background:{COLORS.surface_alt}; border:1px solid {COLORS.border}; border-radius:{RADIUS.md}px; padding:8px 12px; font-weight:600; color:{COLORS.text_secondary};}}"
            f"QToolButton:hover {{background:{COLORS.surface_elevated}; border:1px solid {COLORS.border_strong};}}"
            f"QToolButton:focus {{border:1px solid {COLORS.primary}; color:{COLORS.text_primary};}}"
        )


class SidebarButton(QPushButton):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(CONTROL_HEIGHT)
        self.setStyleSheet(
            f"""
            QPushButton {{
                text-align:left;
                background:transparent;
                border:1px solid transparent;
                border-radius:{RADIUS.md}px;
                padding:11px 14px;
                color:{COLORS.text_secondary};
                font-weight:620;
            }}
            QPushButton:hover {{background:{COLORS.surface_alt}; color:{COLORS.text_primary}; border:1px solid {COLORS.border};}}
            QPushButton:checked {{
                background:{COLORS.surface_elevated};
                border:1px solid {COLORS.border_strong};
                border-left:3px solid {COLORS.primary};
                color:{COLORS.text_primary};
                padding-left:12px;
            }}
            QPushButton:focus {{border:1px solid {COLORS.primary};}}
            """
        )


class SearchInput(QLineEdit):
    def __init__(self, placeholder: str = "Pesquisar...") -> None:
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(CONTROL_HEIGHT)
        self.setClearButtonEnabled(True)
        self.setStyleSheet(
            f"QLineEdit {{padding-left:14px; font-size:13px;}}"
            f"QLineEdit::placeholder {{color:{COLORS.text_muted};}}"
        )


class FilterChip(QPushButton):
    def __init__(self, text: str, active: bool = False) -> None:
        super().__init__(text)
        self.setCheckable(True)
        self.setChecked(active)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(36)
        self.setStyleSheet(
            f"""
            QPushButton {{background:{COLORS.surface}; border:1px solid {COLORS.border}; border-radius:{RADIUS.sm}px; padding:6px 12px;}}
            QPushButton:checked {{background:{COLORS.surface_alt}; border:1px solid {COLORS.primary};}}
            QPushButton:hover {{background:{COLORS.surface_alt};}}
            QPushButton:focus {{border:1px solid {COLORS.primary};}}
            """
        )


class SegmentedControl(QWidget):
    selection_changed = Signal(str)

    def __init__(self, options: list[str]) -> None:
        super().__init__()
        self._options = options
        self._buttons: list[FilterChip] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING.xs)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for idx, label in enumerate(options):
            button = FilterChip(label, active=idx == 0)
            self.group.addButton(button, idx)
            button.clicked.connect(lambda _checked, value=label: self.selection_changed.emit(value))
            self._buttons.append(button)
            layout.addWidget(button)
        layout.addStretch(1)

    def value(self) -> str:
        checked_id = self.group.checkedId()
        if checked_id < 0 or checked_id >= len(self._options):
            return self._options[0] if self._options else ""
        return self._options[checked_id]

    def set_value(self, value: str) -> None:
        for idx, option in enumerate(self._options):
            if option == value and idx < len(self._buttons):
                self._buttons[idx].setChecked(True)
                break


class FilterBar(QWidget):
    def __init__(self, chips: Iterable[str]) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING.xs)
        for index, chip in enumerate(chips):
            layout.addWidget(FilterChip(chip, active=index == 0))
        layout.addStretch(1)


class StatusBadge(QLabel):
    COLORS_BY_STATUS = {
        "ok": COLORS.success,
        "warning": COLORS.warning,
        "danger": COLORS.danger,
        "info": COLORS.info,
        "queued": COLORS.accent_violet,
    }

    def __init__(self, text: str, tone: str = "info") -> None:
        super().__init__(text)
        color = self.COLORS_BY_STATUS.get(tone, COLORS.info)
        self.setStyleSheet(
            f"background:{color}1F; color:{color}; border:1px solid {color}; border-radius:{RADIUS.sm}px; padding:3px 8px; font-weight:650;"
        )


class StatPill(StatusBadge):
    pass


class KPIWidget(AppCard):
    def __init__(self, label: str, value: str, delta: str, tone: str = "info") -> None:
        super().__init__()
        layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        top = QLabel(label)
        top.setStyleSheet(f"color:{COLORS.text_secondary}; font-size:12px; text-transform:uppercase;")
        layout.addWidget(top)
        val = QLabel(value)
        val.setStyleSheet("font-size: 30px; font-weight: 780; letter-spacing: 0.3px;")
        layout.addWidget(val)
        layout.addWidget(StatPill(delta, tone))


class InlineMetric(QWidget):
    def __init__(self, label: str, value: str) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label_widget = QLabel(label)
        label_widget.setStyleSheet(f"color:{COLORS.text_secondary};")
        value_widget = QLabel(value)
        value_widget.setStyleSheet("font-weight:700;")
        layout.addWidget(label_widget)
        layout.addStretch(1)
        layout.addWidget(value_widget)


class MetricTile(AppCard):
    def __init__(self, title: str, value: str) -> None:
        super().__init__()
        layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        title_label = QLabel(title)
        title_label.setStyleSheet(f"color:{COLORS.text_secondary};")
        layout.addWidget(title_label)
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"font-size:18px; font-weight:700; color:{COLORS.text_primary};")
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class EmptyState(AppCard):
    def __init__(self, title: str, description: str) -> None:
        super().__init__()
        layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        layout.setSpacing(SPACING.sm)
        layout.addStretch(1)
        icon = QLabel("◌")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(
            f"min-width:34px; min-height:34px; max-width:34px; max-height:34px;"
            f"border-radius:{RADIUS.sm}px; background:{COLORS.surface_alt}; color:{COLORS.text_secondary}; font-size:16px;"
        )
        layout.addWidget(icon, alignment=Qt.AlignLeft)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size:18px; font-weight:720;")
        self.desc_label = QLabel(description)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet(f"color:{COLORS.text_secondary}; line-height:1.4;")
        layout.addWidget(self.title_label)
        layout.addWidget(self.desc_label)
        layout.addStretch(1)

    def set_content(self, title: str, description: str) -> None:
        self.title_label.setText(title)
        self.desc_label.setText(description)


class RichEmptyState(EmptyState):
    def __init__(self, title: str, description: str, cta_text: str = "Criar agora") -> None:
        super().__init__(title, description)
        layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        layout.addWidget(PrimaryButton(cta_text))


class DetailPanel(ElevatedCard):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setMinimumWidth(360)
        self.setObjectName("DetailPanel")
        self.setStyleSheet(
            f"QFrame#AppCard, QFrame#DetailPanel {{background:{COLORS.surface_elevated}; border:1px solid {COLORS.border_strong}; border-radius:{RADIUS.lg}px;}}"
        )
        panel_layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        panel_layout.setSpacing(SPACING.sm)
        panel_layout.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
        self.header = PanelHeader(title)
        panel_layout.addWidget(self.header)
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(SPACING.sm)
        panel_layout.addLayout(self.content_layout)

    def clear_content(self) -> None:
        clear_layout(self.content_layout)

    def add_content_widget(self, widget: QWidget) -> None:
        self.content_layout.addWidget(widget)


class KeyValueCard(AppCard):
    def __init__(self, title: str, entries: list[tuple[str, str]]) -> None:
        super().__init__(title)
        self._body_layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        self.set_entries(entries)

    def set_entries(self, entries: list[tuple[str, str]]) -> None:
        clear_layout(self._body_layout)
        for key, value in entries:
            self._body_layout.addWidget(InfoRow(key, value))


class InfoRow(QWidget):
    def __init__(self, key: str, value: str) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        left = QLabel(key)
        left.setStyleSheet(f"color:{COLORS.text_secondary}; font-size:12px;")
        right = QLabel(value)
        right.setStyleSheet("font-weight:650;")
        right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(left)
        layout.addStretch(1)
        layout.addWidget(right)


class InfoGrid(AppCard):
    def __init__(self, title: str, rows: list[tuple[str, str]], columns: int = 2) -> None:
        super().__init__(title)
        self.columns = columns
        self._layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        self._wrapper = QWidget()
        self._grid = QGridLayout(self._wrapper)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(SPACING.md)
        self._grid.setVerticalSpacing(SPACING.sm)
        self._layout.addWidget(self._wrapper)
        self.set_rows(rows)

    def set_rows(self, rows: list[tuple[str, str]]) -> None:
        clear_layout(self._grid)
        for index, (key, value) in enumerate(rows):
            row = index // self.columns
            col = index % self.columns
            block = AppCard()
            block_layout: QVBoxLayout = block.layout()  # type: ignore[assignment]
            k = QLabel(key)
            k.setStyleSheet(f"color:{COLORS.text_secondary};")
            v = QLabel(value)
            v.setStyleSheet("font-weight:700;")
            block_layout.addWidget(k)
            block_layout.addWidget(v)
            self._grid.addWidget(block, row, col)


class FormSection(AppCard):
    def __init__(self, title: str) -> None:
        super().__init__(title)


class Toolbar(QWidget):
    def __init__(self, *widgets: QWidget) -> None:
        super().__init__()
        self.setObjectName("Toolbar")
        self.setStyleSheet(
            f"""
            QWidget#Toolbar {{
                background: {COLORS.surface};
                border: 1px solid {COLORS.border};
                border-radius: {RADIUS.lg}px;
            }}
            QWidget#Toolbar:hover {{
                border: 1px solid {COLORS.border_strong};
            }}
            """
        )
        apply_soft_shadow(self, blur=16.0, y_offset=4, alpha=40)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.sm, SPACING.md, SPACING.sm)
        layout.setSpacing(SPACING.sm)
        for widget in widgets:
            layout.addWidget(widget)
        layout.addStretch(1)


class RowActionBar(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING.xs)
        layout.addWidget(IconButton("Abrir"))
        layout.addWidget(IconButton("Editar"))
        layout.addWidget(IconButton("Mais"))


class LoadingState(AppCard):
    def __init__(self, text: str = "A carregar...") -> None:
        super().__init__()
        layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        layout.addWidget(QLabel(text))
        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        progress.setStyleSheet(
            f"QProgressBar {{background:{COLORS.surface_alt}; border:0; border-radius:{RADIUS.sm}px; min-height:8px;}}"
            f"QProgressBar::chunk {{background:{COLORS.primary}; border-radius:{RADIUS.sm}px;}}"
        )
        layout.addWidget(progress)


class DataTable(QTableWidget):
    def __init__(self, rows: int, columns: int) -> None:
        super().__init__(rows, columns)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setCornerButtonEnabled(False)
        self.horizontalHeader().setDefaultSectionSize(168)
        self.horizontalHeader().setMinimumSectionSize(88)
        self.horizontalHeader().setFixedHeight(44)
        self.verticalHeader().setDefaultSectionSize(44)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAlternatingRowColors(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet(
            f"QTableWidget {{border-radius:{RADIUS.lg}px;}}"
            f"QTableWidget::item {{padding: 9px 12px; border-bottom:1px solid {COLORS.border};}}"
            f"QTableWidget::item:selected {{background:{COLORS.overlay_soft}; color:{COLORS.text_primary};}}"
        )


class ActivityList(AppCard):
    def __init__(self, title: str, activities: list[tuple[str, str]]) -> None:
        super().__init__(title)
        self._body_layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        self.set_activities(activities)

    def set_activities(self, activities: list[tuple[str, str]]) -> None:
        clear_layout(self._body_layout)
        for when, what in activities:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(StatPill(when, "info"))
            row_layout.addWidget(QLabel(what))
            row_layout.addStretch(1)
            self._body_layout.addWidget(row)


class PageSection(AppCard):
    def __init__(self, title: str, subtitle: str | None = None) -> None:
        super().__init__()
        layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        layout.addWidget(PanelHeader(title, subtitle))


class PlaceholderThumbnail(QWidget):
    def __init__(self, text: str = "IMG") -> None:
        super().__init__()
        self._text = text
        self.setFixedSize(56, 56)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(COLORS.surface_alt))
        painter.setPen(Qt.white)
        painter.drawText(self.rect(), Qt.AlignCenter, self._text)
        painter.end()


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
        self.setStyleSheet(f"color:{COLORS.danger}; font-size:11px;")
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
        layout.addWidget(QLabel(f"{label}{suffix}"))
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
        layout.addWidget(QLabel(label))
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
        layout.addWidget(QLabel(label))
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
        layout.addWidget(QLabel(label))
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
        self.input.setRange(0.0, 999999.0)
        self.input.setDecimals(2)
        self.input.setPrefix("€")
        self.input.setSingleStep(1.0)
        self.error = ErrorText()
        self._normal_style = self.input.styleSheet()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label))
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


class ToastMessage(QFrame):
    def __init__(self, text: str, tone: str = "info", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        palette = {"info": COLORS.info, "ok": COLORS.success, "danger": COLORS.danger, "warning": COLORS.warning}
        color = palette.get(tone, COLORS.info)
        self.setStyleSheet(
            f"background:{COLORS.surface_elevated}; border:1px solid {color}; border-radius:{RADIUS.md}px;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        accent = QFrame()
        accent.setFixedWidth(4)
        accent.setStyleSheet(f"background:{color}; border:none; border-radius:2px;")
        layout.addWidget(accent)
        label = QLabel(text)
        label.setStyleSheet(f"color:{COLORS.text_primary};")
        layout.addWidget(label)


def show_toast(parent: QWidget, text: str, tone: str = "info") -> None:
    toast = ToastMessage(text, tone, parent)
    toast.adjustSize()

    key = id(parent)
    stack = _ACTIVE_TOASTS.setdefault(key, [])
    stack.append(toast)
    x = max(16, parent.width() - toast.width() - 24)
    y = 16 + (len(stack) - 1) * (toast.height() + 8)
    toast.move(x, y)
    toast.show()
    fade_in(toast, duration=Motion.ULTRA_FAST)
    slide_in = QPropertyAnimation(toast, b"pos", toast)
    slide_in.setDuration(Motion.FAST)
    slide_in.setStartValue(QPoint(x + 20, y))
    slide_in.setEndValue(QPoint(x, y))
    slide_in.setEasingCurve(QEasingCurve.OutCubic)
    slide_in.start()
    toast._slide_anim = slide_in  # type: ignore[attr-defined]

    def _close_toast() -> None:
        fade = QPropertyAnimation(toast, b"windowOpacity", toast)
        fade.setDuration(Motion.ULTRA_FAST)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.finished.connect(toast.deleteLater)
        fade.finished.connect(lambda: _unstack(parent, toast))
        fade.start()
        toast._fade_anim = fade  # type: ignore[attr-defined]

    QTimer.singleShot(2400, _close_toast)


def _unstack(parent: QWidget, toast: ToastMessage) -> None:
    key = id(parent)
    stack = _ACTIVE_TOASTS.get(key, [])
    if toast in stack:
        stack.remove(toast)
    _reposition_toasts(parent)
    if not stack and key in _ACTIVE_TOASTS:
        _ACTIVE_TOASTS.pop(key, None)


def _reposition_toasts(parent: QWidget) -> None:
    key = id(parent)
    stack = _ACTIVE_TOASTS.get(key, [])
    for index, toast in enumerate(stack):
        target_y = 16 + index * (toast.height() + 8)
        if toast.y() == target_y:
            continue
        anim = QPropertyAnimation(toast, b"pos", toast)
        anim.setDuration(Motion.ULTRA_FAST)
        anim.setStartValue(toast.pos())
        anim.setEndValue(QPoint(toast.x(), target_y))
        anim.start()
        toast._move_anim = anim  # type: ignore[attr-defined]


def clear_layout(layout: QLayout, start_index: int = 0) -> None:
    while layout.count() > start_index:
        item = layout.takeAt(start_index)
        if item is None:
            break
        child_layout = item.layout()
        if child_layout is not None:
            clear_layout(child_layout, start_index=0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
