from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QVBoxLayout, QWidget

from services.product_service import ProductService
from ui.components import ErrorText, FormActions, FormRow, LabeledInput, LabeledMoneyField, LabeledSpinBox, ModalHeader
from ui.dialogs.editor_base import EditorDialog
from ui.theme import SPACING


class VariantEditorDialog(EditorDialog):
    def __init__(
        self,
        service: ProductService,
        product_id: int,
        variant: dict[str, object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.product_id = product_id
        self.variant = variant
        self.saved_id: int | None = None
        self.setWindowTitle("Variante de produto")
        self.resize(640, 520)
        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)
        root.addWidget(
            ModalHeader("Editar variante" if variant else "Nova variante", "Tamanho, cor, preço e stock próprios")
        )
        self.sku = LabeledInput("SKU", required=True)
        self.size_field = LabeledInput("Tamanho")
        self.color = LabeledInput("Cor")
        self.price = LabeledMoneyField("Preço")
        self.cost = LabeledMoneyField("Custo")
        self.stock = LabeledSpinBox("Stock físico total", minimum=0, maximum=999999)
        self.reason = LabeledInput("Motivo da alteração de stock")
        self.active = QCheckBox("Disponível para novas encomendas")
        self.active.setChecked(True)
        root.addWidget(self.sku)
        root.addWidget(FormRow(self.size_field, self.color))
        root.addWidget(FormRow(self.price, self.cost, self.stock))
        root.addWidget(self.reason)
        root.addWidget(self.active)
        self.error = ErrorText()
        root.addWidget(self.error)
        self.form_actions = FormActions("Cancelar", "Guardar variante")
        self.form_actions.cancel_button.clicked.connect(self.reject)
        self.form_actions.confirm_button.clicked.connect(self._save)
        root.addWidget(self.form_actions)
        if variant:
            self.sku.set_text(str(variant["sku"]))
            self.size_field.set_text(str(variant["tamanho"]))
            self.color.set_text(str(variant["cor"]))
            self.price.set_value(float(variant["preco"]))
            self.cost.set_value(float(variant["custo"]))
            self.stock.input.setValue(int(variant["stock_on_hand"]))
            self.active.setChecked(bool(int(variant["ativo"])))
        self._initial_values = self._payload()
        self._mark_clean()

    def _save(self) -> None:
        if self._saving:
            return
        if not self.sku.text():
            self.sku.set_error("SKU obrigatório")
            self.sku.input.setFocus()
            return
        if self.variant and self.stock.value() != int(self.variant["stock_on_hand"]) and not self.reason.text():
            self.reason.set_error("Explique a alteração para o histórico de stock")
            self.reason.input.setFocus()
            return
        payload = self._payload()
        if self.variant:
            payload = {key: value for key, value in payload.items() if value != self._initial_values.get(key)}
        self._saving = True
        self.form_actions.confirm_button.setEnabled(False)
        try:
            if self.variant:
                self.saved_id = int(self.variant["id"])
                self.service.update_variant(self.saved_id, payload)
            else:
                self.saved_id = self.service.create_variant(self.product_id, payload)
        except (ValueError, OSError) as exc:
            self._saving = False
            self.form_actions.confirm_button.setEnabled(True)
            self.error.set_error(str(exc))
            self._reveal_error(self.error)
            return
        self._accept_saved()

    def _payload(self) -> dict[str, object]:
        return {
            "sku": self.sku.text(),
            "tamanho": self.size_field.text(),
            "cor": self.color.text(),
            "preco": self.price.value(),
            "custo": self.cost.value(),
            "stock_on_hand": self.stock.value(),
            "ativo": int(self.active.isChecked()),
            "reason": self.reason.text(),
        }
