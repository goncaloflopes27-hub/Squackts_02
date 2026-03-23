from __future__ import annotations

from collections.abc import Callable
from typing import cast

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QParallelAnimationGroup
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget


class Motion:
    ULTRA_FAST = 120
    FAST = 180
    NORMAL = 240
    SLOW = 320


_ANIMATION_REF: set[object] = set()


def _keep_alive(animation: object) -> None:
    _ANIMATION_REF.add(animation)
    if hasattr(animation, "finished"):
        finished = cast(object, getattr(animation, "finished"))
        try:
            finished.connect(lambda a=animation: _ANIMATION_REF.discard(a))
        except Exception:
            pass


def _ensure_opacity_effect(widget: QWidget) -> QGraphicsOpacityEffect:
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    return effect


def fade_in(widget: QWidget, duration: int = Motion.FAST) -> QPropertyAnimation:
    effect = _ensure_opacity_effect(widget)
    effect.setOpacity(0.0)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.OutCubic)
    animation.start()
    _keep_alive(animation)
    return animation


def slide_and_fade_in(widget: QWidget, x_offset: int = 18, duration: int = Motion.NORMAL) -> QParallelAnimationGroup:
    start_pos = widget.pos() + QPoint(x_offset, 0)
    end_pos = widget.pos()

    move_anim = QPropertyAnimation(widget, b"pos", widget)
    move_anim.setDuration(duration)
    move_anim.setStartValue(start_pos)
    move_anim.setEndValue(end_pos)
    move_anim.setEasingCurve(QEasingCurve.OutQuart)

    effect = _ensure_opacity_effect(widget)
    effect.setOpacity(0.0)
    opacity_anim = QPropertyAnimation(effect, b"opacity", widget)
    opacity_anim.setDuration(duration)
    opacity_anim.setStartValue(0.0)
    opacity_anim.setEndValue(1.0)
    opacity_anim.setEasingCurve(QEasingCurve.InOutCubic)

    group = QParallelAnimationGroup(widget)
    group.addAnimation(move_anim)
    group.addAnimation(opacity_anim)
    group.start()
    _keep_alive(group)
    return group


def animate_dialog_open(dialog: QWidget) -> QParallelAnimationGroup:
    return slide_and_fade_in(dialog, x_offset=0, duration=Motion.FAST)


def animate_dialog_close(dialog: QWidget, on_finished: Callable[[], None]) -> QPropertyAnimation:
    effect = _ensure_opacity_effect(dialog)
    animation = QPropertyAnimation(effect, b"opacity", dialog)
    animation.setDuration(Motion.ULTRA_FAST)
    animation.setStartValue(effect.opacity())
    animation.setEndValue(0.0)
    animation.setEasingCurve(QEasingCurve.InOutCubic)
    animation.finished.connect(on_finished)
    animation.start()
    _keep_alive(animation)
    return animation
