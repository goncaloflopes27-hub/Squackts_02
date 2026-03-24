from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QAbstractButton, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.components import IconButton, PrimaryButton, SearchInput, SecondaryButton, StatPill
from ui.theme import COLORS, RADIUS, SPACING


class TopBar(QFrame):
    search_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(104)
        self.setStyleSheet(
            f"QFrame {{background:{COLORS.surface}; border-bottom:1px solid {COLORS.border};}}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.sm, SPACING.lg, SPACING.sm)
        layout.setSpacing(SPACING.sm)

        self.title = QLabel("Centro de controlo")
        self.title.setStyleSheet("font-size: 18px; font-weight: 780; letter-spacing: 0.2px;")
        self.subtitle = QLabel("Visão geral operacional")
        self.subtitle.setStyleSheet(f"font-size:12px; color:{COLORS.text_secondary};")
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.addWidget(self.title)
        title_row.addWidget(StatPill("Ao vivo", "info"))
        title_row.addStretch(1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)
        left_layout.addLayout(title_row)
        left_layout.addWidget(self.subtitle)
        layout.addWidget(left)
        layout.addSpacing(12)

        self.search = SearchInput("Pesquisar...")
        self.search.setMinimumWidth(460)
        self.search.setStyleSheet(
            self.search.styleSheet()
            + f"QLineEdit {{background:{COLORS.surface_alt}; border:1px solid {COLORS.border}; border-radius:{RADIUS.md}px;}}"
            + f"QLineEdit:focus {{border:1px solid {COLORS.primary}; background:{COLORS.surface_elevated};}}"
        )
        self.search.textChanged.connect(self.search_changed.emit)
        layout.addWidget(self.search)

        layout.addStretch(1)
        alerts_btn = IconButton("Alertas")
        alerts_btn.setToolTip("Notificações e alertas operacionais")
        prefs_btn = IconButton("Preferências")
        prefs_btn.setToolTip("Preferências da aplicação")
        layout.addWidget(alerts_btn)
        layout.addWidget(prefs_btn)

        self.secondary_action = SecondaryButton("Ação secundária")
        self.secondary_action.hide()
        self.primary_action = PrimaryButton("Ação principal")
        layout.addWidget(self.secondary_action)
        layout.addWidget(self.primary_action)

    def set_context(
        self,
        *,
        title: str,
        subtitle: str,
        search_placeholder: str,
        primary_action_label: str,
        primary_action: Callable[[], None] | None,
        secondary_action_label: str | None = None,
        secondary_action: Callable[[], None] | None = None,
    ) -> None:
        self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.search.setPlaceholderText(search_placeholder)
        self.search.clear()

        self._rebind_button(self.primary_action, primary_action_label, primary_action)
        self.primary_action.setToolTip(primary_action_label)
        if secondary_action_label and secondary_action:
            self.secondary_action.setVisible(True)
            self._rebind_button(self.secondary_action, secondary_action_label, secondary_action)
            self.secondary_action.setToolTip(secondary_action_label)
        else:
            self.secondary_action.setVisible(False)

    def _rebind_button(self, button: QAbstractButton, label: str, callback: Callable[[], None] | None) -> None:
        button.setText(label)
        try:
            button.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        if callback is not None:
            button.clicked.connect(callback)
