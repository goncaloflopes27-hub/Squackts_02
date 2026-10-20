from __future__ import annotations

from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from sqlite3 import Error as SQLiteError
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from service_container import ServiceContainer
from ui.components import (
    ActivityList,
    ConfirmationDialog,
    InfoGrid,
    KeyValueCard,
    LoadingState,
    PageHeader,
    PrimaryButton,
    SecondaryButton,
    Toolbar,
    show_toast,
)
from ui.formatting import display_action, display_date
from ui.theme import SPACING


class _BackupSignals(QObject):
    completed = Signal(str, object, object)


class SystemPage(QWidget):
    def __init__(self, container: ServiceContainer) -> None:
        super().__init__()
        self.container = container
        self.search_text = ""
        self._jobs = getattr(container, "backup_jobs", None)
        self._signals = _BackupSignals(self)
        self._signals.completed.connect(self._finish_job, Qt.ConnectionType.QueuedConnection)
        self._busy = False
        self._created_path: Path | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)
        root.addWidget(PageHeader("Sistema", "Verificar a instalação, consultar atividade e recuperar os seus dados."))
        self.backup_button = PrimaryButton("Criar backup completo")
        self.backup_button.clicked.connect(self._create_backup)
        diagnostics = SecondaryButton("Executar diagnóstico")
        diagnostics.clicked.connect(self._run_diagnostics)
        self.restore_button = SecondaryButton("Restaurar backup…")
        self.restore_button.clicked.connect(self._restore_backup)
        root.addWidget(Toolbar(self.backup_button, diagnostics, self.restore_button))
        self.loading = LoadingState("A tratar o pedido…")
        self.loading.hide()
        root.addWidget(self.loading)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.grid = QGridLayout()
        self.grid.setSpacing(SPACING.md)
        self.grid.addWidget(
            KeyValueCard(
                "Localização dos dados",
                [
                    ("Base de dados", str(container.db_path)),
                    ("Imagens", str(container.images_dir)),
                    ("Backups", str(container.backups_dir)),
                ],
            ),
            0,
            0,
        )
        self.diagnostics_widget: QWidget | None = None
        self.backups_widget: QWidget | None = None
        self.logs_widget: QWidget | None = None
        root.addLayout(self.grid)
        self.backup_combo = QComboBox()
        self.verify_button = SecondaryButton("Verificar backup selecionado")
        self.verify_button.clicked.connect(self._verify_backup)
        root.addWidget(Toolbar(self.backup_combo, self.verify_button))
        self.refresh()

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes / (1024 * 1024):.2f} MB"

    def _replace_widget(self, previous: QWidget | None, replacement: QWidget, row: int, column: int) -> QWidget:
        if previous is not None:
            self.grid.removeWidget(previous)
            previous.deleteLater()
        self.grid.addWidget(replacement, row, column)
        return replacement

    def refresh(self) -> None:
        self._run_diagnostics()
        self._refresh_logs()

    def _run_diagnostics(self) -> None:
        try:
            result = self.container.backup.get_diagnostics()
            checks = [
                ("Ligação à base de dados", result.connection_ok),
                ("Integridade da base", getattr(result, "integrity_ok", result.connection_ok)),
                ("Relações dos dados", getattr(result, "foreign_keys_ok", result.connection_ok)),
                ("Pasta de backups", result.backups_dir_exists),
                ("Pasta de imagens", result.images_dir_exists),
                ("Pasta de logs", result.logs_dir_exists),
            ]
            values = [(title, "OK" if ok else "Requer atenção") for title, ok in checks]
            values += [
                ("Versão dos dados", str(result.db_user_version)),
                ("Tamanho da base", self._format_size(result.db_size_bytes)),
            ]
            self.diagnostics_widget = self._replace_widget(
                self.diagnostics_widget, InfoGrid("Diagnóstico", values), 0, 1
            )
            self.status.setText(
                f"Diagnóstico executado em {datetime.now().astimezone().strftime('%d/%m/%Y %H:%M:%S')} · "
                + (
                    "Todos os controlos passaram."
                    if all(ok for _, ok in checks)
                    else "Há controlos que requerem atenção."
                )
            )
        except (ValueError, OSError, RuntimeError, SQLiteError) as exc:
            self.status.setText(f"Falha no diagnóstico: {exc}")

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        self.loading.setVisible(busy)
        for button in (self.backup_button, self.verify_button, self.restore_button):
            button.setEnabled(not busy)
        if message:
            self.status.setText(message)

    def _watch_job(self, kind: str, future: Future[Any]) -> None:
        signals = self._signals

        def finished(done: Future[Any]) -> None:
            try:
                result, error = done.result(), None
            except Exception as exc:
                result, error = None, exc
            try:
                signals.completed.emit(kind, result, error)
            except RuntimeError:
                pass  # The window was closed while the worker was finishing.

        future.add_done_callback(finished)

    @Slot(str, object, object)
    def _finish_job(self, kind: str, result: Any, error: Any) -> None:
        if error is not None:
            self._set_busy(False, f"A operação de backup falhou: {error}")
            show_toast(self, str(error), "danger")
            return
        if kind == "create" and self._jobs:
            self._created_path = Path(result)
            try:
                self._watch_job("created-verify", self._jobs.submit_inspection(self._created_path))
            except Exception as exc:
                self._finish_job("created-verify", None, exc)
            return
        self._set_busy(False)
        self._refresh_logs()
        self._run_diagnostics()
        prefix = "Backup criado e verificado" if kind == "created-verify" else "Backup verificado"
        show_toast(self, f"{prefix} · versão {result.schema_version} · {result.image_count} imagens", "ok")

    def _create_backup(self) -> None:
        if self._busy:
            return
        if self._jobs:
            self._set_busy(True, "A criar e verificar o backup. Pode continuar a usar a aplicação.")
            try:
                self._watch_job("create", self._jobs.submit_backup())
            except Exception as exc:
                self._finish_job("create", None, exc)
            return
        try:
            path = self.container.backup.create_backup()
            inspection = self.container.backup.inspect_backup(path)
        except (ValueError, OSError, RuntimeError, SQLiteError) as exc:
            show_toast(self, f"Não foi possível criar/verificar o backup: {exc}", "danger")
            return
        self._refresh_logs()
        show_toast(self, f"Backup criado e verificado: {path.name} · {inspection.image_count} imagens", "ok")

    def _load_logs(self) -> list[tuple[str, str]]:
        rows = self.container.backup.list_recent_logs(limit=200)
        entries = [
            (
                display_action(row["acao"]),
                f"{display_date(row['timestamp'], time=True)} · {row['detalhe'] or '—'}",
            )
            for row in rows
        ]
        if self.search_text:
            entries = [entry for entry in entries if self.search_text in " ".join(entry).lower()]
        return entries[:30] or [("Sem resultados", "Não existem eventos para esta pesquisa.")]

    def _refresh_logs(self) -> None:
        try:
            files = self.container.backup.list_backups(limit=30)
            previous = self.backup_combo.currentData()
            self.backup_combo.clear()
            entries = []
            for path in files:
                stat = path.stat()
                entries.append(
                    (
                        path.name,
                        f"{datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M')} · {self._format_size(stat.st_size)}",
                    )
                )
                self.backup_combo.addItem(path.name, str(path))
            if previous:
                index = self.backup_combo.findData(previous)
                if index >= 0:
                    self.backup_combo.setCurrentIndex(index)
            self.backups_widget = self._replace_widget(
                self.backups_widget,
                ActivityList(
                    "Backups guardados",
                    entries[:8] or [("Sem backups", "Crie um backup completo antes de uma alteração importante.")],
                ),
                1,
                0,
            )
            self.logs_widget = self._replace_widget(
                self.logs_widget, ActivityList("Atividade recente", self._load_logs()), 1, 1
            )
        except (ValueError, OSError, RuntimeError, SQLiteError) as exc:
            show_toast(self, f"Não foi possível consultar a atividade: {exc}", "danger")

    def _verify_backup(self) -> None:
        if self._busy:
            return
        filename = self.backup_combo.currentData()
        if not filename:
            show_toast(self, "Crie ou selecione um backup primeiro", "warning")
            return
        if self._jobs:
            self._set_busy(True, "A verificar a integridade do backup…")
            try:
                self._watch_job("verify", self._jobs.submit_inspection(Path(filename)))
            except Exception as exc:
                self._finish_job("verify", None, exc)
            return
        try:
            inspection = self.container.backup.inspect_backup(Path(filename))
        except (ValueError, OSError, RuntimeError, SQLiteError) as exc:
            show_toast(self, f"Backup inválido: {exc}", "danger")
            return
        show_toast(
            self, f"Backup verificado · versão {inspection.schema_version} · {inspection.image_count} imagens", "ok"
        )

    def _restore_backup(self) -> None:
        if self._busy:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Restaurar backup", str(self.container.backups_dir), "Backups (*.zip *.sqlite3)"
        )
        if not filename:
            return
        try:
            inspection = self.container.backup.inspect_backup(Path(filename))
        except (ValueError, OSError, RuntimeError, SQLiteError) as exc:
            show_toast(self, f"Não é possível restaurar: {exc}", "danger")
            return
        message = f"Substituir os dados atuais por {Path(filename).name}?\nVersão {inspection.schema_version} · {inspection.image_count} imagens.\nÉ criada uma cópia de recuperação antes da substituição. A aplicação fecha no fim; volte a abri-la para usar os dados restaurados."
        if not ConfirmationDialog("Restaurar dados", message, self).exec():
            return
        try:
            result = self.container.backup.restore_backup(Path(filename))
        except (ValueError, OSError, RuntimeError, SQLiteError) as exc:
            show_toast(self, f"Restauro não realizado: {exc}", "danger")
            return
        QMessageBox.information(
            self,
            "Restauro concluído",
            f"Dados restaurados. Volte a abrir a aplicação.\nCópia de recuperação: {result.recovery_backup.name}",
        )
        if result.restart_required:
            QApplication.quit()

    def apply_search(self, text: str) -> None:
        self.search_text = text.strip().lower()
        self._refresh_logs()
