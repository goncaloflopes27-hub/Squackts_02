from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

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
    SummaryCard,
)
from ui.theme import COLORS, RADIUS, SPACING


class ProductEditorDialog(QDialog):
    SIZE_OPTIONS = ["PP", "P", "M", "G", "GG", "XG", "XXG", "TU"]

    def __init__(self, service: ProductService, product: dict[str, object] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.product = product
        self.saved_id: int | None = None
        self._saving = False
        self._closing = False
        self._prepared_image_path = ""
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
        self.color = LabeledInput("Cor", required=True)
        self.sku = LabeledInput("SKU automático")
        self.sku.input.setReadOnly(True)
        form.addWidget(DividerLabel("Identificação"))
        form.addWidget(FormRow(self.name, self.color))
        form.addWidget(self.sku)

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
        self.image_path = LabeledInput("Imagem")
        self.image_path.input.setReadOnly(True)
        self.pick_image_btn = QPushButton("Escolher imagem")
        self.pick_image_btn.clicked.connect(self._pick_image)
        form.addWidget(DividerLabel("Produção e imagem"))
        form.addWidget(FormRow(self.production, self.image_path))
        form.addWidget(self.pick_image_btn, alignment=Qt.AlignLeft)

        self.thumbnail = QLabel("Sem imagem")
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setMinimumSize(180, 180)
        self.thumbnail.setStyleSheet(
            f"background:{COLORS.surface_alt}; border:1px solid {COLORS.border}; border-radius:{RADIUS.md}px; color:{COLORS.text_secondary};"
        )
        form.addWidget(self.thumbnail)

        sizes_row = QWidget()
        sizes_layout = QHBoxLayout(sizes_row)
        sizes_layout.setContentsMargins(0, 0, 0, 0)
        self.size_checks: dict[str, QCheckBox] = {}
        for size in self.SIZE_OPTIONS:
            checkbox = QCheckBox(size)
            self.size_checks[size] = checkbox
            sizes_layout.addWidget(checkbox)
        sizes_layout.addStretch(1)
        form.addWidget(DividerLabel("Tamanhos"))
        form.addWidget(sizes_row)

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
        self.name.input.textChanged.connect(self._update_sku_preview)
        self.color.input.textChanged.connect(self._validate_form)
        self.color.input.textChanged.connect(self._update_sku_preview)
        self.price.input.valueChanged.connect(self._validate_form)
        self.cost.input.valueChanged.connect(self._validate_form)
        self._load_data()
        self._update_sku_preview()
        self._validate_form()

    def _load_data(self) -> None:
        if not self.product:
            return
        self.name.set_text(str(self.product.get("nome", "")))
        self.color.set_text(str(self.product.get("cor", "")))
        self.sku.set_text(str(self.product.get("sku", "")))
        for size in self._product_sizes():
            checkbox = self.size_checks.get(size)
            if checkbox is not None:
                checkbox.setChecked(True)
        self.price.set_value(float(self.product.get("preco", 0.0)))
        self.cost.set_value(float(self.product.get("custo", 0.0)))
        self.stock.input.setValue(int(self.product.get("stock", 0)))
        self.min_stock.input.setValue(int(self.product.get("stock_minimo", 0)))
        current_image = str(self.product.get("image_path", ""))
        self.image_path.set_text(current_image)
        self.notes.input.setPlainText(str(self.product.get("descricao", "")))
        tipo = str(self.product.get("tipo_producao", "print_on_demand"))
        idx = self.production.input.findText(tipo)
        if idx >= 0:
            self.production.input.setCurrentIndex(idx)
        self._set_preview(current_image)
        self._update_margin()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        animate_dialog_open(self)

    def reject(self) -> None:  # type: ignore[override]
        self._close_with_animation(super().reject)

    def _pick_image(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "Selecionar imagem", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not selected:
            return
        try:
            sku_hint = self.sku.text() or f"{self.name.text()}-{self.color.text()}"
            prepared_path = self.service.prepare_image_asset(selected, sku_hint)
        except ValueError as exc:
            self.form_error.set_error(str(exc))
            return
        self._prepared_image_path = prepared_path
        self.image_path.set_text(prepared_path)
        self._set_preview(prepared_path)
        self.form_error.set_error(None)

    def _save(self) -> None:
        if self._saving or not self._validate_form():
            return
        self._saving = True
        self.actions.confirm_button.setEnabled(False)
        self.actions.confirm_button.setText("A guardar...")

        payload = {
            "nome": self.name.text(),
            "cor": self.color.text(),
            "tamanhos": self._selected_sizes(),
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
        QTimer.singleShot(300, lambda: self._close_with_animation(super().accept))

    def _set_preview(self, image_path: str) -> None:
        if not image_path:
            self.thumbnail.setText("Sem imagem")
            self.thumbnail.setPixmap(QPixmap())
            return
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self.thumbnail.setText("Imagem inválida")
            self.thumbnail.setPixmap(QPixmap())
            return
        self.thumbnail.setText("")
        self.thumbnail.setPixmap(pixmap.scaled(170, 170, Qt.KeepAspectRatio, Qt.SmoothTransformation))

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

        if not self.color.text():
            self.color.set_error("Cor obrigatória")
            valid = False
        else:
            self.color.set_error(None)

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

    def _selected_sizes(self) -> list[str]:
        return [size for size, checkbox in self.size_checks.items() if checkbox.isChecked()]

    def _product_sizes(self) -> list[str]:
        raw = self.product.get("tamanhos", self.product.get("tamanhos_json", [])) if self.product else []
        if isinstance(raw, list):
            return [str(item).upper() for item in raw]
        text = str(raw).strip()
        if not text:
            return []
        try:
            import json

            decoded = json.loads(text)
        except Exception:
            return []
        if not isinstance(decoded, list):
            return []
        return [str(item).upper() for item in decoded]

    def _update_sku_preview(self) -> None:
        nome = self.name.text().strip()
        cor = self.color.text().strip()
        if not nome or not cor:
            self.sku.set_text("")
            return
        token_nome = self._sku_token(nome, 4)
        token_cor = self._sku_token(cor, 3)
        self.sku.set_text(f"{token_nome}-{token_cor}")

    def _sku_token(self, value: str, min_len: int) -> str:
        import re
        import unicodedata

        normalized = unicodedata.normalize("NFKD", value)
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        collapsed = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").upper()
        if not collapsed:
            collapsed = "X" * min_len
        if len(collapsed) < min_len:
            return collapsed.ljust(min_len, "X")
        return collapsed

    def _close_with_animation(self, finalize: Callable[[], None]) -> None:
        if self._closing:
            return
        self._closing = True

        def _finish() -> None:
            if not self._closing:
                return
            self._closing = False
            finalize()

        animate_dialog_close(self, _finish)
