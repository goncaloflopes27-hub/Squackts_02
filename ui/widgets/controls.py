from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import COLORS, RADIUS, SPACING, TYPE, translucent
from ui.widgets.common import CONTROL_HEIGHT


class AppCard(QFrame):
    def __init__(self, title: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AppCard")
        self.setStyleSheet(
            f"QFrame#AppCard {{background:{COLORS.surface}; border:1px solid {COLORS.border}; border-radius:{RADIUS.lg}px;}}"
            f"QFrame#AppCard:hover {{border:1px solid {COLORS.border_strong};}}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
        layout.setSpacing(SPACING.sm)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        if title:
            label = QLabel(title)
            label.setStyleSheet(f"font-size:15px; font-weight:650; color:{COLORS.text_primary};")
            layout.addWidget(label)


class ElevatedCard(AppCard):
    def __init__(self, title: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        self.setStyleSheet(
            f"QFrame#AppCard {{background:{COLORS.surface_elevated}; border:1px solid {COLORS.border_strong}; border-radius:{RADIUS.lg}px;}}"
        )


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setStyleSheet(f"font-size:{TYPE.title}px; font-weight:700;")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setStyleSheet(f"font-size: 13px; color: {COLORS.text_secondary};")
        subtitle_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)


class PanelHeader(QWidget):
    def __init__(self, title: str, subtitle: str | None = None, right_widget: QWidget | None = None) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        left = QVBoxLayout()
        label = QLabel(title)
        label.setWordWrap(True)
        label.setStyleSheet("font-size:16px; font-weight:700;")
        left.addWidget(label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setWordWrap(True)
            sub.setStyleSheet(f"font-size:12px; color:{COLORS.text_secondary};")
            left.addWidget(sub)
        layout.addLayout(left, 1)
        if right_widget:
            layout.addWidget(right_widget)


class _BaseButton(QPushButton):
    def __init__(self, text: str, bg: str, hover: str, border: str, fg: str = COLORS.text_primary) -> None:
        super().__init__(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(text)
        self.setMinimumHeight(CONTROL_HEIGHT)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: {bg};
                border: 1px solid {border};
                border-radius: {RADIUS.sm}px;
                color: {fg};
                font-weight: 600;
                padding: 9px 14px;
            }}
            QPushButton:hover {{ background: {hover}; border: 1px solid {COLORS.border_strong}; }}
            QPushButton:focus {{ border: 2px solid {COLORS.primary}; }}
            QPushButton:disabled {{ background:{COLORS.surface_alt}; color:{COLORS.text_muted}; border:1px solid {COLORS.border}; }}
            QPushButton:pressed {{ background: {hover}; }}
            """
        )


class PrimaryButton(_BaseButton):
    def __init__(self, text: str) -> None:
        super().__init__(text, COLORS.primary, COLORS.primary_hover, COLORS.primary, COLORS.on_primary)


class SecondaryButton(_BaseButton):
    def __init__(self, text: str) -> None:
        super().__init__(text, COLORS.surface_alt, COLORS.surface_elevated, COLORS.border)


class GhostButton(_BaseButton):
    def __init__(self, text: str) -> None:
        super().__init__(text, "transparent", COLORS.surface_alt, COLORS.border)


class DangerButton(_BaseButton):
    def __init__(self, text: str) -> None:
        super().__init__("⚠ " + text, translucent(COLORS.danger, 30), translucent(COLORS.danger, 55), COLORS.danger, COLORS.danger)


class IconButton(QToolButton):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.setText(text)
        self.setAccessibleName(text)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(CONTROL_HEIGHT)
        self.setStyleSheet(
            f"QToolButton {{background:{COLORS.surface_alt}; border:1px solid {COLORS.border}; border-radius:{RADIUS.md}px; padding:8px 12px; font-weight:600; color:{COLORS.text_secondary};}}"
            f"QToolButton:hover {{background:{COLORS.surface_elevated}; border:1px solid {COLORS.border_strong};}}"
            f"QToolButton:focus {{border:1px solid {COLORS.primary}; color:{COLORS.text_primary};}}"
        )


class SidebarButton(QPushButton):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(CONTROL_HEIGHT)
        self.setMaximumHeight(44)
        self.setStyleSheet(
            f"""
            QPushButton {{
                text-align:left;
                background:transparent;
                border:1px solid transparent;
                border-radius:{RADIUS.md}px;
                padding:11px 14px;
                color:{COLORS.text_secondary};
                font-weight:500;
            }}
            QPushButton:hover {{background:{COLORS.surface_alt}; color:{COLORS.text_primary}; border:1px solid {COLORS.border};}}
            QPushButton:checked {{
                background:{COLORS.surface_elevated};
                border:1px solid {COLORS.border_strong};
                border-left:3px solid {COLORS.brand_red};
                color:{COLORS.text_primary};
                padding-left:12px;
            }}
            QPushButton:focus {{border:1px solid {COLORS.primary};}}
            QPushButton[compact="true"] {{padding:0; text-align:center;}}
            """
        )


class SearchInput(QLineEdit):
    def __init__(self, placeholder: str = "Pesquisar...") -> None:
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setAccessibleName(placeholder)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(120)
        self.setMinimumHeight(CONTROL_HEIGHT)
        self.setClearButtonEnabled(True)
        self.setStyleSheet(
            "QLineEdit {padding-left:14px; font-size:13px;}"
        )


class FilterChip(QPushButton):
    def __init__(self, text: str, active: bool = False) -> None:
        super().__init__(text)
        self.setCheckable(True)
        self.setChecked(active)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(36)
        self.setStyleSheet(
            f"""
            QPushButton {{background:{COLORS.surface}; border:1px solid {COLORS.border}; border-radius:{RADIUS.sm}px; padding:6px 12px;}}
            QPushButton:checked {{background:{COLORS.surface_alt}; border:1px solid {COLORS.primary};}}
            QPushButton:hover {{background:{COLORS.surface_alt};}}
            QPushButton:focus {{border:1px solid {COLORS.primary};}}
            """
        )


class SegmentedControl(QWidget):
    selection_changed = Signal(str)

    def __init__(self, options: list[str]) -> None:
        super().__init__()
        self._options = options
        self._buttons: list[FilterChip] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING.xs)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for idx, label in enumerate(options):
            button = FilterChip(label, active=idx == 0)
            self.group.addButton(button, idx)
            button.clicked.connect(lambda _checked, value=label: self.selection_changed.emit(value))
            self._buttons.append(button)
            layout.addWidget(button)
        layout.addStretch(1)

    def value(self) -> str:
        checked_id = self.group.checkedId()
        if checked_id < 0 or checked_id >= len(self._options):
            return self._options[0] if self._options else ""
        return self._options[checked_id]

    def set_value(self, value: str) -> None:
        for idx, option in enumerate(self._options):
            if option == value and idx < len(self._buttons):
                self._buttons[idx].setChecked(True)
                break


class FilterBar(QWidget):
    def __init__(self, chips: Iterable[str]) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING.xs)
        for index, chip in enumerate(chips):
            layout.addWidget(FilterChip(chip, active=index == 0))
        layout.addStretch(1)


class StatusBadge(QLabel):
    COLORS_BY_STATUS = {
        "ok": COLORS.success,
        "warning": COLORS.warning,
        "danger": COLORS.danger,
        "info": COLORS.info,
        "queued": COLORS.accent_violet,
    }

    def __init__(self, text: str, tone: str = "info") -> None:
        super().__init__(text)
        color = self.COLORS_BY_STATUS.get(tone, COLORS.info)
        self.setStyleSheet(
            f"background:{translucent(color)}; color:{color}; border:1px solid {translucent(color, 85)}; border-radius:{RADIUS.sm}px; padding:3px 8px; font-weight:600;"
        )
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)


class StatPill(StatusBadge):
    pass
