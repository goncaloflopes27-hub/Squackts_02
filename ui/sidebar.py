from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRect, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QButtonGroup, QFrame, QLabel, QVBoxLayout, QWidget

from config import APP_DISPLAY_VERSION
from ui.animations import reduced_motion
from ui.components import SidebarButton
from ui.theme import COLORS, SPACING

PAGES = (
    ("dashboard", "Hoje"),
    ("orders", "Encomendas"),
    ("products", "Catálogo"),
    ("clients", "Clientes"),
    ("production", "Produção"),
    ("system", "Sistema"),
)


class Sidebar(QFrame):
    def __init__(self, on_select: Callable[[str], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setStyleSheet(
            f"QFrame#Sidebar {{background:{COLORS.surface}; border-right:1px solid {COLORS.border};}}"
        )
        self._compact = False
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, SidebarButton] = {}
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 24, 12, 16)
        self._layout.setSpacing(6)
        self.brand = QLabel(f'Squack<span style="color:{COLORS.primary}">TS</span>')
        self.brand.setStyleSheet(f"font-size:24px; font-weight:600; color:{COLORS.text_primary};")
        self.brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self.brand)
        self.tagline = QLabel("O TEU ATELIER")
        self.tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tagline.setStyleSheet(f"font-size:12px; color:{COLORS.text_secondary};")
        self._layout.addWidget(self.tagline)
        self._layout.addSpacing(SPACING.xl)
        self.section = QLabel("OPERAÇÃO")
        self.section.setStyleSheet(f"font-size:12px; color:{COLORS.text_muted}; padding:0 10px 6px;")
        self._layout.addWidget(self.section)
        for number, (key, label) in enumerate(PAGES, start=1):
            button = SidebarButton(label)
            button.setIcon(QIcon(str(Path(__file__).parent / "icons" / f"nav-{key}.svg")))
            button.setIconSize(QSize(20, 20))
            button.setObjectName(f"Nav_{key}")
            button.setToolTip(f"{label} · Alt+{number}")
            button.setAccessibleName(label)
            button.clicked.connect(lambda _checked=False, page_key=key: on_select(page_key))
            self._group.addButton(button)
            self._buttons[key] = button
            self._layout.addWidget(button)
        self._layout.addStretch(1)
        self.footer = QLabel(f"Local · v{APP_DISPLAY_VERSION}")
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.footer.setStyleSheet(f"color:{COLORS.text_muted}; font-size:12px;")
        self._layout.addWidget(self.footer)
        self._width_animation = QPropertyAnimation(self, b"sidebarWidth", self)
        self._width_animation.setDuration(220)
        self._width_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.indicator = QFrame(self)
        self.indicator.setStyleSheet(f"background:{COLORS.surface_elevated}; border:1px solid {COLORS.border}; border-left:3px solid {COLORS.brand_red}; border-radius:8px;")
        self.indicator.lower()
        self._indicator_animation = QPropertyAnimation(self.indicator, b"geometry", self)
        self._indicator_animation.setDuration(200)
        self._indicator_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.set_compact(False)
        self.set_current("dashboard")

    def set_current(self, key: str) -> None:
        if key in self._buttons:
            self._buttons[key].setChecked(True)
            button = self._buttons[key]
            target = QRect(button.pos(), button.size())
            self._indicator_animation.stop()
            if self.isVisible() and not reduced_motion(self):
                self._indicator_animation.setStartValue(self.indicator.geometry())
                self._indicator_animation.setEndValue(target)
                self._indicator_animation.start()
            else:
                self.indicator.setGeometry(target)

    def set_compact(self, compact: bool) -> None:
        changed = self._compact != compact
        self._compact = compact
        target_width = 72 if compact else 240
        self._width_animation.stop()
        if changed and self.isVisible() and not reduced_motion(self):
            self._width_animation.setStartValue(self.width())
            self._width_animation.setEndValue(target_width)
            self._width_animation.start()
        else:
            self.setFixedWidth(target_width)
        self._layout.setContentsMargins(8 if compact else 12, 24, 8 if compact else 12, 16)
        self.brand.setText("ST" if compact else f'Squack<span style="color:{COLORS.primary}">TS</span>')
        self.tagline.setVisible(not compact)
        self.section.setVisible(not compact)
        self.footer.setText(f"v{APP_DISPLAY_VERSION}" if compact else f"Local · v{APP_DISPLAY_VERSION}")
        for key, label in PAGES:
            button = self._buttons[key]
            button.setText("" if compact else label)
            button.setProperty("compact", compact)
            button.style().unpolish(button)
            button.style().polish(button)
            button.setFixedHeight(44)

    def _get_sidebar_width(self) -> int:
        return self.width()

    def _set_sidebar_width(self, value: int) -> None:
        self.setFixedWidth(value)

    sidebarWidth = Property(int, _get_sidebar_width, _set_sidebar_width)
