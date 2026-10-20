from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QLabel, QVBoxLayout, QWidget

from ui.components import FormActions, ModalHeader
from ui.theme import COLORS, SPACING


class PreferenceStore(Protocol):
    def get(self, key: str, default: str = "") -> str: ...
    def set(self, key: str, value: str) -> None: ...


class LocalPreferences:
    """UI-only settings fallback for independently constructed development windows."""
    def __init__(self, path: str) -> None:
        self.settings = QSettings(path, QSettings.Format.IniFormat)

    def get(self, key: str, default: str = "") -> str:
        return str(self.settings.value(key, default))

    def set(self, key: str, value: str) -> None:
        self.settings.setValue(key, value)
        self.settings.sync()
        if self.settings.status() != QSettings.Status.NoError:
            raise ValueError("Não foi possível guardar as preferências.")


class PreferencesDialog(QDialog):
    saved = Signal()

    def __init__(self, store: PreferenceStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.motion_store = getattr(parent, "motion_preferences", store)
        self.setWindowTitle("Preferências")
        self.setModal(True)
        self.resize(480, 300)
        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)
        root.addWidget(ModalHeader("Preferências", "Personalize a forma como trabalha."))
        root.addWidget(QLabel("Animações"))
        self.motion_mode = QComboBox()
        self.motion_mode.addItems(["Completas", "Reduzidas", "Desligadas"])
        fallback = "reduced" if store.get("ui.reduce_motion", "0") == "1" else "full"
        mode = self.motion_store.get("ui.motion_mode", fallback)
        self.motion_mode.setCurrentIndex({"full": 0, "reduced": 1, "off": 2}.get(mode, 0))
        self.motion_mode.setAccessibleName("Nível de animações")
        root.addWidget(self.motion_mode)
        self.compact_sidebar = QCheckBox("Preferir navegação compacta")
        self.compact_sidebar.setChecked(store.get("ui.compact_sidebar", "0") == "1")
        root.addWidget(self.compact_sidebar)
        helper = QLabel("Em janelas menores a navegação adapta-se automaticamente.\nComandos: Ctrl+K · Pesquisa: Ctrl+F · Atualizar: F5 · Páginas: Alt+1 a Alt+6")
        helper.setWordWrap(True)
        helper.setStyleSheet(f"color:{COLORS.text_secondary}; font-size:12px;")
        root.addWidget(helper)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setStyleSheet(f"color:{COLORS.danger};")
        root.addWidget(self.error)
        root.addStretch(1)
        actions = FormActions()
        actions.cancel_button.clicked.connect(self.reject)
        actions.confirm_button.clicked.connect(self._save)
        root.addWidget(actions)

    def _save(self) -> None:
        try:
            self.motion_store.set("ui.motion_mode", ["full", "reduced", "off"][self.motion_mode.currentIndex()])
            self.store.set("ui.reduce_motion", "1" if self.motion_mode.currentIndex() else "0")
            self.store.set("ui.compact_sidebar", "1" if self.compact_sidebar.isChecked() else "0")
        except (ValueError, OSError) as exc:
            self.error.setText(str(exc))
            return
        self.saved.emit()
        self.accept()
