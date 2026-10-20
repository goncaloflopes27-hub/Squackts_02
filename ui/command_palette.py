"""Keyboard-first navigation using the existing page search and actions."""
from __future__ import annotations

from collections.abc import Callable
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QListWidget, QVBoxLayout, QWidget

from ui.components import SearchInput
from ui.sidebar import PAGES
from ui.theme import COLORS, SPACING


class CommandPalette(QDialog):
    def __init__(self, navigate: Callable[[str, str], None], create: Callable[[], None], parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Comandos rápidos")
        self.setModal(True)
        self.resize(560, 420)
        self.navigate = navigate
        self.create_order = create
        self.callbacks: list[Callable[[], None]] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        title = QLabel("O que queres fazer?")
        title.setStyleSheet("font-size:20px; font-weight:600;")
        layout.addWidget(title)
        self.search = SearchInput("Ir para uma página ou pesquisar…")
        self.search.setToolTip("Escreve um nome ou número · Enter para abrir · Esc para sair")
        layout.addWidget(self.search)
        self.results = QListWidget()
        self.results.setAccessibleName("Comandos e destinos de pesquisa")
        self.results.setStyleSheet(f"QListWidget {{background:{COLORS.surface}; border:none;}} QListWidget::item {{padding:12px; border-radius:8px;}} QListWidget::item:selected {{background:{COLORS.overlay_soft}; color:{COLORS.text_primary};}}")
        layout.addWidget(self.results, 1)
        hint = QLabel("↑ ↓ escolher     Enter abrir     Esc fechar")
        hint.setStyleSheet(f"color:{COLORS.text_secondary}; font-size:12px;")
        layout.addWidget(hint)
        self.search.textChanged.connect(self._populate)
        self.search.returnPressed.connect(self._activate)
        self.results.itemActivated.connect(lambda _item: self._activate())
        self._populate("")
        self.search.setFocus()

    def _populate(self, text: str) -> None:
        self.results.clear()
        self.callbacks.clear()
        query = text.strip()
        for key, label in PAGES:
            if not query or query.casefold() in label.casefold():
                self.results.addItem(f"Ir para {label}")
                self.callbacks.append(partial(self.navigate, key, ""))
        if not query or "nova encomenda".startswith(query.casefold()):
            self.results.addItem("Criar nova encomenda    Ctrl+N")
            self.callbacks.append(self.create_order)
        if query:
            for key, label in (("orders", "encomendas"), ("clients", "clientes"), ("products", "catálogo")):
                self.results.addItem(f"Pesquisar «{query}» em {label}")
                self.callbacks.append(partial(self.navigate, key, query))
        self.results.setCurrentRow(0)

    def keyPressEvent(self, event: object) -> None:
        from PySide6.QtGui import QKeyEvent
        if isinstance(event, QKeyEvent) and event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            delta = 1 if event.key() == Qt.Key.Key_Down else -1
            self.results.setCurrentRow(max(0, min(self.results.count() - 1, self.results.currentRow() + delta)))
            return
        super().keyPressEvent(event)

    def _activate(self) -> None:
        row = self.results.currentRow()
        if 0 <= row < len(self.callbacks):
            callback = self.callbacks[row]
            self.accept()
            callback()
