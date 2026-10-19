from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.components import IconButton, PrimaryButton, SearchInput, SecondaryButton
from ui.theme import COLORS, SPACING


class TopBar(QFrame):
    search_changed = Signal(str)
    alerts_requested = Signal()
    preferences_requested = Signal()
    menu_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(124)
        self.setStyleSheet(
            f"QFrame#TopBar {{background:{COLORS.surface}; border-bottom:1px solid {COLORS.border};}}"
        )
        self._primary_callback: Callable[[], None] | None = None
        self._secondary_callback: Callable[[], None] | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, 12, SPACING.lg, 12)
        root.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(SPACING.sm)
        self.menu_button = IconButton("Menu")
        self.menu_button.setToolTip("Expandir ou recolher navegação")
        self.menu_button.clicked.connect(self.menu_requested.emit)
        row.addWidget(self.menu_button)
        self.title = QLabel("Painel")
        self.title.setStyleSheet("font-size:18px; font-weight:700;")
        row.addWidget(self.title)
        self.subtitle = QLabel("")
        self.subtitle.setStyleSheet(f"font-size:12px; color:{COLORS.text_secondary};")
        row.addWidget(self.subtitle)
        row.addStretch(1)
        self.alerts_button = IconButton("Alertas")
        self.alerts_button.setToolTip("Ver pendências operacionais no Painel")
        self.alerts_button.clicked.connect(self.alerts_requested.emit)
        row.addWidget(self.alerts_button)
        self.preferences_button = IconButton("Preferências")
        self.preferences_button.clicked.connect(self.preferences_requested.emit)
        row.addWidget(self.preferences_button)
        self.secondary_action = SecondaryButton("Atualizar")
        self.secondary_action.clicked.connect(self._run_secondary)
        row.addWidget(self.secondary_action)
        self.primary_action = PrimaryButton("Atualizar")
        self.primary_action.clicked.connect(self._run_primary)
        row.addWidget(self.primary_action)
        root.addLayout(row)
        self.search = SearchInput("Pesquisar…")
        self.search.setObjectName("ContextSearch")
        self.search.setToolTip("Pesquisar nesta página · Ctrl+K")
        self.search.textChanged.connect(self.search_changed.emit)
        root.addWidget(self.search)

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
        search_text: str = "",
        search_enabled: bool = True,
    ) -> None:
        self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.search.setPlaceholderText(search_placeholder)
        self.search.setAccessibleName(search_placeholder)
        self.search.setEnabled(search_enabled)
        with QSignalBlocker(self.search):
            self.search.setText(search_text)
        self._primary_callback = primary_action
        self.primary_action.setText(primary_action_label)
        self.primary_action.setAccessibleName(primary_action_label)
        self.primary_action.setEnabled(primary_action is not None)
        self._secondary_callback = secondary_action
        self.secondary_action.setVisible(bool(secondary_action_label and secondary_action))
        self.secondary_action.setText(secondary_action_label or "Atualizar")

    def set_compact(self, compact: bool) -> None:
        self.subtitle.setVisible(not compact)
        self.preferences_button.setText("Opções" if compact else "Preferências")

    def _run_primary(self) -> None:
        if self._primary_callback:
            self._primary_callback()

    def _run_secondary(self) -> None:
        if self._secondary_callback:
            self._secondary_callback()
