"""Dismissible update notification banner."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

_DARK_STYLESHEET = """
    QFrame {
        background-color: #1f3050;
        border: 1px solid #4a90d9;
        border-radius: 4px;
    }
    QLabel {
        color: #e8eaf0;
    }
    QPushButton {
        background-color: transparent;
        color: #4a90d9;
        border: none;
        text-decoration: underline;
        padding: 0px;
        margin: 0px;
    }
    QPushButton:hover {
        color: #5ba3e6;
    }
    QPushButton:pressed {
        color: #3a7ac9;
    }
    #dismiss-button {
        background-color: transparent;
        color: #9ca3b8;
        border: none;
        padding: 0px;
        margin: 0px;
        font-size: 14pt;
    }
    #dismiss-button:hover {
        color: #e8eaf0;
    }
"""


class UpdateBanner(QFrame):
    """Dismissible update notification banner."""

    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_DARK_STYLESHEET)
        self.hide()

        self._download_url = ""

        layout = QHBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)

        info_icon = QLabel("ℹ")
        info_icon.setStyleSheet("color: #4a90d9; font-size: 12pt; margin-right: 8px;")
        layout.addWidget(info_icon)

        self._message_label = QLabel()
        layout.addWidget(self._message_label)

        layout.addStretch()

        self._download_button = QPushButton(self.tr("Download"))
        self._download_button.clicked.connect(self._on_download_clicked)
        layout.addWidget(self._download_button)

        dismiss_button = QPushButton("×")
        dismiss_button.setObjectName("dismiss-button")
        dismiss_button.setFixedWidth(24)
        dismiss_button.clicked.connect(self._on_dismiss_clicked)
        layout.addWidget(dismiss_button)

        self.setLayout(layout)

    def show_update(self, version: str, download_url: str = "") -> None:
        """Show the banner with the given version and optional download URL."""
        self._message_label.setText(self.tr("KarstLab {0} is available.").format(version))
        self._download_url = download_url
        self.show()

    def _on_download_clicked(self) -> None:
        """Open the download URL in the default browser."""
        if self._download_url:
            QDesktopServices.openUrl(QUrl(self._download_url))

    def _on_dismiss_clicked(self) -> None:
        """Hide the banner and emit dismissed signal."""
        self.hide()
        self.dismissed.emit()


__all__ = ["UpdateBanner"]
