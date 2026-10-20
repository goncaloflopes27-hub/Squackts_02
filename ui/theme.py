from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class ColorTokens:
    background: str = "#0C0D11"
    surface: str = "#13151B"
    surface_alt: str = "#1A1D25"
    surface_elevated: str = "#222630"
    border: str = "#242832"
    border_strong: str = "#343A47"
    text_primary: str = "#F2F3F5"
    text_secondary: str = "#A9AFBC"
    text_muted: str = "#70778A"
    primary: str = "#FF8A1F"
    primary_hover: str = "#FFA047"
    primary_pressed: str = "#E6760F"
    on_primary: str = "#1A1005"
    brand_red: str = "#D93A3A"
    logo_badge: str = "#F5F1EA"
    success: str = "#2FD08A"
    warning: str = "#FFC83D"
    danger: str = "#FF5470"
    info: str = "#4EA1FF"
    accent_violet: str = "#FF8A1F"
    overlay_soft: str = "#222630"
    focus_ring: str = "#FF8A1F"


@dataclass(frozen=True)
class RadiusTokens:
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 20
    pill: int = 999


@dataclass(frozen=True)
class SpacingTokens:
    xs: int = 4
    sm: int = 8
    md: int = 16
    lg: int = 24
    xl: int = 32
    xxl: int = 40


@dataclass(frozen=True)
class TypographyTokens:
    caption: int = 12
    body: int = 14
    section: int = 16
    title: int = 28
    metric: int = 36


COLORS = ColorTokens()
RADIUS = RadiusTokens()
SPACING = SpacingTokens()
TYPE = TypographyTokens()


def translucent(color: str, alpha: int = 24) -> str:
    """Qt supports rgba(); eight-digit CSS hex has a different channel order."""
    return f"rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, {alpha})"


