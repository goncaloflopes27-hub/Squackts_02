from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QGridLayout, QVBoxLayout, QWidget

from service_container import ServiceContainer
from ui.components import ActivityList, InfoGrid, KeyValueCard, LoadingState, PageHeader, PrimaryButton, StatPill, Toolbar, show_toast
from ui.theme import SPACING


class SystemPage(QWidget):
    def __init__(self, container: ServiceContainer) -> None:
        super().__init__()
        self.container = container

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)
        root.addWidget(PageHeader("Sistema", "Administração técnica, backups e saúde da aplicação."))

        backup_btn = PrimaryButton("Criar backup")
        backup_btn.clicked.connect(self._create_backup)
        logs_btn = PrimaryButton("Ver logs")
        logs_btn.clicked.connect(self._refresh_logs)
        root.addWidget(Toolbar(backup_btn, logs_btn))

        self.grid = QGridLayout()
        self.grid.setSpacing(SPACING.md)

        diagnostics = self.container.backup.get_diagnostics()
        paths = KeyValueCard(
            "Caminhos críticos",
            [
                ("Base de dados", str(self.container.db_path)),
                ("Imagens", str(self.container.images_dir)),
                ("Logs", str(self.container.logs_dir)),
                ("Backups", str(self.container.backups_dir)),
            ],
        )
        self.grid.addWidget(paths, 0, 0)

        backups = KeyValueCard(
            "Backups",
            [
                ("Estratégia", "SQLite backup API"),
                ("Retenção", "Manual (fase base)"),
                ("user_version", str(diagnostics.db_user_version)),
            ],
        )
        backups.layout().addWidget(StatPill("Pronto", "ok"))
        self.grid.addWidget(backups, 0, 1)

        info = InfoGrid(
            "Diagnóstico rápido",
            [
                ("DB existe", self._bool_label(diagnostics.db_exists)),
                ("Conexão", self._bool_label(diagnostics.connection_ok)),
                ("DB tamanho", self._format_size(diagnostics.db_size_bytes)),
                ("Backups dir", self._bool_label(diagnostics.backups_dir_exists)),
                ("Imagens dir", self._bool_label(diagnostics.images_dir_exists)),
                ("Logs dir", self._bool_label(diagnostics.logs_dir_exists)),
            ],
        )
        self.grid.addWidget(info, 1, 0, 1, 2)

        self.backups_widget = ActivityList("Backups recentes", self._load_backups())
        self.grid.addWidget(self.backups_widget, 2, 0)

        self.logs_widget = ActivityList("Logs recentes", self._load_logs())
        self.grid.addWidget(self.logs_widget, 2, 1)

        root.addLayout(self.grid)
        root.addWidget(LoadingState("Infraestrutura pronta para services e repositories."))

    def _bool_label(self, value: bool) -> str:
        return "Sim" if value else "Não"

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes / (1024 * 1024):.2f} MB"

    def _create_backup(self) -> None:
        backup_path = self.container.backup.create_backup()
        show_toast(self, f"Backup criado: {backup_path.name}", "ok")
        self._refresh_logs()

    def _load_logs(self) -> list[tuple[str, str]]:
        rows = self.container.backup.list_recent_logs(limit=8)
        if not rows:
            return [("INFO", "Sem eventos de infraestrutura ainda")]
        return [(str(row["acao"]).upper(), f"{row['timestamp']} · {row['detalhe'] or '-'}") for row in rows]

    def _load_backups(self) -> list[tuple[str, str]]:
        files = self.container.backup.list_backups(limit=8)
        if not files:
            return [("INFO", "Sem backups criados ainda")]
        entries: list[tuple[str, str]] = []
        for item in files:
            meta = item.stat()
            updated = datetime.fromtimestamp(meta.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            entries.append((item.name, f"{updated} · {self._format_size(meta.st_size)}"))
        return entries

    def _refresh_logs(self) -> None:
        self.grid.removeWidget(self.backups_widget)
        self.backups_widget.deleteLater()
        self.backups_widget = ActivityList("Backups recentes", self._load_backups())
        self.grid.addWidget(self.backups_widget, 2, 0)

        self.grid.removeWidget(self.logs_widget)
        self.logs_widget.deleteLater()
        self.logs_widget = ActivityList("Logs recentes", self._load_logs())
        self.grid.addWidget(self.logs_widget, 2, 1)
        show_toast(self, "Logs atualizados", "info")
