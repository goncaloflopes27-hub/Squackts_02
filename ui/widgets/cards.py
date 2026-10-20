from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEasingCurve, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.animations import reduced_motion
from ui.theme import COLORS, RADIUS, SPACING
from ui.widgets.common import clear_layout
from ui.widgets.controls import AppCard, ElevatedCard, IconButton, PanelHeader, PrimaryButton, StatPill
from ui.widgets.flow_layout import FlowLayout
from ui.widgets.skeleton import Skeleton


class KPIWidget(AppCard):
    clicked = Signal()

    def __init__(self, label: str, value: str, delta: str, tone: str = "info") -> None:
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"{label}: {value}. Abrir lista correspondente.")
        self.setMinimumHeight(160)
        self.setMaximumHeight(180)
        layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        top = QLabel(label)
        top.setWordWrap(True)
        top.setStyleSheet(f"color:{COLORS.text_secondary}; font-size:12px;")
        layout.addWidget(top)
        self.value_label = QLabel(value)
        self.value_label.setMinimumHeight(44)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.value_label.setStyleSheet("font-size:28px; font-weight:600;")
        layout.addWidget(self.value_label)
        hint = QLabel(delta)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{COLORS.text_secondary}; font-size:12px;")
        layout.addWidget(hint)
        layout.addStretch()
        self._value = 0.0
        self._target = value
        self._counter = QVariantAnimation(self)
        self._counter.setDuration(600)
        self._counter.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._counter.valueChanged.connect(self._render_count)
        self._counter.finished.connect(lambda: self.value_label.setText(self._target))
        QTimer.singleShot(0, lambda: self.set_value(value))

    def set_value(self, value: str) -> None:
        self._counter.stop()
        self._target = value
        self.setAccessibleName(f"{self.findChildren(QLabel)[0].text()}: {value}. Abrir lista correspondente.")
        try:
            number = float(value.replace(" €", "").replace(" ", "").replace(",", "."))
        except ValueError:
            self.value_label.setText(value)
            return
        if reduced_motion(self):
            self.value_label.setText(value)
            self._value = number
            return
        self._counter.setStartValue(self._value)
        self._counter.setEndValue(number)
        self._counter.start()

    def _render_count(self, number: float) -> None:
        self._value = number
        # Interpolation is presentation only; the exact service-formatted target is restored at the end.
        text = f"{number:,.2f}".replace(",", " ").replace(".", ",") + " €" if "€" in self._target else str(round(number))
        self.value_label.setText(text)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)


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
        self.illustration = QSvgWidget()
        self.illustration.setFixedSize(128, 90)
        self.illustration.setAccessibleName("Ilustração de um pato em repouso")
        layout.addWidget(self.illustration)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size:18px; font-weight:720;")
        self.desc_label = QLabel(description)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet(f"color:{COLORS.text_secondary};")
        layout.addWidget(self.title_label)
        layout.addWidget(self.desc_label)
        self.action = PrimaryButton("Criar agora")
        self.action.hide()
        layout.addWidget(self.action, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        self._set_illustration(title)

    def set_content(self, title: str, description: str) -> None:
        self.title_label.setText(title)
        self.desc_label.setText(description)
        self._set_illustration(title)

    def _set_illustration(self, title: str) -> None:
        searching = title == "Sem resultados"
        filename = "empty-search.svg" if searching else "empty-sleep.svg"
        self.illustration.load(str(Path(__file__).parents[1] / "assets/illustrations" / filename))
        self.illustration.setAccessibleName("Pato à procura de resultados" if searching else "Pato em repouso")

    def set_action(self, text: str, callback: Callable[[], None]) -> None:
        self.action.setText(text)
        self.action.clicked.connect(callback)
        self.action.show()


class RichEmptyState(EmptyState):
    def __init__(self, title: str, description: str, cta_text: str = "Criar agora") -> None:
        super().__init__(title, description)
        layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        layout.addWidget(PrimaryButton(cta_text))


class DetailPanel(ElevatedCard):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setMinimumWidth(280)
        self.setMaximumWidth(480)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setObjectName("DetailPanel")
        self.setStyleSheet(
            f"QFrame#AppCard, QFrame#DetailPanel {{background:{COLORS.surface_elevated}; border:1px solid {COLORS.border_strong}; border-radius:{RADIUS.lg}px;}}"
        )
        panel_layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        panel_layout.setSpacing(SPACING.sm)
        panel_layout.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
        self.header = PanelHeader(title)
        panel_layout.addWidget(self.header)
        body = QWidget()
        self.content_layout = QVBoxLayout(body)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(SPACING.sm)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("QScrollArea {border:none; background:transparent;}")
        self.scroll_area.setWidget(body)
        panel_layout.addWidget(self.scroll_area, 1)

    def clear_content(self) -> None:
        clear_layout(self.content_layout)

    def add_content_widget(self, widget: QWidget) -> None:
        self.content_layout.addWidget(widget)


class KeyValueCard(AppCard):
    def __init__(self, title: str, entries: list[tuple[str, str]]) -> None:
        super().__init__(title)
        layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        for key, value in entries:
            layout.addWidget(InfoRow(key, value))


class InfoRow(QWidget):
    def __init__(self, key: str, value: str) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        left = QLabel(key)
        left.setStyleSheet(f"color:{COLORS.text_secondary}; font-size:12px;")
        right = QLabel(value)
        right.setStyleSheet("font-weight:650;")
        right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        right.setWordWrap(True)
        right.setTextFormat(Qt.TextFormat.PlainText)
        right.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right.setToolTip(value)
        right.setMinimumWidth(0)
        # Long Windows paths must wrap inside the card, not widen the whole page.
        right.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout.addWidget(left)
        layout.addWidget(right, 1)


class InfoGrid(AppCard):
    def __init__(self, title: str, rows: list[tuple[str, str]], columns: int = 2) -> None:
        super().__init__(title)
        wrapper = QWidget()
        grid = QGridLayout(wrapper)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(SPACING.md)
        grid.setVerticalSpacing(SPACING.sm)
        for index, (key, value) in enumerate(rows):
            row = index // columns
            col = index % columns
            block = AppCard()
            block_layout: QVBoxLayout = block.layout()  # type: ignore[assignment]
            k = QLabel(key)
            k.setStyleSheet(f"color:{COLORS.text_secondary};")
            v = QLabel(value)
            v.setWordWrap(True)
            v.setTextFormat(Qt.TextFormat.PlainText)
            v.setMinimumWidth(0)
            v.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            v.setToolTip(value)
            v.setStyleSheet("font-weight:700;")
            block_layout.addWidget(k)
            block_layout.addWidget(v)
            grid.addWidget(block, row, col)
        layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        layout.addWidget(wrapper)


class FormSection(AppCard):
    def __init__(self, title: str) -> None:
        super().__init__(title)


class Toolbar(QWidget):
    def __init__(self, *widgets: QWidget) -> None:
        super().__init__()
        self.setObjectName("Toolbar")
        self.setStyleSheet(
            f"QWidget#Toolbar {{background:{COLORS.surface}; border:1px solid {COLORS.border}; border-radius:{RADIUS.lg}px;}}"
        )
        layout = FlowLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.sm, SPACING.md, SPACING.sm)
        layout.setSpacing(SPACING.sm)
        for widget in widgets:
            layout.addWidget(widget)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)


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
        layout.addWidget(Skeleton(self))


class ActivityList(AppCard):
    def __init__(self, title: str, activities: list[tuple[str, str]]) -> None:
        super().__init__(title)
        layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        for when, what in activities:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(StatPill(when, "info"))
            description = QLabel(what)
            description.setWordWrap(True)
            description.setTextFormat(Qt.TextFormat.PlainText)
            row_layout.addWidget(description, 1)
            row_layout.addStretch(1)
            layout.addWidget(row)


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

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(COLORS.surface_alt))
        painter.setPen(QColor(COLORS.text_primary))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)
        super().paintEvent(event)
