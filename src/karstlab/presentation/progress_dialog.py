"""Non-modal dialog for displaying DAG pipeline progress."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from karstlab.data.schemas import PipelineStatus

_ICON_MAP = {
    PipelineStatus.PENDING: "○",
    PipelineStatus.RUNNING: "⟳",
    PipelineStatus.SUCCESS: "✓",
    PipelineStatus.COMPLETED: "✓",
    PipelineStatus.FAILED: "✗",
    PipelineStatus.SKIPPED: "—",
}

_DARK_STYLESHEET = """
    QDialog {
        background-color: #1a1f2e;
        color: #e8eaf0;
    }
    QLabel {
        color: #e8eaf0;
    }
    QListWidget {
        background-color: #242938;
        color: #e8eaf0;
        border: 1px solid #3a4058;
        border-radius: 4px;
    }
    QListWidget::item {
        padding: 4px;
    }
    QProgressBar {
        background-color: #242938;
        border: 1px solid #3a4058;
        border-radius: 4px;
        text-align: center;
        color: #e8eaf0;
    }
    QProgressBar::chunk {
        background-color: #c75d4a;
        border-radius: 2px;
    }
    QTextBrowser {
        background-color: #242938;
        color: #e8eaf0;
        border: 1px solid #3a4058;
        border-radius: 4px;
    }
    QPushButton {
        background-color: #c75d4a;
        color: #e8eaf0;
        border: none;
        border-radius: 4px;
        padding: 6px 12px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #d97460;
    }
    QPushButton:pressed {
        background-color: #b04a3a;
    }
    QPushButton:disabled {
        background-color: #3a4058;
        color: #5a6580;
    }
"""


class ProgressDialog(QDialog):
    """Non-modal dialog showing DAG pipeline execution progress."""

    rerun_failed_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Analysis Progress"))
        self.setModal(False)
        self.setStyleSheet(_DARK_STYLESHEET)
        self.resize(500, 400)

        self._steps: dict[str, QListWidgetItem] = {}

        layout = QVBoxLayout()

        header_label = QLabel(self.tr("Pipeline Steps"))
        header_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(header_label)

        self._list_widget = QListWidget()
        layout.addWidget(self._list_widget)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #9ca3b8;")
        layout.addWidget(self._status_label)

        self._error_browser = QTextBrowser()
        self._error_browser.hide()
        layout.addWidget(self._error_browser)

        button_layout = QHBoxLayout()
        self._rerun_button = QPushButton(self.tr("Rerun failed steps"))
        self._rerun_button.setEnabled(False)
        self._rerun_button.clicked.connect(self.rerun_failed_requested.emit)
        button_layout.addWidget(self._rerun_button)

        close_button = QPushButton(self.tr("Close"))
        close_button.clicked.connect(self.close)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def add_step(self, step_id: str, label: str) -> None:
        """Add a step to the progress list in PENDING state."""
        item_text = f"{_ICON_MAP[PipelineStatus.PENDING]} {label}"
        item = QListWidgetItem(item_text)
        self._list_widget.addItem(item)
        self._steps[step_id] = item

    def update_step(self, step_id: str, status: PipelineStatus, message: str = "") -> None:
        """Update the status and optional message for a step."""
        if step_id not in self._steps:
            return

        item = self._steps[step_id]
        current_text = item.text()
        label = current_text[2:].strip()

        icon = _ICON_MAP.get(status, "?")
        new_text = f"{icon} {label}"
        if message:
            new_text += f" — {message}"

        item.setText(new_text)

    def set_progress(self, value: int) -> None:
        """Update the overall progress bar (0-100)."""
        self._progress_bar.setValue(value)

    def set_status_message(self, message: str) -> None:
        """Update the status message label."""
        self._status_label.setText(message)

    def show_error(self, error_text: str) -> None:
        """Display error details and enable the rerun button."""
        self._error_browser.setPlainText(error_text)
        self._error_browser.show()
        self._rerun_button.setEnabled(True)

    def reset(self) -> None:
        """Clear all steps, reset progress, and hide error details."""
        self._list_widget.clear()
        self._steps.clear()
        self._progress_bar.setValue(0)
        self._status_label.setText("")
        self._error_browser.setPlainText("")
        self._error_browser.hide()
        self._rerun_button.setEnabled(False)


__all__ = ["ProgressDialog"]