def app_stylesheet() -> str:
    c = COLORS
    icons = Path(__file__).resolve().parent / "icons"
    arrow = (icons / "chevron-down.svg").as_posix()
    check = (icons / "check.svg").as_posix()
    return f"""
    QWidget {{
        color: {c.text_primary};
        font-family: 'Inter';
        font-size: 14px;
    }}
    QMainWindow, QFrame#MainFrame, QWidget#MainFrame {{ background-color: {c.background}; }}
    QLabel {{ background: transparent; }}
    QGroupBox {{
        border: 1px solid {c.border};
        border-radius: {RADIUS.lg}px;
        margin-top: 10px;
        padding-top: 10px;
    }}
    QGroupBox::title {{
        color: {c.text_secondary};
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
    }}

    QDialog {{
        background: {c.surface};
        border: 1px solid {c.border_strong};
        border-radius: {RADIUS.xl}px;
    }}
    QFrame {{
        background: transparent;
    }}
    QScrollArea {{
        background: transparent;
        border: 1px solid {c.border};
        border-radius: {RADIUS.lg}px;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit {{
        background: {c.surface_alt};
        border: 1px solid {c.border};
        border-radius: {RADIUS.sm}px;
        padding: 8px 12px;
        color: {c.text_primary};
        selection-background-color: {c.primary};
        min-height: 20px;
    }}
    QTextEdit, QPlainTextEdit {{
        min-height: 60px;
        padding-top: 10px;
    }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QTextEdit:hover, QDateEdit:hover, QDateTimeEdit:hover {{ border: 1px solid {c.border_strong}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus, QDateEdit:focus, QDateTimeEdit:focus {{
        border: 2px solid {c.primary};
        background: {c.surface_elevated};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
        margin-right: 6px;
    }}
    QComboBox::down-arrow {{
        image: url("{arrow}");
        width: 12px;
        height: 12px;
    }}
    QComboBox QAbstractItemView {{
        border: 1px solid {c.border_strong};
        background: {c.surface};
        selection-background-color: {c.surface_elevated};
        outline: 0;
    }}
    QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QDateEdit:disabled, QDateTimeEdit:disabled {{
        color:{c.text_muted};
        background:{c.surface};
    }}
    QTableView {{
        background: {c.surface_alt};
        border: 1px solid {c.border};
        border-radius: {RADIUS.lg}px;
        gridline-color: {c.border};
        selection-background-color: {c.overlay_soft};
        selection-color: {c.text_primary};
        alternate-background-color: {c.surface};
        outline: 0;
        padding: 4px;
    }}
    QTableView::item {{
        border-bottom: 1px solid {c.border};
        padding: 8px 10px;
    }}
    QTableView::item:hover {{ background: {c.surface_elevated}; }}
    QTableView::item:selected {{
        background: {c.overlay_soft};
        border-bottom: 1px solid {c.primary};
    }}
    QTableCornerButton::section {{
        background: {c.surface};
        border: none;
        border-bottom: 1px solid {c.border};
        border-right: 1px solid {c.border};
    }}
    QHeaderView::section {{
        background-color: {c.surface};
        color: {c.text_secondary};
        border: none;
        border-bottom: 1px solid {c.border};
        border-right: 1px solid {c.border};
        padding: 12px 10px;
        font-weight: 600;
    }}
    QHeaderView::section:last {{ border-right: none; }}
    QPushButton {{
        min-height: 20px;
    }}
    QPushButton:focus, QToolButton:focus {{ border: 1px solid {c.focus_ring}; }}
    QTableView:focus {{ border: 1px solid {c.focus_ring}; }}
    QCheckBox {{ spacing: 9px; padding: 5px 0; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid {c.border_strong}; border-radius: 5px; background: {c.surface_alt}; }}
    QCheckBox::indicator:checked {{ image:url("{check}"); background: {c.primary}; border: 1px solid {c.focus_ring}; }}
    QCheckBox:focus {{ color: {c.focus_ring}; }}
    QMenu {{ background: {c.surface_elevated}; border: 1px solid {c.border_strong}; padding: 6px; }}
    QMenu::item {{ padding: 8px 18px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {c.overlay_soft}; }}
    QCalendarWidget QWidget {{ background:{c.surface_alt}; color:{c.text_primary}; }}
    QCalendarWidget QAbstractItemView {{ background:{c.surface}; color:{c.text_primary}; selection-background-color:{c.primary}; }}
    QScrollBar:vertical {{
        background: {c.surface};
        width: 10px;
        margin: 2px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical {{
        background: {c.border_strong};
        border-radius: 5px;
        min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{ background:{c.primary}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; background: transparent; }}
    QScrollBar:horizontal {{
        background: {c.surface};
        height: 10px;
        margin: 2px;
        border-radius: 5px;
    }}
    QScrollBar::handle:horizontal {{
        background: {c.border_strong};
        border-radius: 5px;
        min-width: 28px;
    }}
    QScrollBar::handle:horizontal:hover {{ background:{c.primary}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; border: none; background: transparent; }}
    QToolTip {{
        background: {c.surface_elevated};
        color: {c.text_primary};
        border: 1px solid {c.border_strong};
        padding: 6px 8px;
    }}
    """


def initialize_theme(app: QApplication) -> None:
    """One embedded typeface and one palette, including native Qt popups."""
    if not app.property("interLoaded"):
        font_id = QFontDatabase.addApplicationFont(str(Path(__file__).parent / "assets/fonts/Inter.ttf"))
        if font_id < 0:
            raise RuntimeError("A fonte Inter incluída na aplicação não foi encontrada.")
        app.setProperty("interLoaded", True)
    font = QFont("Inter")
    font.setPixelSize(TYPE.body)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, COLORS.background),
        (QPalette.ColorRole.WindowText, COLORS.text_primary),
        (QPalette.ColorRole.Base, COLORS.surface),
        (QPalette.ColorRole.AlternateBase, COLORS.surface_alt),
        (QPalette.ColorRole.Text, COLORS.text_primary),
        (QPalette.ColorRole.Button, COLORS.surface_alt),
        (QPalette.ColorRole.ButtonText, COLORS.text_primary),
        (QPalette.ColorRole.Highlight, COLORS.primary),
        (QPalette.ColorRole.HighlightedText, COLORS.on_primary),
        (QPalette.ColorRole.PlaceholderText, COLORS.text_secondary),
        (QPalette.ColorRole.ToolTipBase, COLORS.surface_elevated),
        (QPalette.ColorRole.ToolTipText, COLORS.text_primary),
    ):
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(COLORS.text_muted))
    app.setPalette(palette)
    app.setStyleSheet(app_stylesheet())
