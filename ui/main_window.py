from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from config import APP_NAME, WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH
from service_container import ServiceContainer
from ui.animations import fade_in
from ui.pages import (
    ClientsPage,
    DashboardPage,
    OrdersPage,
    ProductionPage,
    ProductsPage,
    SystemPage,
)
from ui.sidebar import Sidebar
from ui.theme import app_stylesheet
from ui.topbar import TopBar


class MainWindow(QMainWindow):
    def __init__(self, container: ServiceContainer) -> None:
        super().__init__()
        self.container = container
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.setStyleSheet(app_stylesheet())

        root = QWidget()
        root.setObjectName("MainFrame")
        self.setCentralWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar(self.navigate)
        layout.addWidget(self.sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.topbar = TopBar()
        self.topbar.search_changed.connect(self._handle_global_search)
        content_layout.addWidget(self.topbar)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet(
            "QStackedWidget {background: transparent;}"
        )
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self.stack, stretch=1)
        layout.addWidget(content, stretch=1)

        self.page_map: dict[str, int] = {}
        self.page_refs: dict[str, QWidget] = {}
        self._register_pages()
        self.navigate("dashboard")

    def _register_pages(self) -> None:
        pages = {
            "dashboard": DashboardPage(self.container.dashboard),
            "orders": OrdersPage(self.container.orders, self.container.clients, self.container.products),
            "products": ProductsPage(self.container.products),
            "clients": ClientsPage(self.container.clients, self.container.orders),
            "production": ProductionPage(self.container.production),
            "system": SystemPage(self.container),
        }
        for key, page in pages.items():
            index = self.stack.addWidget(page)
            self.page_map[key] = index
            self.page_refs[key] = page

    def navigate(self, page_key: str) -> None:
        index = self.page_map.get(page_key)
        if index is None:
            return
        self.stack.setCurrentIndex(index)
        self._sync_topbar(page_key)
        current = self.stack.currentWidget()
        if current is not None:
            current.setAttribute(Qt.WA_TranslucentBackground, False)
            fade_in(current)

    def _sync_topbar(self, page_key: str) -> None:
        page = self.page_refs.get(page_key)
        if page_key == "dashboard":
            self.topbar.set_context(
                title="Painel",
                subtitle="Resumo operacional em tempo real",
                search_placeholder="Pesquisar no dashboard...",
                primary_action_label="Atualizar",
                primary_action=getattr(page, "refresh", None),
            )
            return
        if page_key == "orders":
            self.topbar.set_context(
                title="Encomendas",
                subtitle="Operação comercial e logística",
                search_placeholder="Pesquisar por número, cliente ou tracking...",
                primary_action_label="Nova encomenda",
                primary_action=getattr(page, "_open_create", None),
                secondary_action_label="Atualizar",
                secondary_action=getattr(page, "refresh", None),
            )
            return
        if page_key == "products":
            self.topbar.set_context(
                title="Catálogo",
                subtitle="Produtos, margens e produção",
                search_placeholder="Pesquisar por nome ou SKU...",
                primary_action_label="Novo produto",
                primary_action=getattr(page, "_open_create", None),
                secondary_action_label="Atualizar",
                secondary_action=getattr(page, "refresh", None),
            )
            return
        if page_key == "clients":
            self.topbar.set_context(
                title="Clientes",
                subtitle="Gestão comercial e relacionamento",
                search_placeholder="Pesquisar por nome, email ou telefone...",
                primary_action_label="Novo cliente",
                primary_action=getattr(page, "_open_create", None),
                secondary_action_label="Atualizar",
                secondary_action=getattr(page, "refresh", None),
            )
            return
        if page_key == "production":
            self.topbar.set_context(
                title="Produção",
                subtitle="Fila e estados de execução",
                search_placeholder="Pesquisar por estado, pedido ou cliente...",
                primary_action_label="Atualizar fila",
                primary_action=getattr(page, "refresh", None),
            )
            return
        self.topbar.set_context(
            title="Sistema",
            subtitle="Backups, logs e diagnóstico",
            search_placeholder="Pesquisar eventos...",
            primary_action_label="Criar backup",
            primary_action=getattr(page, "trigger_primary_action", None),
            secondary_action_label="Atualizar",
            secondary_action=getattr(page, "refresh", None),
        )

    def _handle_global_search(self, text: str) -> None:
        current = self.stack.currentWidget()
        if current is None:
            return
        apply_search = getattr(current, "apply_search", None)
        if callable(apply_search):
            apply_search(text)
