from __future__ import annotations

import re

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QScrollArea, QVBoxLayout, QWidget

from services.client_service import ClientService
from ui.animations import animate_dialog_close, animate_dialog_open
from ui.components import (
    DividerLabel,
    ErrorText,
    FormActions,
    FormRow,
    LabeledInput,
    LabeledTextArea,
    ModalHeader,
)
from ui.theme import SPACING


class ClientEditorDialog(QDialog):
    EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def __init__(self, service: ClientService, client: dict[str, object] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.client = client
        self.saved_id: int | None = None
        self._saving = False
        self.setWindowTitle("Editor de Cliente")
        self.setModal(True)
        self.resize(860, 680)

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)
        root.addWidget(ModalHeader("Editar cliente" if client else "Novo cliente", "Perfil comercial completo e validado"))

        content = QWidget()
        form = QVBoxLayout(content)
        form.setSpacing(SPACING.sm)

        self.name = LabeledInput("Nome", required=True)
        self.email = LabeledInput("Email", required=True)
        form.addWidget(DividerLabel("Dados principais"))
        form.addWidget(FormRow(self.name, self.email))

        self.phone = LabeledInput("Telefone")
        self.nif = LabeledInput("NIF")
        form.addWidget(DividerLabel("Contactos e fiscal"))
        form.addWidget(FormRow(self.phone, self.nif))

        self.address = LabeledInput("Morada")
        form.addWidget(DividerLabel("Morada"))
        form.addWidget(self.address)

        self.notes = LabeledTextArea("Notas", "Condições comerciais e observações...")
        form.addWidget(DividerLabel("Notas"))
        form.addWidget(self.notes)

        self.form_error = ErrorText()
        form.addWidget(self.form_error)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

        self.actions = FormActions("Cancelar", "Guardar cliente")
        self.actions.cancel_button.clicked.connect(self.reject)
        self.actions.confirm_button.clicked.connect(self._save)
        root.addWidget(self.actions)

        self.name.input.textChanged.connect(self._validate_form)
        self.email.input.textChanged.connect(self._validate_form)
        self.nif.input.textChanged.connect(self._validate_form)
        self._load_data()
        self._validate_form()

    def _load_data(self) -> None:
        if not self.client:
            return
        self.name.set_text(str(self.client.get("nome", "")))
        self.email.set_text(str(self.client.get("email", "")))
        self.phone.set_text(str(self.client.get("telefone", "")))
        self.nif.set_text(str(self.client.get("nif", "")))
        self.address.set_text(str(self.client.get("morada", "")))
        self.notes.input.setPlainText(str(self.client.get("notas", "")))

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        animate_dialog_open(self)

    def reject(self) -> None:  # type: ignore[override]
        animate_dialog_close(self, super().reject)

    def _save(self) -> None:
        if self._saving or not self._validate_form():
            return
        self._saving = True
        self.actions.confirm_button.setEnabled(False)
        self.actions.confirm_button.setText("A guardar...")
        payload = {
            "nome": self.name.text(),
            "email": self.email.text(),
            "telefone": self.phone.text(),
            "nif": self.nif.text(),
            "morada": self.address.text(),
            "notas": self.notes.text(),
            "ativo": 1,
        }
        try:
            if self.client and self.client.get("id") is not None:
                client_id = int(self.client["id"])
                self.service.update_client(client_id, payload)
                self.saved_id = client_id
            else:
                self.saved_id = self.service.create_client(payload)
        except ValueError as exc:
            self.form_error.set_error(str(exc))
            self._saving = False
            self.actions.confirm_button.setText("Guardar cliente")
            self._validate_form()
            return

        self.form_error.set_error(None)
        self.actions.confirm_button.setText("Guardado ✓")
        QTimer.singleShot(300, lambda: animate_dialog_close(self, super().accept))

    def _validate_form(self) -> bool:
        valid = True
        name = self.name.text()
        email = self.email.text()
        nif = self.nif.text()

        if not name:
            self.name.set_error("Nome obrigatório")
            valid = False
        else:
            self.name.set_error(None)
        if not self.EMAIL_REGEX.match(email):
            self.email.set_error("Email inválido")
            valid = False
        else:
            self.email.set_error(None)
        if nif and (len(nif) != 9 or not nif.isdigit()):
            self.nif.set_error("NIF deve ter 9 dígitos")
            valid = False
        else:
            self.nif.set_error(None)

        self.actions.confirm_button.setEnabled(valid)
        if valid:
            self.form_error.set_error(None)
        return valid
