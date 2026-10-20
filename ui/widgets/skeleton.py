from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, QRectF, QTimer
from PySide6.QtGui import QColor, QHideEvent, QLinearGradient, QPainter, QPaintEvent, QShowEvent
from PySide6.QtWidgets import QWidget

from ui.animations import reduced_motion
from ui.theme import COLORS


class Skeleton(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(72)
        self.clock = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.update)
        self.setAccessibleName("Operação em curso")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.clock.start()
        if not reduced_motion(self):
            self.timer.start()

    def hideEvent(self, event: QHideEvent) -> None:
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        phase = (self.clock.elapsed() % 1400) / 1400 if self.clock.isValid() else 0
        for y, ratio in ((0, 1.0), (24, 0.8), (48, 0.55)):
            rect = QRectF(0, y, self.width() * ratio, 12)
            gradient = QLinearGradient(self.width() * (phase * 2 - 1), 0, self.width() * phase * 2, 0)
            gradient.setColorAt(0, QColor(COLORS.surface_alt))
            gradient.setColorAt(0.5, QColor(COLORS.border_strong if not reduced_motion(self) else COLORS.surface_alt))
            gradient.setColorAt(1, QColor(COLORS.surface_alt))
            painter.setPen(QColor(COLORS.surface_alt))
            painter.setBrush(gradient)
            painter.drawRoundedRect(rect, 6, 6)
