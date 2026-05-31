"""Keyboard shortcuts reference dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ShortcutsDialog(QDialog):
    """Dialog displaying keyboard shortcuts reference."""

    def _get_shortcuts(self) -> list[tuple[str, str]]:
        """Return the list of shortcuts with translations."""
        return [
            ("Ctrl+N", self.tr("New project")),
            ("Ctrl+O", self.tr("Open project")),
            ("Ctrl+S", self.tr("Save project")),
            ("Ctrl+?", self.tr("Show keyboard shortcuts")),
            ("Ctrl+,", self.tr("Open settings")),
            ("F5 / Ctrl+R", self.tr("Run analysis")),
            ("Escape", self.tr("Cancel analysis")),
            ("Ctrl+1", self.tr("Switch to Tools tab")),
            ("Ctrl+2", self.tr("Switch to Results tab")),
            ("Ctrl+3", self.tr("Switch to Layers tab")),
            ("Ctrl+4", self.tr("Switch to Markers tab")),
            ("Ctrl+5", self.tr("Switch to Export tab")),
        ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Keyboard Shortcuts"))
        self.setMinimumWidth(450)
        self.setMinimumHeight(400)
        self.setModal(True)

        shortcuts = self._get_shortcuts()
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels([self.tr("Shortcut"), self.tr("Action")])
        table.setRowCount(len(shortcuts))
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for row, (shortcut, action) in enumerate(shortcuts):
            shortcut_item = QTableWidgetItem(shortcut)
            shortcut_item.setFlags(shortcut_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            action_item = QTableWidgetItem(action)
            action_item.setFlags(action_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)

            table.setItem(row, 0, shortcut_item)
            table.setItem(row, 1, action_item)

        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        close_button = QPushButton(self.tr("Close"))
        close_button.setObjectName("primaryButton")
        close_button.clicked.connect(self.accept)
        close_button.setMaximumWidth(100)

        layout = QVBoxLayout()
        layout.addWidget(table)
        layout.addWidget(close_button)

        self.setLayout(layout)
        self.setStyleSheet(self._stylesheet())

    @staticmethod
    def _stylesheet() -> str:
        """Dark theme stylesheet for this dialog."""
        return """
        QDialog, QWidget {
            background: #1a1f2e; color: #e8eaf0;
            font-family: Arial; font-size: 13px;
        }
        QTableWidget {
            background: #242938; border: 1px solid #3a4058; border-radius: 6px;
            gridline-color: #3a4058;
        }
        QTableWidget::item {
            padding: 6px;
            background: #242938;
        }
        QTableWidget::item:selected {
            background: #2d3348;
        }
        QHeaderView::section {
            background: #242938; color: #e8eaf0; border: 0; padding: 6px;
            font-weight: 600;
            border-right: 1px solid #3a4058;
        }
        QPushButton {
            background: #242938; border: 1px solid #3a4058;
            border-radius: 6px; padding: 7px 10px;
        }
        QPushButton:hover { background: #2d3348; }
        QPushButton#primaryButton {
            background: #c75d4a; border-color: #c75d4a; color: white; font-weight: 600;
        }
        QPushButton#primaryButton:hover { background: #b5503f; border-color: #b5503f; }
        QScrollBar:vertical { background: #1a1f2e; width: 10px; margin: 0; }
        QScrollBar::handle:vertical {
            background: #3a4058; border-radius: 5px; min-height: 20px;
        }
        QScrollBar::handle:vertical:hover { background: #4a5068; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar:horizontal { background: #1a1f2e; height: 10px; margin: 0; }
        QScrollBar::handle:horizontal {
            background: #3a4058; border-radius: 5px; min-width: 20px;
        }
        QScrollBar::handle:horizontal:hover { background: #4a5068; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
        """


__all__ = ["ShortcutsDialog"]
