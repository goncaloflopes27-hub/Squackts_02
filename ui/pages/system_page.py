from __future__ import annotations

from datetime import datetime
from sqlite3 import Row

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget

from config import APP_NAME
from service_container import ServiceContainer
from services.backup_service import BackupFileInfo, SystemDiagnostics
from ui.components import (
    ActivityList,
    ConfirmationDialog,
    InfoGrid,
    KeyValueCard,
    PageHeader,
    PrimaryButton,
    SecondaryButton,
    Toolbar,
    show_toast,
)
from ui.theme import SPACING


class SystemPage(QWidget):
    def __init__(self, container: ServiceContainer) -> None:
        super().__init__()
        self.container = container
        self._backups: list[BackupFileInfo] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)
        root.addWidget(PageHeader("Sistema", "Administração técnica, backups e saúde da aplicação."))

        self.btn_refresh = SecondaryButton("Atualizar")
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_backup = PrimaryButton("Criar backup")
        self.btn_backup.clicked.connect(self._create_backup)
        self.btn_restore = SecondaryButton("Restaurar backup")
        self.btn_restore.clicked.connect(self._restore_selected_backup)
        root.addWidget(Toolbar(self.btn_refresh, self.btn_backup, self.btn_restore))

        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(SPACING.sm)
        controls_layout.addWidget(QLabel("Backup selecionado:"))
        self.backup_combo = QComboBox()
        self.backup_combo.currentTextChanged.connect(self._on_backup_selected)
        controls_layout.addWidget(self.backup_combo, stretch=2)
        controls_layout.addWidget(QLabel("Retenção:"))
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(1, 200)
        self.retention_spin.valueChanged.connect(self._update_retention)
        controls_layout.addWidget(self.retention_spin)
        controls_layout.addStretch(1)
        root.addWidget(controls)

        self.paths_card = KeyValueCard("Caminhos críticos", [])
        self.backup_card = KeyValueCard("Backups", [])
        self.health_card = InfoGrid("Diagnóstico rápido", [])
        self.backups_widget = ActivityList("Backups recentes", [("INFO", "Sem dados")])
        self.logs_widget = ActivityList("Logs recentes", [("INFO", "Sem dados")])
        self.runtime_card = InfoGrid("Runtime", [])

        root.addWidget(self.paths_card)
        root.addWidget(self.backup_card)
        root.addWidget(self.health_card)

        lower = QHBoxLayout()
        lower.setSpacing(SPACING.md)
        lower.addWidget(self.backups_widget)
        lower.addWidget(self.logs_widget)
        root.addLayout(lower)

        root.addWidget(self.runtime_card)
        self.refresh()

    def _bool_label(self, value: bool) -> str:
        return "Sim" if value else "Não"

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes / (1024 * 1024):.2f} MB"

    def _set_busy(self, is_busy: bool) -> None:
        self.btn_refresh.setEnabled(not is_busy)
        self.btn_backup.setEnabled(not is_busy)
        self.btn_restore.setEnabled(not is_busy and self.backup_combo.count() > 0)

    def _on_backup_selected(self, _value: str) -> None:
        self.btn_restore.setEnabled(self.backup_combo.count() > 0)

    def trigger_primary_action(self) -> None:
        self._create_backup()

    def _create_backup(self) -> None:
        self._set_busy(True)
        try:
            backup_path = self.container.backup.create_backup()
        except Exception as exc:
            show_toast(self, f"Falha ao criar backup: {exc}", "danger")
        else:
            show_toast(self, f"Backup criado: {backup_path.name}", "ok")
        finally:
            self._set_busy(False)
            self.refresh()

    def _restore_selected_backup(self) -> None:
        selected = self.backup_combo.currentData()
        if not selected:
            show_toast(self, "Selecione um backup", "warning")
            return

        dialog = ConfirmationDialog(
            "Confirmar restore",
            "Esta operação substitui a base de dados atual. Confirme apenas se tem certeza.",
            self,
        )
        if dialog.exec() == 0:
            return

        self._set_busy(True)
        try:
            self.container.backup.restore_backup(str(selected))
        except ValueError as exc:
            show_toast(self, str(exc), "danger")
        except Exception as exc:
            show_toast(self, f"Falha inesperada no restore: {exc}", "danger")
        else:
            show_toast(self, "Restore concluído com sucesso", "ok")
        finally:
            self._set_busy(False)
            self.refresh()

    def _update_retention(self, value: int) -> None:
        try:
            self.container.backup.set_retention_count(value)
        except Exception as exc:
            show_toast(self, f"Falha ao atualizar retenção: {exc}", "danger")
        else:
            show_toast(self, f"Retenção atualizada para {value}", "info")
            self.refresh()

    def refresh(self) -> None:
        try:
            diagnostics = self.container.backup.get_diagnostics()
            self._backups = self.container.backup.list_backups(limit=32)
            logs = self.container.backup.list_recent_logs(limit=8)
            retention = self.container.backup.get_retention_count()
        except Exception as exc:
            show_toast(self, f"Falha ao atualizar Sistema: {exc}", "danger")
            return

        self._sync_controls(retention)
        self._update_cards(diagnostics, logs, retention)

    def _sync_controls(self, retention: int) -> None:
        self.retention_spin.blockSignals(True)
        self.retention_spin.setValue(retention)
        self.retention_spin.blockSignals(False)

        current_name = str(self.backup_combo.currentData() or "")
        self.backup_combo.blockSignals(True)
        self.backup_combo.clear()
        for item in self._backups:
            self.backup_combo.addItem(item.path.name, item.path.name)
        if current_name:
            idx = self.backup_combo.findData(current_name)
            if idx >= 0:
                self.backup_combo.setCurrentIndex(idx)
        self.backup_combo.blockSignals(False)
        self.btn_restore.setEnabled(self.backup_combo.count() > 0)

    def _update_cards(self, diagnostics: SystemDiagnostics, logs: list[Row], retention: int) -> None:
        self.paths_card.set_entries(
            [
                ("Base de dados", str(self.container.db_path)),
                ("Imagens", str(self.container.images_dir)),
                ("Logs", str(self.container.logs_dir)),
                ("Backups", str(self.container.backups_dir)),
            ]
        )

        self.backup_card.set_entries(
            [
                ("Estratégia", "SQLite backup API"),
                ("user_version", str(diagnostics.db_user_version)),
                ("Retenção", f"{retention} ficheiros"),
                ("Total backups", str(len(self._backups))),
            ]
        )

        self.health_card.set_rows(
            [
                ("DB existe", self._bool_label(diagnostics.db_exists)),
                ("Conexão", self._bool_label(diagnostics.connection_ok)),
                ("DB tamanho", self._format_size(diagnostics.db_size_bytes)),
                ("Backups dir", self._bool_label(diagnostics.backups_dir_exists)),
                ("Imagens dir", self._bool_label(diagnostics.images_dir_exists)),
                ("Logs dir", self._bool_label(diagnostics.logs_dir_exists)),
            ]
        )

        backup_entries: list[tuple[str, str]] = [("INFO", "Sem backups criados ainda")]
        if self._backups:
            backup_entries = [
                (
                    item.path.name,
                    f"{item.modified_at.strftime('%Y-%m-%d %H:%M:%S')} · {self._format_size(item.size_bytes)}",
                )
                for item in self._backups[:8]
            ]
        self.backups_widget.set_activities(backup_entries)

        log_entries: list[tuple[str, str]] = [("INFO", "Sem eventos de infraestrutura ainda")]
        if logs:
            log_entries = [(str(row["acao"]).upper(), f"{row['timestamp']} · {row['detalhe'] or '-'}") for row in logs]
        self.logs_widget.set_activities(log_entries)

        self.runtime_card.set_rows(
            [
                ("Aplicação", APP_NAME),
                ("Timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                ("Modo", "Desktop local"),
                ("Serviços", "UI → Services → Repositories → SQLite"),
                ("Backup selecionado", self.backup_combo.currentText() or "-"),
            ]
        )
