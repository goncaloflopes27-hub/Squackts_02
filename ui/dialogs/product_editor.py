from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QScrollArea, QVBoxLayout, QWidget

from services.product_service import ProductService
from ui.animations import animate_dialog_close, animate_dialog_open
from ui.components import (
    DividerLabel,
    ErrorText,
    FormActions,
    FormRow,
    LabeledComboBox,
    LabeledInput,
    LabeledMoneyField,
    LabeledSpinBox,
    LabeledTextArea,
    ModalHeader,
    PlaceholderThumbnail,
    SummaryCard,
)
from ui.theme import SPACING


class ProductEditorDialog(QDialog):
    def __init__(self, service: ProductService, product: dict[str, object] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.product = product
        self.saved_id: int | None = None
        self._saving = False
        self.setWindowTitle("Editor de Produto")
        self.setModal(True)
        self.resize(900, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)
        root.addWidget(ModalHeader("Editar produto" if product else "Novo produto", "Gestão comercial e operacional do catálogo"))

        content = QWidget()
        form = QVBoxLayout(content)
        form.setSpacing(SPACING.sm)

        self.name = LabeledInput("Nome", required=True)
        self.sku = LabeledInput("SKU", required=True)
        form.addWidget(DividerLabel("Identificação"))
        form.addWidget(FormRow(self.name, self.sku))

        self.price = LabeledMoneyField("Preço")
        self.cost = LabeledMoneyField("Custo")
        form.addWidget(DividerLabel("Preços e custos"))
        form.addWidget(FormRow(self.price, self.cost))
        self.margin = SummaryCard("Preview de margem", [("Margem", "0.0%")])
        form.addWidget(self.margin)

        self.stock = LabeledSpinBox("Stock", minimum=0, maximum=99999)
        self.min_stock = LabeledSpinBox("Stock mínimo", minimum=0, maximum=99999)
        form.addWidget(DividerLabel("Stock"))
        form.addWidget(FormRow(self.stock, self.min_stock))

        self.production = LabeledComboBox("Tipo de produção", ["print_on_demand", "stock_fisico", "misto"])
        self.image_path = LabeledInput("Imagem (path)")
        form.addWidget(DividerLabel("Produção e imagem"))
        form.addWidget(FormRow(self.production, self.image_path))
        form.addWidget(PlaceholderThumbnail("POD"))

        self.notes = LabeledTextArea("Descrição", "Descrição e notas internas...")
        form.addWidget(DividerLabel("Notas"))
        form.addWidget(self.notes)

        self.form_error = ErrorText()
        form.addWidget(self.form_error)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

        self.actions = FormActions("Cancelar", "Guardar produto")
        self.actions.cancel_button.clicked.connect(self.reject)
        self.actions.confirm_button.clicked.connect(self._save)
        root.addWidget(self.actions)

        self.price.input.valueChanged.connect(self._update_margin)
        self.cost.input.valueChanged.connect(self._update_margin)
        self.name.input.textChanged.connect(self._validate_form)
        self.sku.input.textChanged.connect(self._validate_form)
        self.price.input.valueChanged.connect(self._validate_form)
        self.cost.input.valueChanged.connect(self._validate_form)
        self._load_data()
        self._validate_form()

    def _load_data(self) -> None:
        if not self.product:
            return
        self.name.set_text(str(self.product.get("nome", "")))
        self.sku.set_text(str(self.product.get("sku", "")))
        self.price.set_value(float(self.product.get("preco", 0.0)))
        self.cost.set_value(float(self.product.get("custo", 0.0)))
        self.stock.input.setValue(int(self.product.get("stock", 0)))
        self.min_stock.input.setValue(int(self.product.get("stock_minimo", 0)))
        self.image_path.set_text(str(self.product.get("image_path", "")))
        self.notes.input.setPlainText(str(self.product.get("descricao", "")))
        tipo = str(self.product.get("tipo_producao", "print_on_demand"))
        idx = self.production.input.findText(tipo)
        if idx >= 0:
            self.production.input.setCurrentIndex(idx)
        self._update_margin()

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
            "sku": self.sku.text(),
            "descricao": self.notes.text(),
            "preco": self.price.value(),
            "custo": self.cost.value(),
            "stock": self.stock.value(),
            "stock_minimo": self.min_stock.value(),
            "tipo_producao": self.production.value(),
            "image_path": self.image_path.text(),
            "ativo": 1,
        }
        try:
            if self.product and self.product.get("id") is not None:
                product_id = int(self.product["id"])
                self.service.update_product(product_id, payload)
                self.saved_id = product_id
            else:
                self.saved_id = self.service.create_product(payload)
        except ValueError as exc:
            self.form_error.set_error(str(exc))
            self._saving = False
            self.actions.confirm_button.setText("Guardar produto")
            self._validate_form()
            return

        self.form_error.set_error(None)
        self.actions.confirm_button.setText("Guardado ✓")
        QTimer.singleShot(300, lambda: animate_dialog_close(self, super().accept))

    def _update_margin(self) -> None:
        price = self.price.value()
        cost = self.cost.value()
        margin = ((price - cost) / price * 100.0) if price > 0 else 0.0
        self.margin.set_rows([("Margem", f"{margin:.1f}%")])

    def _validate_form(self) -> bool:
        valid = True
        if not self.name.text():
            self.name.set_error("Nome obrigatório")
            valid = False
        else:
            self.name.set_error(None)

        if not self.sku.text():
            self.sku.set_error("SKU obrigatório")
            valid = False
        else:
            self.sku.set_error(None)

        if self.price.value() < 0:
            self.price.set_error("Preço inválido")
            valid = False
        else:
            self.price.set_error(None)
        if self.cost.value() < 0:
            self.cost.set_error("Custo inválido")
            valid = False
        else:
            self.cost.set_error(None)

        self.actions.confirm_button.setEnabled(valid)
        if valid:
            self.form_error.set_error(None)
        return valid
