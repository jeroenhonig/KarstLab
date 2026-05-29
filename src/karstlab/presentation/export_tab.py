"""Export controls tab widget for KarstLab."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ExportTab(QWidget):
    """Export controls tab for opening and generating analysis exports."""

    open_export_requested = Signal(str)
    generate_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._export_paths: dict[str, Path] = {}
        self._export_buttons: dict[str, QPushButton] = {}
        self._project_name: str | None = None
        self._generate_section: QWidget | None = None
        self._generate_label: QLabel | None = None
        self._generate_button: QPushButton | None = None
        self._build_layout()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        open_group = QGroupBox(self.tr("Open exported files"))
        open_layout = QVBoxLayout(open_group)
        for key in (
            self.tr("Open report"),
            self.tr("Open GeoJSON"),
            self.tr("Open KML"),
            self.tr("Open GPX"),
            self.tr("Open statistics JSON"),
            self.tr("Open map"),
        ):
            button = QPushButton(key)
            button.setEnabled(False)
            button.clicked.connect(lambda _checked=False, k=key: self._on_open_clicked(k))
            self._export_buttons[key] = button
            open_layout.addWidget(button)
        layout.addWidget(open_group)

        self._generate_section = QWidget()
        gen_layout = QVBoxLayout(self._generate_section)
        self._generate_label = QLabel(self.tr("Run analysis first to generate exports."))
        self._generate_label.setObjectName("secondaryText")
        gen_layout.addWidget(self._generate_label)
        self._generate_button = QPushButton(self.tr("Generate all"))
        self._generate_button.setVisible(False)
        self._generate_button.clicked.connect(self._on_generate_clicked)
        gen_layout.addWidget(self._generate_button)
        gen_layout.addStretch(1)
        layout.addWidget(self._generate_section)

        layout.addStretch(1)

    def set_export_paths(self, paths: dict[str, Path]) -> None:
        """Enable export buttons for available paths."""
        self._export_paths = dict(paths)
        for key, button in self._export_buttons.items():
            path = self._export_paths.get(key)
            button.setEnabled(path is not None and path.exists())
            button.setToolTip(str(path) if path is not None else "")

    def set_project(self, project_name: str | None) -> None:
        """Show/hide generate section and update label."""
        self._project_name = project_name
        if self._generate_label is not None and self._generate_button is not None:
            if project_name:
                self._generate_label.setText(self.tr("Project: {0}").format(project_name))
                self._generate_button.setVisible(True)
            else:
                self._generate_label.setText(self.tr("Run analysis first to generate exports."))
                self._generate_button.setVisible(False)

    def export_buttons(self) -> list[QPushButton]:
        """Return export buttons for backward compatibility."""
        return list(self._export_buttons.values())

    def _on_open_clicked(self, key: str) -> None:
        path = self._export_paths.get(key)
        if path is None or not path.exists():
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.open_export_requested.emit(key)

    def _on_generate_clicked(self) -> None:
        self.generate_requested.emit()


__all__ = ["ExportTab"]
