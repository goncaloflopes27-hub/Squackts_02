"""An unsent form snapshot, independent of commercial order records."""
from __future__ import annotations

from concurrent.futures import Future
from copy import deepcopy
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, QObject, QTimer
from PySide6.QtWidgets import QLabel, QVBoxLayout

from ui.dialogs.order_editor import OrderEditorDialog
from ui.storage import submit_file
from ui.theme import COLORS
from ui.widgets.controls import SecondaryButton


class OrderDraft(QObject):
    def __init__(self, editor: OrderEditorDialog, path: Path) -> None:
        super().__init__(editor)
        self.editor = editor
        self.path = path
        self.closed = False
        self.restoring = False
        self.recoverable: dict[str, Any] = {}
        self.label = QLabel("Rascunho local: a preparar…")
        self.label.setWordWrap(True)
        self.label.setStyleSheet(f"color:{COLORS.text_secondary}; font-size:12px;")
        self.recover = SecondaryButton("Retomar rascunho anterior")
        self.recover.hide()
        root = editor.layout()
        assert isinstance(root, QVBoxLayout)
        root.insertWidget(1, self.label)
        root.insertWidget(2, self.recover)
        self.recover.clicked.connect(self._restore)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(800)
        self.timer.timeout.connect(self._save)
        self.read: Future[dict[str, Any]] | None = submit_file("read", path)
        self.write: Future[dict[str, Any]] | None = None
        self.poll = QTimer(self)
        self.poll.setInterval(100)
        self.poll.timeout.connect(self._poll)
        self.poll.start()
        self.changed = False
        self.last = self._snapshot()
        # This timer also captures changes to the in-memory item buffer.
        self.scan = QTimer(self)
        self.scan.setInterval(400)
        self.scan.timeout.connect(self._detect_changes)
        self.scan.start()
        editor.finished.connect(self._finish)

    def _snapshot(self) -> dict[str, Any]:
        e = self.editor
        return {"format": 1, "client": e.client_combo.input.currentText(), "status": e.status.input.currentData(),
                "payment": e.payment.input.currentIndex(), "shipping": e.shipping.value(),
                "tracking": e.tracking.text(), "notes": e.notes.text(), "items": deepcopy(e.items_buffer),
                "deadline_enabled": e.has_deadline.isChecked(), "deadline": e.deadline.date().toString("yyyy-MM-dd"),
                "request_key": e._idempotency_key}

    def _detect_changes(self) -> None:
        if self.closed or self.restoring:
            return
        snapshot = self._snapshot()
        if snapshot != self.last:
            self.changed = True
            self.last = snapshot
            self.timer.start()

    def _save(self) -> None:
        if not self.closed and self.changed:
            self.write = submit_file("write", self.path, self._snapshot())
            self.label.setText("A guardar rascunho local…")

    def _poll(self) -> None:
        if self.read is not None and self.read.done():
            try:
                data = self.read.result()
                if data.get("format") == 1:
                    self.recoverable = data
                    self.recover.show()
                    self.label.setText("Existe um rascunho anterior. Podes retomá-lo ou começar de novo.")
                else:
                    self.label.setText("As alterações ficam guardadas neste computador, sem criar uma encomenda.")
            except (ValueError, OSError):
                self.label.setText("Não foi possível ler o rascunho anterior. Podes continuar a preencher.")
            self.read = None
        if self.write is not None and self.write.done():
            try:
                self.write.result()
                self.label.setText("Rascunho local guardado · a encomenda só é criada ao Guardar.")
            except (ValueError, OSError):
                self.label.setText("Não foi possível guardar o rascunho local. Mantém este formulário aberto.")
            self.write = None

    def _restore(self) -> None:
        data, e = self.recoverable, self.editor
        if not isinstance(data.get("items"), list) or len(data["items"]) > 1000:
            self.label.setText("O rascunho não é válido. Preenche uma nova encomenda.")
            return
        try:
            self.restoring = True
            e.client_combo.input.setCurrentText(str(data.get("client", "")))
            state = e.status.input.findData(data.get("status"))
            if state >= 0:
                e.status.input.setCurrentIndex(state)
            e.payment.input.setCurrentIndex(int(data.get("payment", 0)))
            e.shipping.set_value(float(data.get("shipping", 0)))
            e.tracking.set_text(str(data.get("tracking", "")))
            e.notes.input.setPlainText(str(data.get("notes", "")))
            e.has_deadline.setChecked(bool(data.get("deadline_enabled")))
            date = QDate.fromString(str(data.get("deadline", "")), "yyyy-MM-dd")
            if date.isValid():
                e.deadline.setDate(date)
            e.items_buffer = [dict(item) for item in data["items"]]
            e._idempotency_key = str(data.get("request_key", e._idempotency_key))
            e._refresh_items_table()
            e._validate_form()
            self.changed = True
            self.last = self._snapshot()
            self.label.setText("Rascunho retomado. Revê os itens e os valores antes de guardar.")
            self.recover.hide()
        except (ValueError, TypeError, KeyError, OverflowError):
            self.label.setText("Não foi possível retomar todos os campos. Revê o formulário antes de guardar.")
        finally:
            self.restoring = False

    def _finish(self, result: int) -> None:
        self._detect_changes()
        if self.changed and not self.editor._saved:
            self._save()
        self.closed = True
        self.timer.stop()
        self.scan.stop()
        self.poll.stop()
        if self.editor._saved:
            # All writes use one queue: deletion happens after any pending autosave.
            submit_file("delete", self.path)
