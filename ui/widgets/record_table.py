"""Read-only record lists backed by a model; editors keep their small item tables."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QByteArray,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QKeyEvent, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QTableWidgetItem,
    QWidget,
)

from ui.storage import submit_file
from ui.theme import COLORS
from ui.widgets.controls import SecondaryButton

EMPTY_INDEX = QModelIndex()


class RecordModel(QAbstractTableModel):
    def __init__(self, columns: int, parent: QWidget) -> None:
        super().__init__(parent)
        self.headers = [""] * columns
        self.cells: list[list[QTableWidgetItem | None]] = []

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = EMPTY_INDEX) -> int:
        return 0 if parent.isValid() else len(self.cells)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = EMPTY_INDEX) -> int:
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section]
        return None

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        cell = self.cells[index.row()][index.column()]
        if cell is None:
            return None
        if role == Qt.ItemDataRole.UserRole:
            text = cell.text()
            if self.headers[index.column()] in {"Preço", "Custo", "Margem", "Total", "Itens", "Unidades", "Disponível"}:
                try:
                    return float(text.replace(" €", "").replace("%", "").replace(" ", "").replace(",", "."))
                except ValueError:
                    return 0.0
            return text.casefold()
        if role == Qt.ItemDataRole.TextAlignmentRole and self.headers[index.column()] in {"Preço", "Custo", "Margem", "Total", "Itens", "Unidades", "Disponível"}:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if role == Qt.ItemDataRole.ToolTipRole:
            return cell.text()
        return cell.data(role)


class StatusDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        header = str(index.model().headerData(index.column(), Qt.Orientation.Horizontal))
        if header not in {"Estado", "Pagamento", "Pago"}:
            super().paint(painter, option, index)
            return
        text = str(index.data() or "")
        key = text.casefold()
        color = COLORS.info
        if key in {"pago", "sim", "pronta envio", "pronta para envio", "pronto"}:
            color = COLORS.success
        elif key in {"em producao", "em produção"}:
            color = COLORS.primary
        elif key in {"pendente", "não", "a aguardar"}:
            color = COLORS.warning
        elif key in {"cancelada", "entregue", "expedida"}:
            color = COLORS.text_secondary
        elif key in {"atrasada", "atrasado"}:
            color = COLORS.danger
            text = "! " + text
        background = QStyleOptionViewItem(option)
        self.initStyleOption(background, index)
        background.text = ""
        style = option.widget.style() if option.widget else None
        if style:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, background, painter, option.widget)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(10, 9, -10, -9)
        rect.setWidth(min(rect.width(), option.fontMetrics.horizontalAdvance(text) + 20))
        painter.setPen(Qt.PenStyle.NoPen)
        # QColor does not parse Qt's rgba() QSS syntax.
        tint = QColor(color)
        tint.setAlpha(36)
        painter.setBrush(tint)
        painter.drawRoundedRect(rect, 6, 6)
        painter.setPen(QColor(color))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


@dataclass(frozen=True)
class SelectedRecord:
    source_row: int

    def row(self) -> int:
        return self.source_row


class RecordTable(QTableView):
    itemSelectionChanged = Signal()

    def __init__(self, rows: int, columns: int) -> None:
        super().__init__()
        self._source = RecordModel(columns, self)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._source)
        self._proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self._proxy.setDynamicSortFilter(False)
        self.setModel(self._proxy)
        self.setItemDelegate(StatusDelegate(self))
        self.setAccessibleName("Lista de registos. Cabeçalhos permitem ordenar; Ctrl+C copia a seleção.")
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setMinimumSize(160, 180)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(44)
        self.horizontalHeader().setDefaultSectionSize(144)
        self.horizontalHeader().setMinimumSectionSize(72)
        self.horizontalHeader().setFixedHeight(44)
        self.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._column_menu)
        self.horizontalHeader().setToolTip("Clique para ordenar · botão direito para escolher colunas")
        self.setSortingEnabled(True)
        self._proxy.sort(-1)
        self.selectionModel().selectionChanged.connect(lambda _selected, _deselected: self.itemSelectionChanged.emit())
        self.selection_bar = QWidget(self)
        row = QHBoxLayout(self.selection_bar)
        row.setContentsMargins(0, 0, 0, 0)
        self.selection_label = QLabel()
        row.addWidget(self.selection_label)
        copy = SecondaryButton("Copiar selecionados")
        copy.clicked.connect(self.copy_selection)
        row.addWidget(copy)
        row.addStretch()
        self.selection_bar.hide()
        self.itemSelectionChanged.connect(self._selection_feedback)
        self.setRowCount(rows)

    def setHorizontalHeaderLabels(self, labels: list[str]) -> None:
        self._source.headers = labels
        self._source.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(labels) - 1)
        widths = {"Número": 156, "Encomenda": 156, "Cliente": 168, "Produto": 192, "SKU": 120, "Itens": 80,
                  "Estado": 132, "Total": 112, "Pago": 80, "Preço": 100, "Disponível": 104, "Produção": 128,
                  "Email": 208, "Telefone": 136, "NIF": 112, "Unidades": 88}
        for column, label in enumerate(labels):
            self.setColumnWidth(column, widths.get(label, 144))
            self.setColumnHidden(column, label in {"Tracking", "Custo", "Margem", "Morada", "Trabalho"})

    def rowCount(self) -> int:
        return self._source.rowCount()

    def setRowCount(self, rows: int) -> None:
        self._source.beginResetModel()
        self._source.cells = [[None] * len(self._source.headers) for _ in range(rows)]
        self._source.endResetModel()

    def setItem(self, row: int, column: int, item: QTableWidgetItem) -> None:
        self._source.cells[row][column] = item
        index = self._source.index(row, column)
        self._source.dataChanged.emit(index, index)

    def selectedItems(self) -> list[SelectedRecord]:
        return [SelectedRecord(self._proxy.mapToSource(index).row()) for index in self.selectionModel().selectedRows()]

    def selectRow(self, row: int) -> None:
        index = self._proxy.mapFromSource(self._source.index(row, 0))
        if index.isValid():
            super().selectRow(index.row())

    def blockSignals(self, block: bool) -> bool:
        if not block:
            self._proxy.invalidate()
        self.setUpdatesEnabled(not block)
        return super().blockSignals(block)

    def _selection_feedback(self) -> None:
        count = len(self.selectionModel().selectedRows())
        self.selection_label.setText(f"{count} registos selecionados")
        self.selection_bar.setVisible(count > 1)

    def copy_selection(self) -> None:
        rows = self.selectionModel().selectedRows()
        text = "\n".join("\t".join(str(self._proxy.index(index.row(), column).data() or "") for column in range(self._proxy.columnCount())) for index in rows)
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def remember_layout(self, path: Path) -> None:
        # Disk work happens in a serialized worker; Qt header access stays on the UI thread.
        self._layout_path = path
        self._layout_read = submit_file("read", path)
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(300)
        self._layout_timer.timeout.connect(self._save_layout)
        self._layout_poll = QTimer(self)
        self._layout_poll.setInterval(100)
        self._layout_poll.timeout.connect(self._restore_layout)
        self._layout_poll.start()
        self.horizontalHeader().sectionResized.connect(lambda _section, _before, _after: self._layout_timer.start())
        self.horizontalHeader().sortIndicatorChanged.connect(lambda _section, _order: self._layout_timer.start())

    def _restore_layout(self) -> None:
        if not self._layout_read.done():
            return
        self._layout_poll.stop()
        try:
            data = self._layout_read.result()
            state = data.get("header")
            if isinstance(state, str):
                self.horizontalHeader().restoreState(QByteArray.fromBase64(state.encode("ascii")))
        except (ValueError, OSError, UnicodeError):
            # Invalid presentation preferences must never prevent access to records.
            pass
        self._layout_timer.stop()

    def _save_layout(self) -> None:
        if self._layout_read.done():
            header = bytes(self.horizontalHeader().saveState().toBase64()).decode("ascii")
            submit_file("write", self._layout_path, {"header": header})

    def _column_menu(self, point: object) -> None:
        menu = QMenu(self)
        for column, label in enumerate(self._source.headers):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(not self.isColumnHidden(column))
            action.toggled.connect(lambda visible, col=column: self._toggle_column(col, visible))
        menu.exec(self.horizontalHeader().mapToGlobal(point))

    def _toggle_column(self, column: int, visible: bool) -> None:
        self.setColumnHidden(column, not visible)
        if hasattr(self, "_layout_timer"):
            self._layout_timer.start()
