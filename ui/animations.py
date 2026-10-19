from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QTimer
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QWidget


class Motion:
    ULTRA_FAST = 120
    FAST = 180
    NORMAL = 240
    SLOW = 320


def reduced_motion(widget: QWidget | None = None) -> bool:
    if widget is not None and widget.window().property("reduceMotion") is not None:
        return bool(widget.window().property("reduceMotion"))
    app = QApplication.instance()
    return bool(app and app.property("reduceMotion"))


def _opacity_animation(widget: QWidget, start: float, end: float, duration: int) -> QPropertyAnimation:
    effect = widget.graphicsEffect()
    # A QWidget owns a single graphics effect. Preserve an existing shadow.
    if effect is not None and not isinstance(effect, QGraphicsOpacityEffect):
        animation = QPropertyAnimation(widget, b"windowOpacity", widget)
        animation.setDuration(0)
        animation.setStartValue(1.0)
        animation.setEndValue(1.0)
        return animation
    if effect is None:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOpacity(start)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(0 if reduced_motion(widget) else duration)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    return animation


def fade_in(widget: QWidget, duration: int = Motion.FAST) -> QPropertyAnimation:
    animation = _opacity_animation(widget, 1.0 if reduced_motion(widget) else 0.0, 1.0, duration)
    widget._fade_animation = animation  # type: ignore[attr-defined]
    animation.start()
    return animation


def slide_and_fade_in(widget: QWidget, x_offset: int = 18, duration: int = Motion.NORMAL) -> QParallelAnimationGroup:
    # Layouts own widget geometry; animating pos() fights the layout manager.
    group = QParallelAnimationGroup(widget)
    group.addAnimation(_opacity_animation(widget, 1.0 if reduced_motion(widget) else 0.0, 1.0, duration))
    widget._open_animation = group  # type: ignore[attr-defined]
    group.start()
    return group


def animate_dialog_open(dialog: QWidget) -> QParallelAnimationGroup:
    return slide_and_fade_in(dialog, x_offset=0, duration=Motion.FAST)


def animate_dialog_close(dialog: QWidget, on_finished: Callable[[], None]) -> QPropertyAnimation:
    animation = _opacity_animation(dialog, 1.0, 0.0, Motion.ULTRA_FAST)
    dialog._close_animation = animation  # type: ignore[attr-defined]
    if reduced_motion(dialog):
        QTimer.singleShot(0, on_finished)
    else:
        animation.finished.connect(on_finished)
    animation.start()
    return animation
