from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.components import AppCard, SidebarButton, StatPill
from ui.theme import COLORS, SPACING


class Sidebar(QFrame):
    def __init__(self, on_select: Callable[[str], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(272)
        self.setStyleSheet(
            f"QFrame {{background:{COLORS.surface}; border-right:1px solid {COLORS.border};}}"
        )
        self._on_select = on_select
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.lg, SPACING.md, SPACING.md)
        layout.setSpacing(SPACING.md)

        brand_card = AppCard()
        brand_card.setStyleSheet(
            f"QFrame#AppCard {{background:{COLORS.surface_elevated}; border:1px solid {COLORS.border_strong}; border-radius:14px;}}"
        )
        brand_layout = brand_card.layout()
        assert isinstance(brand_layout, QVBoxLayout)
        brand_layout.setContentsMargins(12, 12, 12, 12)
        brand_layout.setSpacing(4)
        badge = QLabel("S")
        badge.setFixedSize(26, 26)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"background:{COLORS.primary}; color:white; border-radius:13px; font-weight:760;"
        )
        brand_layout.addWidget(badge)
        brand = QLabel("Squackts POD")
        brand.setStyleSheet(f"font-size:18px; font-weight:780; color:{COLORS.text_primary};")
        brand_layout.addWidget(brand)
        subtitle = QLabel("Console Operacional")
        subtitle.setStyleSheet(f"font-size:12px; color:{COLORS.text_secondary};")
        brand_layout.addWidget(subtitle)
        layout.addWidget(brand_card)
        section_label = QLabel("Navegação")
        section_label.setStyleSheet(f"font-size:11px; color:{COLORS.text_muted}; font-weight:700;")
        layout.addWidget(section_label)

        pages = [
            ("dashboard", "Painel"),
            ("orders", "Encomendas"),
            ("products", "Catálogo"),
            ("clients", "Clientes"),
            ("production", "Produção"),
            ("system", "Sistema"),
        ]
        for index, (key, label) in enumerate(pages):
            button = SidebarButton(label)
            button.clicked.connect(lambda checked=False, page_key=key: self._on_select(page_key))
            self._group.addButton(button)
            layout.addWidget(button)
            if index == 0:
                button.setChecked(True)

        layout.addSpacing(SPACING.xs)
        layout.addStretch(1)
        footer = QHBoxLayout()
        footer.addWidget(StatPill("Ativo", "ok"))
        version = QLabel("Build local • v1")
        version.setStyleSheet(f"color:{COLORS.text_muted};")
        footer.addWidget(version)
        footer.addStretch(1)
        layout.addLayout(footer)
