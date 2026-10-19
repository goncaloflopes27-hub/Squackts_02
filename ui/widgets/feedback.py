from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ui.animations import Motion, fade_in
from ui.theme import COLORS, RADIUS

_ACTIVE_TOASTS: dict[int, list[ToastMessage]] = {}


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
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setStyleSheet(f"color:{COLORS.text_primary};")
        layout.addWidget(label)


def show_toast(parent: QWidget, text: str, tone: str = "info") -> None:
    """A parent-owned timer cannot outlive its toast or call deleted Qt objects."""
    toast = ToastMessage(text, tone, parent)
    toast.setAccessibleName(text)
    toast.setMaximumWidth(max(220, min(520, parent.width() - 32)))
    toast.adjustSize()
    key = id(parent)
    stack = _ACTIVE_TOASTS.setdefault(key, [])
    stack.append(toast)
    parent.destroyed.connect(lambda _obj=None, item_key=key: _ACTIVE_TOASTS.pop(item_key, None))
    _reposition_toasts(parent)
    toast.show()
    toast.raise_()
    fade_in(toast, duration=Motion.ULTRA_FAST)
    timer = QTimer(toast)
    timer.setSingleShot(True)

    def close_toast() -> None:
        current = _ACTIVE_TOASTS.get(key, [])
        if toast in current:
            current.remove(toast)
        toast.hide()
        toast.deleteLater()
        _reposition_toasts(parent)
        if not current:
            _ACTIVE_TOASTS.pop(key, None)

    timer.timeout.connect(close_toast)
    timer.start(6000 if tone in {"danger", "warning"} else 3500)


def _reposition_toasts(parent: QWidget) -> None:
    y = 16
    for toast in _ACTIVE_TOASTS.get(id(parent), []):
        toast.move(max(16, parent.width() - toast.width() - 24), y)
        y += toast.height() + 8
