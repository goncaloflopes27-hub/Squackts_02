from __future__ import annotations

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QSizePolicy,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ui.theme import COLORS, RADIUS


class _ColumnEditor(QStyledItemDelegate):
    def __init__(self, columns: set[int], parent: QWidget) -> None:
        super().__init__(parent)
        self.columns = columns

    # Qt accepts a null editor to disallow editing; the PySide stub omits None.
    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget | None:  # type: ignore[override]
        return super().createEditor(parent, option, index) if index.column() in self.columns else None


class DataTable(QTableWidget):
    def __init__(self, rows: int, columns: int) -> None:
        super().__init__(rows, columns)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAccessibleName("Lista de registos")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(160)
        self.setMinimumHeight(140)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setCornerButtonEnabled(False)
        self.horizontalHeader().setDefaultSectionSize(128)
        self.horizontalHeader().setMinimumSectionSize(64)
        self.horizontalHeader().setFixedHeight(44)
        self.verticalHeader().setDefaultSectionSize(44)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(
            f"QTableWidget {{border-radius:{RADIUS.lg}px;}}"
            f"QTableWidget::item {{padding: 9px 12px; border-bottom:1px solid {COLORS.border};}}"
            f"QTableWidget::item:selected {{background:{COLORS.overlay_soft}; color:{COLORS.text_primary};}}"
        )

    def setItem(self, row: int, column: int, item: QTableWidgetItem) -> None:
        header = self.horizontalHeaderItem(column)
        if header and header.text() in {"Preço", "Custo", "Margem", "Total", "Total item", "Itens", "Qtd", "Unidades", "Disponível"}:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        super().setItem(row, column, item)

    def set_editable_columns(self, columns: set[int]) -> None:
        self.setItemDelegate(_ColumnEditor(set(columns), self))
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
            if columns else QAbstractItemView.EditTrigger.NoEditTriggers
        )
