"""Dark-mode QSS stylesheet for KarstLab."""

from __future__ import annotations


def _stylesheet() -> str:
    return """
    QMainWindow, QWidget {
        background: #1a1f2e; color: #e8eaf0;
        font-family: Arial; font-size: 13px;
    }
    QTabWidget::pane, QGroupBox, QFrame#placeholder {
        border: 1px solid #3a4058; border-radius: 6px;
    }
    QFrame#guidedBar {
        background: #1f2433; border-top: 1px solid #3a4058;
    }
    QTabBar::tab { background: #242938; color: #9ca3b8; padding: 8px 10px; }
    QTabBar::tab:hover { background: #2d3348; color: #e8eaf0; }
    QTabBar::tab:selected {
        background: #2d3348; color: #e8eaf0; border-bottom: 2px solid #c75d4a;
    }
    QGroupBox::title { color: #e8eaf0; font-weight: 600; padding: 0 4px; }
    QLineEdit, QComboBox, QTextBrowser, QTableWidget, QListWidget {
        background: #242938; border: 1px solid #3a4058; border-radius: 6px; color: #e8eaf0;
    }
    QLineEdit:focus, QComboBox:focus, QTableWidget:focus, QListWidget:focus {
        border: 2px solid #4a90d9;
    }
    QComboBox QAbstractItemView {
        background: #242938; color: #e8eaf0; border: 1px solid #3a4058;
        selection-background-color: #2d3348;
    }
    QComboBox::drop-down { border: 0; width: 24px; }
    QComboBox::down-arrow { width: 0; height: 0; }
    QPushButton {
        background: #242938; border: 1px solid #3a4058;
        border-radius: 6px; padding: 7px 10px;
    }
    QPushButton:hover { background: #2d3348; }
    QPushButton#primaryButton {
        background: #c75d4a; border-color: #c75d4a; color: white; font-weight: 600;
    }
    QPushButton#primaryButton:hover { background: #b5503f; border-color: #b5503f; }
    QPushButton:disabled { color: #5a6178; background: #1f2433; }
    QCheckBox { spacing: 8px; }
    QCheckBox::indicator {
        width: 16px; height: 16px; border: 1px solid #3a4058;
        border-radius: 3px; background: #242938;
    }
    QCheckBox::indicator:checked { background: #c75d4a; border-color: #c75d4a; }
    QSlider::groove:horizontal {
        background: #3a4058; height: 4px; border-radius: 2px;
    }
    QSlider::sub-page:horizontal { background: #c75d4a; border-radius: 2px; }
    QSlider::handle:horizontal {
        background: #e8eaf0; width: 12px; margin: -4px 0; border-radius: 6px;
    }
    QSlider::handle:horizontal:hover { background: #f0c040; }
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
    QSplitter::handle { background: #3a4058; }
    QStatusBar {
        background: #242938; color: #9ca3b8; border-top: 1px solid #3a4058; font-size: 11px;
    }
    QProgressBar {
        background: #242938; border: 1px solid #3a4058;
        border-radius: 4px; min-height: 8px;
    }
    QProgressBar::chunk { background: #c75d4a; border-radius: 4px; }
    QLabel#secondaryText { color: #9ca3b8; }
    QHeaderView::section { background: #242938; color: #e8eaf0; border: 0; padding: 6px; }
    """


__all__ = ["_stylesheet"]
