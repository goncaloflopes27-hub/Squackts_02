from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QStandardItemModel
from PySide6.QtWidgets import QDialog, QHBoxLayout, QScrollArea, QTableWidgetItem, QVBoxLayout, QWidget

from services.client_service import ClientService
from services.order_domain import (
    PAID_REQUIRED_STATES,
    TRACKING_ALLOWED_STATES,
    TRACKING_REQUIRED_STATES,
    editor_allowed_states,
)
from services.order_service import OrderService
from services.product_service import ProductService
from ui.animations import animate_dialog_close, animate_dialog_open
from ui.components import (
    DataTable,
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
    PrimaryButton,
    SecondaryButton,
    SummaryCard,
)
from ui.theme import SPACING
from utils import format_currency


class OrderEditorDialog(QDialog):
    def __init__(
        self,
        order_service: OrderService,
        client_service: ClientService,
        product_service: ProductService,
        order: dict[str, object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.order_service = order_service
        self.client_service = client_service
        self.product_service = product_service
        self.order = order
        self.saved_id: int | None = None
        self.items_buffer: list[dict[str, int]] = []
        self._saving = False
        self._closing = False

        self.setWindowTitle("Editor de Encomenda")
        self.setModal(True)
        self.resize(980, 780)

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)
        root.addWidget(ModalHeader("Editar encomenda" if order else "Nova encomenda", "Editor real com múltiplos itens e cálculo financeiro"))

        content = QWidget()
        form = QVBoxLayout(content)
        form.setSpacing(SPACING.sm)

        clients = self.client_service.list_clients()
        self.client_options = [f"{c['id']} - {c['nome']}" for c in clients] or ["0 - Sem clientes"]
        self.products = self.product_service.list_products()
        self.product_options = [f"{p['id']} - {p['nome']} ({p['sku']})" for p in self.products] or ["0 - Sem produtos"]

        self.client_combo = LabeledComboBox("Cliente", self.client_options)
        status_options = editor_allowed_states(str(order.get("estado", "rascunho")) if order else None, is_create=order is None)
        self.status = LabeledComboBox("Estado", status_options)
        self.payment = LabeledComboBox("Pagamento", ["0 - Não pago", "1 - Pago"])
        form.addWidget(DividerLabel("Cliente e estado"))
        form.addWidget(FormRow(self.client_combo, self.status, self.payment))

        self.product_combo = LabeledComboBox("Produto", self.product_options)
        self.quantity = LabeledSpinBox("Quantidade", minimum=1)
        self.quantity.input.setValue(1)
        add_item_btn = PrimaryButton("Adicionar item")
        add_item_btn.clicked.connect(self._add_item)
        remove_item_btn = SecondaryButton("Remover item")
        remove_item_btn.clicked.connect(self._remove_selected_item)
        item_actions = QHBoxLayout()
        item_actions.setContentsMargins(0, 0, 0, 0)
        item_actions.addWidget(self.product_combo)
        item_actions.addWidget(self.quantity)
        item_actions.addWidget(add_item_btn)
        item_actions.addWidget(remove_item_btn)
        row = QWidget()
        row.setLayout(item_actions)
        form.addWidget(DividerLabel("Itens da encomenda"))
        form.addWidget(row)

        self.items_table = DataTable(0, 5)
        self.items_table.setHorizontalHeaderLabels(["Produto", "Tipo", "Preço", "Qtd", "Total item"])
        self.items_table.horizontalHeader().setStretchLastSection(True)
        self.items_table.itemChanged.connect(self._on_item_changed)
        form.addWidget(self.items_table)

        self.tracking = LabeledInput("Tracking", "Disponível a partir de pronta_envio")
        self.shipping = LabeledMoneyField("Portes")
        self.shipping.set_value(0.0)
        form.addWidget(FormRow(self.tracking, self.shipping))

        self.notes = LabeledTextArea("Notas")
        form.addWidget(self.notes)

        self.summary = SummaryCard("Resumo", [("Subtotal", "€0.00"), ("Portes", "€0.00"), ("Total", "€0.00")])
        form.addWidget(self.summary)

        self.error = ErrorText()
        form.addWidget(self.error)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

        self.actions = FormActions("Cancelar", "Guardar encomenda")
        self.actions.cancel_button.clicked.connect(self.reject)
        self.actions.confirm_button.clicked.connect(self._save)
        root.addWidget(self.actions)

        self.shipping.input.valueChanged.connect(self._refresh_items_table)
        self.client_combo.input.currentTextChanged.connect(lambda _v: self._validate_form())
        self.status.input.currentTextChanged.connect(lambda _v: self._on_status_changed())
        self.tracking.input.textChanged.connect(lambda _v: self._validate_form())
        self._load_data()
        self._sync_state_dependent_fields()
        self._validate_form()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        animate_dialog_open(self)

    def reject(self) -> None:  # type: ignore[override]
        self._close_with_animation(super().reject)

    def _parse_selected_id(self, value: str) -> int:
        try:
            return int(value.split(" - ", 1)[0])
        except Exception:
            return 0

    def _find_product(self, product_id: int) -> dict[str, object] | None:
        for product in self.products:
            if int(product["id"]) == product_id:
                return dict(product)
        return None

    def _add_item(self) -> None:
        product_id = self._parse_selected_id(self.product_combo.value())
        quantity = int(self.quantity.value())
        if product_id <= 0:
            self.error.set_error("Selecione um produto válido")
            return
        if quantity <= 0:
            self.error.set_error("Quantidade inválida")
            return

        for item in self.items_buffer:
            if item["product_id"] == product_id:
                item["quantidade"] += quantity
                self.error.set_error(None)
                self._refresh_items_table()
                return

        self.items_buffer.append({"product_id": product_id, "quantidade": quantity})
        self.error.set_error(None)
        self._refresh_items_table()
        self._validate_form()

    def _remove_selected_item(self) -> None:
        selected = self.items_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        if 0 <= row < len(self.items_buffer):
            self.items_buffer.pop(row)
            self._refresh_items_table()
            self._validate_form()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 3:
            return
        row = item.row()
        if row >= len(self.items_buffer):
            return
        try:
            quantity = int(item.text())
        except ValueError:
            quantity = 1
        self.items_buffer[row]["quantidade"] = max(1, quantity)
        self._refresh_items_table()

    def _load_data(self) -> None:
        if self.order is None:
            self._refresh_items_table()
            return

        client_id = int(self.order.get("client_id", 0))
        for index, option in enumerate(self.client_options):
            if option.startswith(f"{client_id} - "):
                self.client_combo.input.setCurrentIndex(index)
                break

        status = str(self.order.get("estado", "rascunho"))
        status_index = self.status.input.findText(status)
        if status_index >= 0:
            self.status.input.setCurrentIndex(status_index)
        self.payment.input.setCurrentIndex(1 if int(self.order.get("pago", 0)) else 0)
        self.tracking.set_text(str(self.order.get("tracking", "")))
        self.shipping.set_value(float(self.order.get("portes", 0.0)))
        self.notes.input.setPlainText(str(self.order.get("notas", "")))

        order_id = int(self.order.get("id", 0))
        for order_item in self.order_service.get_order_items(order_id):
            self.items_buffer.append({"product_id": int(order_item["product_id"]), "quantidade": int(order_item["quantidade"])})
        self._refresh_items_table()
        self._sync_state_dependent_fields()

    def _refresh_items_table(self) -> None:
        self.items_table.blockSignals(True)
        self.items_table.setRowCount(len(self.items_buffer))

        subtotal = Decimal("0.00")
        for idx, item in enumerate(self.items_buffer):
            product = self._find_product(item["product_id"])
            if product is None:
                continue
            unit_price = Decimal(str(product["preco"])).quantize(Decimal("0.01"))
            qty = int(item["quantidade"])
            item_total = unit_price * Decimal(qty)
            subtotal += item_total

            name_item = QTableWidgetItem(str(product["nome"]))
            type_item = QTableWidgetItem(str(product["tipo_producao"]))
            price_item = QTableWidgetItem(format_currency(unit_price))
            qty_item = QTableWidgetItem(str(qty))
            total_item = QTableWidgetItem(format_currency(item_total))

            for cell in [name_item, type_item, price_item, total_item]:
                cell.setFlags((cell.flags() | Qt.ItemIsSelectable | Qt.ItemIsEnabled) & ~Qt.ItemIsEditable)
            qty_item.setFlags(qty_item.flags() | Qt.ItemIsEditable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.items_table.setItem(idx, 0, name_item)
            self.items_table.setItem(idx, 1, type_item)
            self.items_table.setItem(idx, 2, price_item)
            self.items_table.setItem(idx, 3, qty_item)
            self.items_table.setItem(idx, 4, total_item)

        self.items_table.blockSignals(False)
        self._update_summary(subtotal)
        self._validate_form()

    def _update_summary(self, subtotal: Decimal) -> None:
        shipping = Decimal(str(self.shipping.value())).quantize(Decimal("0.01"))
        total = subtotal + shipping
        self.summary.set_rows(
            [
                ("Subtotal", format_currency(subtotal)),
                ("Portes", format_currency(shipping)),
                ("Total", format_currency(total)),
            ]
        )

    def _save(self) -> None:
        if self._saving or not self._validate_form():
            return
        self._saving = True
        self.actions.confirm_button.setEnabled(False)
        self.actions.confirm_button.setText("A guardar...")
        client_id = self._parse_selected_id(self.client_combo.value())
        if client_id <= 0:
            self.error.set_error("Selecione um cliente válido")
            self._saving = False
            self.actions.confirm_button.setText("Guardar encomenda")
            self._validate_form()
            return
        if not self.items_buffer:
            self.error.set_error("Adicione pelo menos um item")
            self._saving = False
            self.actions.confirm_button.setText("Guardar encomenda")
            self._validate_form()
            return

        payload = {
            "client_id": client_id,
            "estado": self.status.value(),
            "pago": 1 if self.payment.value().startswith("1") else 0,
            "tracking": self.tracking.text(),
            "metodo_pagamento": "manual",
            "portes": str(Decimal(str(self.shipping.value())).quantize(Decimal("0.01"))),
            "data_prevista": "",
            "notas": self.notes.text(),
            "items": [{"product_id": item["product_id"], "quantidade": item["quantidade"]} for item in self.items_buffer],
        }
        try:
            if self.order and self.order.get("id") is not None:
                order_id = int(self.order["id"])
                self.order_service.update_order(order_id, payload)
                self.saved_id = order_id
            else:
                self.saved_id = self.order_service.create_order(payload)
        except ValueError as exc:
            self.error.set_error(str(exc))
            self._saving = False
            self.actions.confirm_button.setText("Guardar encomenda")
            self._validate_form()
            return

        self.error.set_error(None)
        self.actions.confirm_button.setText("Guardado")
        QTimer.singleShot(320, lambda: self._close_with_animation(super().accept))

    def _validate_form(self) -> bool:
        valid = True
        status = self.status.value()
        if self._parse_selected_id(self.client_combo.value()) <= 0:
            self.client_combo.set_error("Cliente obrigatório")
            valid = False
        else:
            self.client_combo.set_error(None)

        if not self.items_buffer:
            self.error.set_error("Adicione pelo menos um item")
            valid = False
        elif any(int(item.get("quantidade", 0)) <= 0 for item in self.items_buffer):
            self.error.set_error("Todos os itens precisam de quantidade válida")
            valid = False
        else:
            self.error.set_error(None)

        tracking_value = self.tracking.text().strip()
        if status in TRACKING_REQUIRED_STATES and not tracking_value:
            self.tracking.set_error("Tracking obrigatório para este estado")
            valid = False
        elif tracking_value and status not in TRACKING_ALLOWED_STATES:
            self.tracking.set_error("Tracking só pode ser definido a partir de pronta_envio")
            valid = False
        else:
            self.tracking.set_error(None)

        if status == "rascunho" and self.payment.value().startswith("1"):
            self.payment.set_error("Rascunho não pode estar pago")
            valid = False
        elif status in PAID_REQUIRED_STATES and not self.payment.value().startswith("1"):
            self.payment.set_error("Estado exige encomenda paga")
            valid = False
        else:
            self.payment.set_error(None)

        self.actions.confirm_button.setEnabled(valid)
        return valid

    def _on_status_changed(self) -> None:
        self._sync_state_dependent_fields()
        self._validate_form()

    def _sync_state_dependent_fields(self) -> None:
        status = self.status.value()
        tracking_allowed = status in TRACKING_ALLOWED_STATES
        self.tracking.input.setEnabled(tracking_allowed)
        if not tracking_allowed:
            self.tracking.set_text("")
            self.tracking.input.setToolTip("Tracking disponível a partir de pronta_envio")
        else:
            self.tracking.input.setToolTip("Tracking obrigatório em expedida/concluida")

        requires_paid = status in PAID_REQUIRED_STATES
        is_draft = status == "rascunho"
        self._set_payment_option_enabled(0, enabled=not requires_paid)
        self._set_payment_option_enabled(1, enabled=not is_draft)

        if requires_paid:
            self.payment.input.setCurrentIndex(1)
        elif is_draft:
            self.payment.input.setCurrentIndex(0)


    def _set_payment_option_enabled(self, index: int, *, enabled: bool) -> None:
        model = self.payment.input.model()
        if isinstance(model, QStandardItemModel):
            item = model.item(index)
            if item is None:
                return
            flags = item.flags()
            if enabled:
                item.setFlags(flags | Qt.ItemIsEnabled)
            else:
                item.setFlags(flags & ~Qt.ItemIsEnabled)
        tone = "#E5E7EB" if enabled else "#64748B"
        self.payment.input.setItemData(index, QColor(tone), Qt.ForegroundRole)

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
