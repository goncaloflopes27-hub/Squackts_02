from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColorTokens:
    background: str = "#0B1020"
    surface: str = "#111827"
    surface_alt: str = "#162033"
    surface_elevated: str = "#1B2740"
    border: str = "#243244"
    border_strong: str = "#334155"
    text_primary: str = "#E5E7EB"
    text_secondary: str = "#94A3B8"
    text_muted: str = "#64748B"
    primary: str = "#3B82F6"
    primary_hover: str = "#2563EB"
    success: str = "#22C55E"
    warning: str = "#F59E0B"
    danger: str = "#EF4444"
    info: str = "#06B6D4"
    accent_violet: str = "#8B5CF6"
    overlay_soft: str = "#1E293B"
    focus_ring: str = "#60A5FA"


@dataclass(frozen=True)
class RadiusTokens:
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 20
    pill: int = 999


@dataclass(frozen=True)
class SpacingTokens:
    xs: int = 6
    sm: int = 10
    md: int = 16
    lg: int = 24
    xl: int = 32
    xxl: int = 40


COLORS = ColorTokens()
RADIUS = RadiusTokens()
SPACING = SpacingTokens()


def app_stylesheet() -> str:
    c = COLORS
    return f"""
    QWidget {{
        color: {c.text_primary};
        font-family: 'Segoe UI', 'Inter', sans-serif;
        font-size: 13px;
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
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {c.surface_alt};
        border: 1px solid {c.border};
        border-radius: {RADIUS.md}px;
        padding: 9px 12px;
        color: {c.text_primary};
        selection-background-color: {c.primary};
        min-height: 40px;
    }}
    QTextEdit, QPlainTextEdit {{
        min-height: 92px;
        padding-top: 10px;
    }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QTextEdit:hover {{ border: 1px solid {c.border_strong}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {{
        border: 1px solid {c.primary};
        background: {c.surface_elevated};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
        margin-right: 6px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid {c.text_secondary};
        width: 0px;
        height: 0px;
    }}
    QComboBox QAbstractItemView {{
        border: 1px solid {c.border_strong};
        background: {c.surface};
        selection-background-color: {c.surface_elevated};
        outline: 0;
    }}
    QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
        color:{c.text_muted};
        background:{c.surface};
    }}
    QTableWidget {{
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
    QTableWidget::item {{
        border-bottom: 1px solid {c.border};
        padding: 8px 10px;
    }}
    QTableWidget::item:hover {{ background: {c.surface_elevated}; }}
    QTableWidget::item:selected {{
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
        text-transform: uppercase;
        letter-spacing: 0.4px;
    }}
    QHeaderView::section:last {{ border-right: none; }}
    QPushButton {{
        min-height: 40px;
    }}
    QPushButton:disabled {{ opacity: 0.7; }}
    QPushButton:focus, QToolButton:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {{
        outline: none;
    }}
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
