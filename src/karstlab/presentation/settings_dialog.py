"""Settings dialog for user preferences."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from karstlab.data.land_profiles import list_land_profile_ids
from karstlab.data.schemas import Locale, UserSettings


class SettingsDialog(QDialog):
    """Dialog for editing user settings."""

    settings_saved = Signal(object)

    def __init__(self, settings: UserSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Settings"))
        self.setModal(True)
        self.setMinimumWidth(500)
        self._settings = settings
        self._original_language = settings.language
        self._whitebox_path_value: Path | None = settings.whitebox_path

        self._language_combo = QComboBox()
        self._language_combo.addItems([
            self.tr("English (en)"), self.tr("Nederlands (nl)"), self.tr("Français (fr)"),
        ])
        self._set_combo_index_by_locale(self._language_combo, settings.language)

        self._land_profile_combo = QComboBox()
        self._land_profile_combo.addItems(list_land_profile_ids())
        current_index = self._land_profile_combo.findText(settings.land_profile)
        if current_index >= 0:
            self._land_profile_combo.setCurrentIndex(current_index)

        self._update_check_box = QCheckBox()
        self._update_check_box.setChecked(settings.update_check)

        self._whitebox_path_input = QLineEdit()
        self._whitebox_path_input.setPlaceholderText(self.tr("Leave blank to use bundled binary"))
        if settings.whitebox_path:
            self._whitebox_path_input.setText(str(settings.whitebox_path))
        self._whitebox_path_input.setReadOnly(True)

        self._whitebox_browse_button = QPushButton(self.tr("Browse…"))
        self._whitebox_browse_button.clicked.connect(self._on_browse_whitebox)

        whitebox_layout = QHBoxLayout()
        whitebox_layout.addWidget(self._whitebox_path_input)
        whitebox_layout.addWidget(self._whitebox_browse_button)

        form_layout = QFormLayout()
        form_layout.addRow(self.tr("Language:"), self._language_combo)
        form_layout.addRow(self.tr("Land profile:"), self._land_profile_combo)
        form_layout.addRow(self.tr("Check for updates:"), self._update_check_box)
        form_layout.addRow(self.tr("WhiteboxTools path:"), whitebox_layout)

        button_layout = QHBoxLayout()
        self._ok_button = QPushButton(self.tr("OK"))
        self._ok_button.setObjectName("primaryButton")
        self._ok_button.clicked.connect(self._on_ok)

        self._cancel_button = QPushButton(self.tr("Cancel"))
        self._cancel_button.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self._ok_button)
        button_layout.addWidget(self._cancel_button)

        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addStretch()
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)
        self.setStyleSheet(self._stylesheet())

    def _set_combo_index_by_locale(self, combo: QComboBox, locale: Locale) -> None:
        """Set combo box index based on Locale enum."""
        locale_map = {
            Locale.EN: 0,
            Locale.NL: 1,
            Locale.FR: 2,
        }
        combo.setCurrentIndex(locale_map.get(locale, 0))

    def _get_locale_from_index(self, index: int) -> Locale:
        """Get Locale enum from combo box index."""
        locales = [Locale.EN, Locale.NL, Locale.FR]
        return locales[max(0, min(index, len(locales) - 1))]

    def _on_browse_whitebox(self) -> None:
        """Handle WhiteboxTools directory browse."""
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            self.tr("Select WhiteboxTools Directory"),
            str(self._whitebox_path_value) if self._whitebox_path_value else "",
        )
        if selected_dir:
            self._whitebox_path_value = Path(selected_dir)
            self._whitebox_path_input.setText(str(self._whitebox_path_value))

    def _on_ok(self) -> None:
        """Save settings and emit signal."""
        language = self._get_locale_from_index(self._language_combo.currentIndex())
        land_profile = self._land_profile_combo.currentText()
        update_check = self._update_check_box.isChecked()

        updated_settings = UserSettings(
            schema_version=self._settings.schema_version,
            language=language,
            land_profile=land_profile,
            recent_projects=self._settings.recent_projects,
            update_check=update_check,
            whitebox_path=self._whitebox_path_value,
            crs_override=self._settings.crs_override,
            large_dem_threshold_mb=self._settings.large_dem_threshold_mb,
            last_project_dir=self._settings.last_project_dir,
            analysis_params=self._settings.analysis_params,
        )

        self.settings_saved.emit(updated_settings)

        if language != self._original_language:
            QMessageBox.information(
                self,
                self.tr("Restart required"),
                self.tr("Language change takes effect after restarting KarstLab."),
            )

        self.accept()

    def whitebox_path_value(self) -> Path | None:
        """Get the WhiteboxTools path value."""
        return self._whitebox_path_value

    @staticmethod
    def _stylesheet() -> str:
        """Dark theme stylesheet for this dialog."""
        return """
        QDialog, QWidget {
            background: #1a1f2e; color: #e8eaf0;
            font-family: Arial; font-size: 13px;
        }
        QLineEdit, QComboBox {
            background: #242938; border: 1px solid #3a4058; border-radius: 6px; color: #e8eaf0;
            padding: 4px;
        }
        QLineEdit:focus, QComboBox:focus {
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
        QCheckBox { spacing: 8px; color: #e8eaf0; }
        QCheckBox::indicator {
            width: 16px; height: 16px; border: 1px solid #3a4058;
            border-radius: 3px; background: #242938;
        }
        QCheckBox::indicator:checked { background: #c75d4a; border-color: #c75d4a; }
        QLabel { color: #e8eaf0; }
        """


__all__ = ["SettingsDialog"]
