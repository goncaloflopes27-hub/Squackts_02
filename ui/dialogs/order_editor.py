from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QScrollArea,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.client_service import ClientService
from services.image_service import ImageService
from services.order_domain import initial_creation_states_ordered
from services.order_service import OrderService
from services.product_service import ProductService
from ui.animations import animate_dialog_open
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
    Toolbar,
)
from ui.dialogs.client_editor import ClientEditorDialog
from ui.dialogs.editor_base import EditorDialog
from ui.theme import SPACING
from utils import format_currency


class OrderEditorDialog(EditorDialog):
    def __init__(
        self,
        order_service: OrderService,
        client_service: ClientService,
        product_service: ProductService,
        order: dict[str, object] | None = None,
        parent: QWidget | None = None,
        initial_client_id: int | None = None,
        image_service: ImageService | None = None,
    ) -> None:
        super().__init__(parent)
        self.order_service = order_service
        self.client_service = client_service
        self.product_service = product_service
        self.order = order
        self.image_service = image_service
        self._idempotency_key = str(uuid4())
        self._artwork_path = ""
        self.variants: list[dict[str, object]] = []
        self.saved_id: int | None = None
        self.items_buffer: list[dict[str, object]] = []
        self._submission_error: str | None = None
        self._saving = False

        self.setWindowTitle("Editor de Encomenda")
        self.setModal(True)
        self.resize(980, 780)

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)
        root.addWidget(
            ModalHeader(
                "Editar encomenda" if order else "Nova encomenda",
                "Editor real com múltiplos itens e cálculo financeiro",
            )
        )

        content = QWidget()
        form = QVBoxLayout(content)
        form.setSpacing(SPACING.sm)

        clients = self.client_service.list_clients()
        self.clients = [c for c in clients if int(c["ativo"]) or (order and int(c["id"]) == int(order["client_id"]))]
        self.client_options = [f"{c['id']} - {c['nome']}" for c in self.clients] or ["0 - Sem clientes"]
        self.products = self.product_service.list_products()
        self.product_options = [f"{p['id']} - {p['nome']} ({p['sku']})" for p in self.products if int(p["ativo"])] or [
            "0 - Sem produtos"
        ]

        self.client_combo = LabeledComboBox("Cliente", self.client_options)
        status_options = initial_creation_states_ordered()
        if order and str(order.get("estado", "rascunho")) not in status_options:
            status_options = [str(order["estado"])]
        self.status = LabeledComboBox("Estado", status_options)
        labels = {
            "rascunho": "Rascunho",
            "confirmada": "Confirmada",
            "em_producao": "Em produção",
            "pronta_envio": "Pronta para envio",
            "expedida": "Expedida",
            "concluida": "Concluída",
            "cancelada": "Cancelada",
        }
        self.status.input.clear()
        for state in status_options:
            self.status.input.addItem(labels.get(state, state), state)
        self.payment = LabeledComboBox("Pagamento", ["Pendente", "Pago"])
        form.addWidget(DividerLabel("Cliente e estado"))
        form.addWidget(FormRow(self.client_combo, self.status, self.payment))
        quick_client = SecondaryButton("Criar cliente")
        quick_client.clicked.connect(self._create_client)
        form.addWidget(quick_client)
        self._make_searchable(self.client_combo.input)

        self.product_combo = LabeledComboBox("Produto", self.product_options)
        self._make_searchable(self.product_combo.input)
        self.variant_combo = LabeledComboBox("Variante", [])
        self.personalization = LabeledInput("Personalização", "Texto, referência ou instruções para produzir…")
        self.art_button = SecondaryButton("Associar ficheiro de arte…")
        self.art_button.setEnabled(self.image_service is not None)
        self.art_button.clicked.connect(self._choose_artwork)
        self.product_combo.input.currentTextChanged.connect(lambda _text: self._load_variants())
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
        form.addWidget(FormRow(self.variant_combo, self.personalization))
        form.addWidget(self.art_button)
        self._load_variants()

        self.items_table = DataTable(0, 5)
        self.items_table.set_editable_columns({3})
        self.items_table.setHorizontalHeaderLabels(["Produto", "Tipo", "Preço", "Qtd", "Total item"])
        self.items_table.horizontalHeader().setStretchLastSection(True)
        self.items_table.itemChanged.connect(self._on_item_changed)
        form.addWidget(self.items_table)

        self.tracking = LabeledInput("Tracking", "Disponível quando a encomenda está pronta para envio")
        self.shipping = LabeledMoneyField("Portes")
        self.shipping.set_value(0.0)
        form.addWidget(FormRow(self.tracking, self.shipping))

        self.has_deadline = QCheckBox("Definir data prevista")
        self.deadline = QDateEdit(QDate.currentDate())
        self.deadline.setCalendarPopup(True)
        self.deadline.setDisplayFormat("dd/MM/yyyy")
        self.deadline.setEnabled(False)
        self.has_deadline.toggled.connect(self.deadline.setEnabled)
        form.addWidget(Toolbar(self.has_deadline, self.deadline))

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

        self.form_actions = FormActions("Cancelar", "Guardar encomenda")
        self.form_actions.cancel_button.clicked.connect(self.reject)
        self.form_actions.confirm_button.clicked.connect(self._save)
        root.addWidget(self.form_actions)

        self.shipping.input.valueChanged.connect(self._refresh_items_table)
        self.client_combo.input.currentTextChanged.connect(lambda _v: self._validate_form())
        self.status.input.currentTextChanged.connect(lambda _v: self._validate_form())
        self.tracking.input.textChanged.connect(lambda _v: self._validate_form())
        self._load_data()
        self._validate_form()
        if initial_client_id is not None:
            self._select_client(initial_client_id)
        self._mark_clean()

    def _load_variants(self) -> None:
        product_id = self._parse_selected_id(self.product_combo.value())
        self.variant_combo.input.clear()
        self.variants = (
            [dict(v) for v in self.product_service.list_variants(product_id) if int(v["ativo"])]
            if product_id > 0
            else []
        )
        for variant in self.variants:
            label = " / ".join(str(variant[key]) for key in ("tamanho", "cor") if variant[key]) or "Principal"
            self.variant_combo.input.addItem(
                f"{label} · {variant['sku']} · {format_currency(variant['preco'])}", int(variant["id"])
            )

    def _choose_artwork(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Arte de impressão", "", "Imagens (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not filename or self.image_service is None:
            return
        try:
            self._artwork_path = self.image_service.import_image(filename).image_path
        except (ValueError, OSError) as exc:
            self.error.set_error(str(exc))
            return
        self.art_button.setText("Arte associada ✓")

    @staticmethod
    def _make_searchable(combo: QComboBox) -> None:
        combo.setEditable(True)
        combo.setInsertPolicy(combo.InsertPolicy.NoInsert)
        completer = combo.completer()
        assert completer is not None
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def _select_client(self, client_id: int) -> None:
        for index in range(self.client_combo.input.count()):
            if self.client_combo.input.itemText(index).startswith(f"{client_id} - "):
                self.client_combo.input.setCurrentIndex(index)
                return

    def _create_client(self) -> None:
        dialog = ClientEditorDialog(self.client_service, parent=self)
        if not dialog.exec() or dialog.saved_id is None:
            return
        clients = self.client_service.list_clients()
        self.client_options = [f"{client['id']} - {client['nome']}" for client in clients if int(client["ativo"])]
        self.client_combo.input.clear()
        self.client_combo.input.addItems(self.client_options)
        self._select_client(dialog.saved_id)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        animate_dialog_open(self)

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

        variant_id = self.variant_combo.input.currentData()
        personalization = self.personalization.text()
        for item in self.items_buffer:
            if (
                item["product_id"] == product_id
                and item.get("variant_id") == variant_id
                and item.get("personalization", "") == personalization
                and item.get("artwork_path", "") == self._artwork_path
            ):
                item["quantidade"] = int(item["quantidade"]) + quantity
                self.error.set_error(None)
                self._refresh_items_table()
                return

        self.items_buffer.append(
            {
                "product_id": product_id,
                "quantidade": quantity,
                "variant_id": variant_id,
                "personalization": personalization,
                "artwork_path": self._artwork_path,
            }
        )
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
        status_index = self.status.input.findData(status)
        if status_index >= 0:
            self.status.input.setCurrentIndex(status_index)
        self.payment.input.setCurrentIndex(1 if int(self.order.get("pago", 0)) else 0)
        self.tracking.set_text(str(self.order.get("tracking", "")))
        self.shipping.set_value(float(self.order.get("portes", 0.0)))
        self.notes.input.setPlainText(str(self.order.get("notas", "")))
        deadline = str(self.order.get("data_prevista", ""))
        if deadline:
            parsed = QDate.fromString(deadline[:10], "yyyy-MM-dd")
            if parsed.isValid():
                self.has_deadline.setChecked(True)
                self.deadline.setDate(parsed)

        order_id = int(self.order.get("id", 0))
        for order_item in self.order_service.get_order_items(order_id):
            self.items_buffer.append(dict(order_item))
        self._refresh_items_table()

    def _refresh_items_table(self) -> None:
        self.items_table.blockSignals(True)
        self.items_table.setRowCount(len(self.items_buffer))

        subtotal = Decimal("0.00")
        for idx, item in enumerate(self.items_buffer):
            product = self._find_product(int(item["product_id"]))
            if product is None:
                continue
            variants = [dict(v) for v in self.product_service.list_variants(int(item["product_id"]))]
            variant = next((v for v in variants if v["id"] == item.get("variant_id")), None)
            unit_price = Decimal(
                str(item.get("preco_unit", variant["preco"] if variant else product["preco"]))
            ).quantize(Decimal("0.01"))
            qty = int(item["quantidade"])
            item_total = unit_price * Decimal(qty)
            subtotal += item_total

            name = str(item.get("nome_snapshot", product["nome"]))
            if variant:
                name += " · " + " / ".join(str(variant[k]) for k in ("tamanho", "cor") if variant[k])
            if item.get("personalization"):
                name += " · " + str(item["personalization"])
            name_item = QTableWidgetItem(name)
            type_item = QTableWidgetItem(
                {"print_on_demand": "A pedido", "stock_fisico": "Stock físico", "misto": "Misto"}.get(
                    str(product["tipo_producao"]), str(product["tipo_producao"])
                )
            )
            price_item = QTableWidgetItem(format_currency(unit_price))
            qty_item = QTableWidgetItem(str(qty))
            total_item = QTableWidgetItem(format_currency(item_total))

            for cell in [name_item, type_item, price_item, total_item]:
                cell.setFlags(
                    (cell.flags() | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                    & ~Qt.ItemFlag.ItemIsEditable
                )
            qty_item.setFlags(
                qty_item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            )
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
        self.form_actions.confirm_button.setEnabled(False)
        self.form_actions.confirm_button.setText("A guardar...")
        client_id = self._parse_selected_id(self.client_combo.value())
        if client_id <= 0:
            self.error.set_error("Selecione um cliente válido")
            return
        if not self.items_buffer:
            self.error.set_error("Adicione pelo menos um item")
            return

        payload = {
            "client_id": client_id,
            "estado": str(self.status.input.currentData()),
            "pago": 1 if self.payment.input.currentIndex() == 1 else 0,
            "tracking": self.tracking.text(),
            "metodo_pagamento": "manual",
            "portes": str(Decimal(str(self.shipping.value())).quantize(Decimal("0.01"))),
            "data_prevista": self.deadline.date().toString("yyyy-MM-dd") if self.has_deadline.isChecked() else "",
            "notas": self.notes.text(),
            "items": [
                {
                    key: item[key]
                    for key in ("product_id", "quantidade", "variant_id", "personalization", "artwork_path")
                    if key in item
                }
                for item in self.items_buffer
            ],
            "idempotency_key": self._idempotency_key,
        }
        try:
            if self.order and self.order.get("id") is not None:
                order_id = int(self.order["id"])
                self.order_service.update_order(order_id, payload)
                self.saved_id = order_id
            else:
                self.saved_id = self.order_service.create_order(payload)
        except (ValueError, OSError) as exc:
            self._submission_error = str(exc)
            self.error.set_error(self._submission_error)
            self._reveal_error(self.error)
            self._saving = False
            self.form_actions.confirm_button.setText("Guardar encomenda")
            self._validate_form()
            return

        self.error.set_error(None)
        self.form_actions.confirm_button.setText("Guardado")
        self._accept_saved()

    def _validate_form(self) -> bool:
        valid = True
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
            self.error.set_error(self._submission_error)

        self.form_actions.confirm_button.setEnabled(valid and not self._saving)
        return valid
