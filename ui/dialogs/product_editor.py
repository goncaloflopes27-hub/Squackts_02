from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QShowEvent
from PySide6.QtWidgets import QFileDialog, QLabel, QScrollArea, QVBoxLayout, QWidget

from services.image_service import ImageService
from services.product_service import ProductService
from ui.animations import animate_dialog_open
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
    SecondaryButton,
    SummaryCard,
)
from ui.dialogs.editor_base import EditorDialog
from ui.theme import SPACING


class ProductEditorDialog(EditorDialog):
    def __init__(
        self,
        service: ProductService,
        product: dict[str, object] | None = None,
        parent: QWidget | None = None,
        image_service: ImageService | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.product = product
        self.image_service = image_service
        self._pending_image: str | None = None
        self.saved_id: int | None = None
        self._saving = False
        self.setWindowTitle("Editor de Produto")
        self.setModal(True)
        self.resize(900, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)
        root.addWidget(
            ModalHeader("Editar produto" if product else "Novo produto", "Gestão comercial e operacional do catálogo")
        )

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

        self.stock = LabeledSpinBox("Stock disponível (físico/misto)", minimum=0, maximum=99999)
        self.min_stock = LabeledSpinBox("Stock mínimo", minimum=0, maximum=99999)
        form.addWidget(DividerLabel("Stock"))
        form.addWidget(FormRow(self.stock, self.min_stock))

        self.production = LabeledComboBox("Modo de tratamento", [])
        for label, value in [
            ("Produzir a pedido", "print_on_demand"),
            ("Separar stock físico", "stock_fisico"),
            ("Usar stock e produzir o restante", "misto"),
        ]:
            self.production.input.addItem(label, value)
        self.production.input.currentIndexChanged.connect(self._update_stock_fields)
        self._update_stock_fields()
        self.technique = LabeledInput("Técnica de produção", "Ex.: DTF, sublimação ou bordado")
        form.addWidget(self.technique)
        self.image_path = LabeledInput("Imagem gerida pela aplicação")
        self.image_path.input.setReadOnly(True)
        form.addWidget(DividerLabel("Produção e imagem"))
        form.addWidget(FormRow(self.production, self.image_path))
        self.image_preview = QLabel("Sem imagem")
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setFixedHeight(120)
        form.addWidget(self.image_preview)
        self.choose_image = SecondaryButton("Escolher imagem…")
        self.choose_image.clicked.connect(self._choose_image)
        self.choose_image.setEnabled(self.image_service is not None)
        form.addWidget(self.choose_image)

        self.notes = LabeledTextArea("Descrição", "Descrição e notas internas...")
        form.addWidget(DividerLabel("Notas"))
        form.addWidget(self.notes)

        self.form_error = ErrorText()
        form.addWidget(self.form_error)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

        self.form_actions = FormActions("Cancelar", "Guardar produto")
        self.form_actions.cancel_button.clicked.connect(self.reject)
        self.form_actions.confirm_button.clicked.connect(self._save)
        root.addWidget(self.form_actions)

        self.price.input.valueChanged.connect(self._update_margin)
        self.cost.input.valueChanged.connect(self._update_margin)
        self.name.input.textChanged.connect(self._validate_form)
        self.sku.input.textChanged.connect(self._validate_form)
        self.price.input.valueChanged.connect(self._validate_form)
        self.cost.input.valueChanged.connect(self._validate_form)
        self._load_data()
        self._initial_values = self._payload()
        self._validate_form()
        self._mark_clean()

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
        self.technique.set_text(str(self.product.get("technique", "")))
        tipo = str(self.product.get("tipo_producao", "print_on_demand"))
        idx = self.production.input.findData(tipo)
        if idx >= 0:
            self.production.input.setCurrentIndex(idx)
        self._update_margin()
        self._update_image_preview()

    def _choose_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Imagem do produto", "", "Imagens (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not filename:
            return
        self._pending_image = filename
        self.image_path.set_text(Path(filename).name)
        self._update_image_preview(filename)

    def _update_image_preview(self, source: str | None = None) -> None:
        try:
            path = (
                Path(source)
                if source
                else self.image_service.resolve(self.image_path.text())
                if self.image_service and self.image_path.text()
                else None
            )
            pixmap = QPixmap(str(path)) if path else QPixmap()
            if not pixmap.isNull():
                self.image_preview.setPixmap(
                    pixmap.scaled(
                        180, 110, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                    )
                )
            else:
                self.image_preview.setText("Sem imagem")
        except ValueError:
            self.image_preview.setText("Imagem indisponível")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        animate_dialog_open(self)

    def _save(self) -> None:
        if self._saving or not self._validate_form():
            return
        self._saving = True
        self.form_actions.confirm_button.setEnabled(False)
        self.form_actions.confirm_button.setText("A guardar...")
        payload = self._payload()
        if self.product:
            payload = {key: value for key, value in payload.items() if value != self._initial_values.get(key)}
        try:
            if self._pending_image and self.image_service:
                payload["image_path"] = self.image_service.import_image(self._pending_image).image_path
            if self.product and self.product.get("id") is not None:
                product_id = int(self.product["id"])
                self.service.update_product(product_id, payload)
                self.saved_id = product_id
            else:
                self.saved_id = self.service.create_product(payload)
        except (ValueError, OSError) as exc:
            self.form_error.set_error(str(exc))
            self._reveal_error(self.form_error)
            self._saving = False
            self.form_actions.confirm_button.setText("Guardar produto")
            self._validate_form()
            return

        self.form_error.set_error(None)
        self.form_actions.confirm_button.setText("Guardado ✓")
        self._accept_saved()

    def _payload(self) -> dict[str, object]:
        return {
            "nome": self.name.text(),
            "sku": self.sku.text(),
            "descricao": self.notes.text(),
            "preco": self.price.value(),
            "custo": self.cost.value(),
            "stock": self.stock.value(),
            "stock_minimo": self.min_stock.value(),
            "tipo_producao": str(self.production.input.currentData()),
            "technique": self.technique.text(),
            "image_path": self.image_path.text(),
            "ativo": int(self.product.get("ativo", 1)) if self.product else 1,
        }
    def _update_stock_fields(self) -> None:
        physical = self.production.input.currentData() != "print_on_demand"
        self.stock.setEnabled(physical)
        self.min_stock.setEnabled(physical)

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

        self.form_actions.confirm_button.setEnabled(valid and not self._saving)
        return valid
