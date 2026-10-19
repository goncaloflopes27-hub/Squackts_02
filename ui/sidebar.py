from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QButtonGroup, QFrame, QLabel, QVBoxLayout, QWidget

from config import APP_VERSION
from ui.components import SidebarButton
from ui.theme import COLORS, SPACING

PAGES = (
    ("dashboard", "Painel"),
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
        self._layout.setContentsMargins(16, 24, 16, 16)
        self._layout.setSpacing(6)
        self.brand = QLabel("SquackTS")
        self.brand.setStyleSheet(f"font-size:18px; font-weight:700; color:{COLORS.text_primary};")
        self.brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self.brand)
        self.tagline = QLabel("PRINT ON DEMAND")
        self.tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tagline.setStyleSheet(f"font-size:10px; color:{COLORS.text_secondary};")
        self._layout.addWidget(self.tagline)
        self._layout.addSpacing(SPACING.xl)
        self.section = QLabel("OPERAÇÃO")
        self.section.setStyleSheet(f"font-size:10px; color:{COLORS.text_muted}; padding:0 10px 6px;")
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
        self.footer = QLabel(f"Local · v{APP_VERSION}")
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.footer.setStyleSheet(f"color:{COLORS.text_muted}; font-size:11px;")
        self._layout.addWidget(self.footer)
        self.set_compact(False)
        self.set_current("dashboard")

    def set_current(self, key: str) -> None:
        if key in self._buttons:
            self._buttons[key].setChecked(True)

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.setFixedWidth(76 if compact else 224)
        self._layout.setContentsMargins(10 if compact else 16, 24, 10 if compact else 16, 16)
        self.brand.setText("ST" if compact else "SquackTS")
        self.tagline.setVisible(not compact)
        self.section.setVisible(not compact)
        self.footer.setText(f"v{APP_VERSION}" if compact else f"Local · v{APP_VERSION}")
        for key, label in PAGES:
            button = self._buttons[key]
            button.setText("" if compact else label)
            button.setProperty("compact", compact)
            button.style().unpolish(button)
            button.style().polish(button)
            button.setFixedHeight(44)
