from __future__ import annotations

from collections.abc import Callable
from functools import partial

from PySide6.QtCore import QObject, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QResizeEvent, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config import APP_NAME, WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH
from service_container import ServiceContainer
from ui.animations import PageTransition, reduced_motion
from ui.command_palette import CommandPalette
from ui.components import SearchInput, show_toast
from ui.pages import ClientsPage, DashboardPage, OrdersPage, ProductionPage, ProductsPage, SystemPage
from ui.preferences import LocalPreferences, PreferencesDialog
from ui.sidebar import PAGES, Sidebar
from ui.theme import app_stylesheet, initialize_theme
from ui.topbar import TopBar


class _EventBridge(QObject):
    changed = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self, container: ServiceContainer, *, available_geometry: QRect | None = None) -> None:
        super().__init__()
        application = QApplication.instance()
        if isinstance(application, QApplication):
            initialize_theme(application)
        self.container = container
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        screen = self.screen()
        if screen is not None:
            available = available_geometry if available_geometry is not None else screen.availableGeometry()
            self.setMinimumSize(min(WINDOW_MIN_WIDTH, max(320, available.width() - 24)), min(WINDOW_MIN_HEIGHT, max(320, available.height() - 48)))
        self.setStyleSheet(app_stylesheet())
        self.current_page_key = "dashboard"
        self._searches: dict[str, str] = {}
        self._dirty: set[str] = set()
        self._manual_compact: bool | None = None
        self._unsubscribe: Callable[[], None] | None = None
        self._closing = False
        self.preferences = getattr(container, "preferences", None) or LocalPreferences(str(container.db_path.parent / "ui.ini"))
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
        self.topbar.commands_requested.connect(self.open_commands)
        self.topbar.menu_requested.connect(self._toggle_sidebar)
        self.topbar.alerts_requested.connect(self._open_alerts)
        self.topbar.preferences_requested.connect(self.open_preferences)
        content_layout.addWidget(self.topbar)
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        layout.addWidget(content, 1)
        self.page_map: dict[str, int] = {}
        self.page_refs: dict[str, QWidget] = {}
        self.page_scrolls: dict[str, QScrollArea] = {}
        self._register_pages()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._flush_invalidations)
        self._event_bridge = _EventBridge(self)
        self._event_bridge.changed.connect(self.invalidate_pages, Qt.ConnectionType.QueuedConnection)
        events = getattr(container, "events", None)
        if events is not None:
            self._unsubscribe = events.subscribe(self._event_bridge.changed.emit)
        self._install_shortcuts()
        self._apply_preferences()
        self.navigate("dashboard")

    def _register_pages(self) -> None:
        images = getattr(self.container, "images", None)
        pages = {
            "dashboard": DashboardPage(self.container.dashboard),
            "orders": OrdersPage(self.container.orders, self.container.clients, self.container.products, image_service=images),
            "products": ProductsPage(self.container.products, image_service=images),
            "clients": ClientsPage(self.container.clients, self.container.orders, self.container.products, image_service=images),
            "production": ProductionPage(self.container.production, inventory_service=getattr(self.container, "inventory", None)),
            "system": SystemPage(self.container),
        }
        for key, page in pages.items():
            # Only the shell owns contextual text search; page filters remain local.
            search = getattr(page, "search_input", None)
            if isinstance(search, SearchInput):
                search.hide()
            # The contextual primary action lives in the header, not in duplicate toolbars.
            for button in page.findChildren(QPushButton):
                if button.text() in {"Nova encomenda", "Novo produto", "Novo cliente"}:
                    button.hide()
            empty = getattr(page, "empty", None)
            create = getattr(page, "_open_create", None)
            if empty is not None and callable(create):
                empty.set_action({"orders": "Criar encomenda", "products": "Criar produto", "clients": "Criar cliente"}[key], create)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet("QScrollArea {border:none; background:transparent;}")
            scroll.setWidget(page)
            self.page_map[key] = self.stack.addWidget(scroll)
            self.page_refs[key] = page
            self.page_scrolls[key] = scroll
        for page in pages.values():
            navigation = getattr(page, "navigate_requested", None)
            if navigation is not None:
                navigation.connect(self.navigate_to_results)

    def navigate(self, page_key: str) -> None:
        if page_key not in self.page_map:
            return
        previous = self.current_page_key
        self.current_page_key = page_key
        self.stack.setCurrentIndex(self.page_map[page_key])
        self.sidebar.set_current(page_key)
        self._sync_topbar(page_key)
        if page_key in self._dirty or previous != page_key:
            self._refresh_page(page_key)
        if previous != page_key:
            if not reduced_motion(self):
                self._page_transition = PageTransition(self.page_scrolls[page_key], self.stack)

    def navigate_to_results(self, page_key: str, query: str = "") -> None:
        self.navigate(page_key)
        page = self.page_refs.get(page_key)
        state_filter = getattr(page, "_set_status_filter", None)
        if query and callable(state_filter):
            self.topbar.search.clear()
            state_filter(query)
        elif query:
            self.topbar.search.setText(query)

    def _sync_topbar(self, page_key: str) -> None:
        page = self.page_refs[page_key]
        contexts = {
            "dashboard": ("Hoje", "O teu atelier, organizado", "Pesquisar encomendas recentes…", "Atualizar", None),
            "orders": ("Encomendas", "Da confirmação à entrega", "Pesquisar número, cliente ou tracking…", "Nova encomenda", "_open_create"),
            "products": ("Catálogo", "Produtos e disponibilidade", "Pesquisar produto ou SKU…", "Novo produto", "_open_create"),
            "clients": ("Clientes", "Contactos e relacionamento", "Pesquisar nome, email ou telefone…", "Novo cliente", "_open_create"),
            "production": ("Produção", "Trabalho a executar", "Pesquisar encomenda, cliente ou item…", "Atualizar fila", None),
            "system": ("Sistema", "Diagnóstico e recuperação", "Pesquisar eventos…", "Atualizar", None),
        }
        title, subtitle, placeholder, primary_label, method = contexts[page_key]
        self.topbar.set_context(
            title=title, subtitle=subtitle, search_placeholder=placeholder,
            primary_action_label=primary_label,
            primary_action=getattr(page, method, None) if method else self.refresh_current,
            secondary_action_label="Atualizar" if method else None,
            secondary_action=self.refresh_current if method else None,
            search_text=self._searches.get(page_key, ""),
            search_enabled=callable(getattr(page, "apply_search", None)),
        )

    def _handle_global_search(self, text: str) -> None:
        key = self.current_page_key
        self._searches[key] = text
        search = getattr(self.page_refs[key], "apply_search", None)
        if callable(search):
            try:
                search(text)
            except Exception as exc:
                show_toast(self, f"Não foi possível pesquisar: {exc}", "danger")

    def invalidate_pages(self, *topics: str) -> None:
        if self._closing:
            return
        dependencies = {
            "orders": {"orders", "dashboard", "products", "production", "clients", "system"},
            "products": {"products", "dashboard", "orders", "production", "system"},
            "clients": {"clients", "orders", "dashboard", "system"},
            "production": {"production", "orders", "products", "dashboard", "system"},
            "inventory": {"production", "orders", "products", "dashboard", "system"},
            "settings": {"system"},
        }
        for topic in topics or ("all",):
            self._dirty.update(self.page_refs if topic == "all" else dependencies.get(topic, {topic}))
        if hasattr(self, "_refresh_timer"):
            self._refresh_timer.start(0)

    def _flush_invalidations(self) -> None:
        if QApplication.activeModalWidget() is not None:
            self._refresh_timer.start(150)
            return
        if self.current_page_key in self._dirty:
            self._refresh_page(self.current_page_key)

    def refresh_current(self) -> None:
        self._refresh_page(self.current_page_key)

    def _refresh_page(self, key: str) -> None:
        page = self.page_refs[key]
        refresh = getattr(page, "refresh", None) or getattr(page, "_refresh_logs", None)
        if callable(refresh):
            scroll = self.page_scrolls[key]
            position = scroll.verticalScrollBar().value()
            try:
                refresh()
                self._dirty.discard(key)
                scroll.verticalScrollBar().setValue(position)
            except Exception as exc:
                self._dirty.add(key)
                show_toast(self, f"Não foi possível atualizar esta página: {exc}", "danger")

    def _open_alerts(self) -> None:
        self.navigate("dashboard")
        self._refresh_page("dashboard")
        self.page_scrolls["dashboard"].verticalScrollBar().setValue(0)

    def open_preferences(self) -> None:
        dialog = PreferencesDialog(self.preferences, self)
        dialog.saved.connect(self._apply_preferences)
        dialog.exec()

    def _apply_preferences(self) -> None:
        reduced = self.preferences.get("ui.reduce_motion", "0") == "1"
        self.setProperty("reduceMotion", reduced)
        app = QApplication.instance()
        if app:
            app.setProperty("reduceMotion", reduced)
        self._manual_compact = None
        self._apply_responsive()

    def _toggle_sidebar(self) -> None:
        self._manual_compact = not self.sidebar._compact
        self._apply_responsive()

    def _apply_responsive(self) -> None:
        compact = self.preferences.get("ui.compact_sidebar", "0") == "1" or self.width() < 1480
        self.sidebar.set_compact(compact if self._manual_compact is None else self._manual_compact)
        self.topbar.set_compact(self.width() < 1480)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "preferences") and hasattr(self, "topbar"):
            self._apply_responsive()

    def _install_shortcuts(self) -> None:
        shortcuts: list[tuple[str, Callable[[], None]]] = [
            ("Ctrl+K", self.open_commands), ("Ctrl+F", self._focus_search),
            ("F5", self.refresh_current), ("Ctrl+,", self.open_preferences),
            ("Ctrl+B", self._toggle_sidebar), ("Ctrl+N", self._create_current),
        ]
        for number, (key, _label) in enumerate(PAGES, start=1):
            shortcuts.append((f"Alt+{number}", partial(self.navigate, key)))
        self._shortcuts = []
        for sequence, callback in shortcuts:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

    def open_commands(self) -> None:
        def create_order() -> None:
            self.navigate("orders")
            self._create_current()
        self.command_palette = CommandPalette(self.navigate_to_results, create_order, self)
        self.command_palette.open()

    def _focus_search(self) -> None:
        if self.topbar.search.isEnabled():
            self.topbar.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
            self.topbar.search.selectAll()

    def _create_current(self) -> None:
        create = getattr(self.page_refs[self.current_page_key], "_open_create", None)
        if callable(create):
            create()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._closing = True
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        self._refresh_timer.stop()
        super().closeEvent(event)
