"""Wrap filter/action controls at their natural size on smaller work areas."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QWidget


class FlowLayout(QLayout):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._items[index] if 0 <= index < self.count() else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        return self._items.pop(index) if 0 <= index < self.count() else None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        left, top, right, bottom = margins.left(), margins.top(), margins.right(), margins.bottom()
        return size + QSize(left + right, top + bottom)

    def _arrange(self, rect: QRect, apply: bool) -> int:
        margins = self.contentsMargins()
        left, top, right, bottom = margins.left(), margins.top(), margins.right(), margins.bottom()
        area = rect.adjusted(left, top, -right, -bottom)
        x, y, row_height = area.x(), area.y(), 0
        spacing = max(0, self.spacing())
        for item in self._items:
            if item.isEmpty():
                continue
            size = item.sizeHint()
            size.setWidth(min(size.width(), area.width()))
            if x + size.width() > area.right() + 1 and row_height:
                x, y = area.x(), y + row_height + spacing
                row_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), size))
            x += size.width() + spacing
            row_height = max(row_height, size.height())
        return y + row_height - rect.y() + bottom
