from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QLabel,
    QLayout,
    QWidget,
)

CONTROL_HEIGHT = 40


def _caption(text: str, field: QWidget) -> QLabel:
    label = QLabel(text)
    label.setBuddy(field)
    field.setAccessibleName(text)
    return label


def apply_soft_shadow(widget: QWidget, *, blur: float = 28.0, y_offset: int = 8, alpha: int = 72) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    effect.setColor(QColor(10, 15, 30, alpha))
    widget.setGraphicsEffect(effect)


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
