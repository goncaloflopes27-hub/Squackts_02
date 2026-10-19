from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.theme import COLORS, RADIUS, SPACING
from ui.widgets.common import clear_layout
from ui.widgets.controls import AppCard, ElevatedCard, IconButton, PanelHeader, PrimaryButton, StatPill


class KPIWidget(AppCard):
    def __init__(self, label: str, value: str, delta: str, tone: str = "info") -> None:
        super().__init__()
        layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        top = QLabel(label)
        top.setStyleSheet(f"color:{COLORS.text_secondary}; font-size:12px;")
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
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"min-width:34px; min-height:34px; max-width:34px; max-height:34px;"
            f"border-radius:{RADIUS.sm}px; background:{COLORS.surface_alt}; color:{COLORS.text_secondary}; font-size:16px;"
        )
        layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignLeft)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size:18px; font-weight:720;")
        self.desc_label = QLabel(description)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet(f"color:{COLORS.text_secondary};")
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
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
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
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)
        super().paintEvent(event)
