from __future__ import annotations

from PySide6.QtCore import QEventLoop, Qt
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

from ui.theme import COLORS, app_stylesheet


class StartupSplash(QWidget):
    """Actual startup milestones, without an artificial loading delay."""
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(400, 240)
        self.setObjectName("StartupSplash")
        self.setStyleSheet(app_stylesheet() + f"QWidget#StartupSplash {{background:{COLORS.surface}; border:1px solid {COLORS.border}; border-radius:16px;}}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        title = QLabel(f'Squack<span style="color:{COLORS.primary}">TS</span>')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:36px; font-weight:600;")
        layout.addWidget(title)
        caption = QLabel("O teu atelier, organizado.")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setStyleSheet(f"color:{COLORS.text_secondary};")
        layout.addWidget(caption)
        layout.addStretch()
        self.message = QLabel("A preparar o espaço de trabalho…")
        self.message.setStyleSheet(f"font-size:12px; color:{COLORS.text_secondary};")
        layout.addWidget(self.message)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet(f"QProgressBar {{border:0; background:{COLORS.border};}} QProgressBar::chunk {{background:{COLORS.brand_red};}}")
        layout.addWidget(self.progress)

    def advance(self, value: int, message: str) -> None:
        self.message.setText(message)
        self.progress.setValue(value)
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
