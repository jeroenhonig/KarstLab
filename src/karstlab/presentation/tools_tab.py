"""Tools tab for analysis configuration and DEM selection."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from karstlab.data.land_profiles import list_land_profile_ids
from karstlab.data.schemas import AnalysisParams


class ToolsTab(QWidget):
    """Tab for analysis tools, DEM selection, and parameter configuration."""

    analyze_requested = Signal()
    cancel_requested = Signal()
    dem_path_changed = Signal(Path)
    tile_paths_changed = Signal(object)  # list[Path]
    project_dir_changed = Signal(Path)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dem_path: Path | None = None
        self._tile_paths: list[Path] = []
        self._project_dir: Path | None = None

        self._dem_edit = QLineEdit()
        self._dem_edit.setReadOnly(True)
        self._dem_browse_button = QPushButton(self.tr("Browse…"))
        self._dem_browse_button.clicked.connect(self._browse_dem)
        self._dem_tiles_button = QPushButton(self.tr("Tiles…"))
        self._dem_tiles_button.clicked.connect(self._pick_tiles)

        self._project_edit = QLineEdit()
        self._project_browse_button = QPushButton(self.tr("Browse…"))
        self._project_browse_button.clicked.connect(self._browse_project)

        self._profile_combo = QComboBox()
        self._profile_combo.addItems(list_land_profile_ids())

        form_layout = QFormLayout()
        dem_row = QHBoxLayout()
        dem_row.addWidget(self._dem_edit)
        dem_row.addWidget(self._dem_browse_button)
        dem_row.addWidget(self._dem_tiles_button)
        dem_wrapper = QWidget()
        dem_wrapper.setLayout(dem_row)
        form_layout.addRow(self.tr("DEM"), dem_wrapper)

        project_row = QHBoxLayout()
        project_row.addWidget(self._project_edit)
        project_row.addWidget(self._project_browse_button)
        project_wrapper = QWidget()
        project_wrapper.setLayout(project_row)
        form_layout.addRow(self.tr("Project folder"), project_wrapper)

        form_layout.addRow(self.tr("Land profile"), self._profile_combo)

        params_group = self._create_parameters_group()

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)

        self._analyze_button = QPushButton(self.tr("Analyze"))
        self._analyze_button.setObjectName("primaryButton")
        self._analyze_button.clicked.connect(self.analyze_requested.emit)

        self._cancel_button = QPushButton(self.tr("Cancel"))
        self._cancel_button.setEnabled(False)
        self._cancel_button.clicked.connect(self.cancel_requested.emit)

        self._status_label = QLabel(self.tr("Ready"))
        self._status_label.setObjectName("secondaryText")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addLayout(form_layout)
        layout.addWidget(params_group)
        layout.addWidget(self._progress_bar)
        layout.addWidget(self._analyze_button)
        layout.addWidget(self._cancel_button)
        layout.addWidget(self._status_label)
        layout.addStretch(1)

    def _create_parameters_group(self) -> QGroupBox:
        """Create the analysis parameters group box."""
        group = QGroupBox(self.tr("Analysis parameters"))
        grid_layout = QFormLayout(group)

        self._contour_spin = QDoubleSpinBox()
        self._contour_spin.setRange(0.1, 100.0)
        self._contour_spin.setSingleStep(0.5)
        self._contour_spin.setValue(5.0)
        grid_layout.addRow(self.tr("Contour interval (m)"), self._contour_spin)

        self._min_depth_spin = QDoubleSpinBox()
        self._min_depth_spin.setRange(0.0, 100.0)
        self._min_depth_spin.setSingleStep(0.1)
        self._min_depth_spin.setValue(0.25)
        grid_layout.addRow(self.tr("Min depth (m)"), self._min_depth_spin)

        self._max_depth_spin = QDoubleSpinBox()
        self._max_depth_spin.setRange(0.1, 500.0)
        self._max_depth_spin.setSingleStep(1.0)
        self._max_depth_spin.setValue(40.0)
        grid_layout.addRow(self.tr("Max depth (m)"), self._max_depth_spin)

        self._min_area_spin = QDoubleSpinBox()
        self._min_area_spin.setRange(0.0, 100000.0)
        self._min_area_spin.setSingleStep(10.0)
        self._min_area_spin.setValue(1.0)
        grid_layout.addRow(self.tr("Min area (m²)"), self._min_area_spin)

        self._max_area_spin = QDoubleSpinBox()
        self._max_area_spin.setRange(1.0, 1000000.0)
        self._max_area_spin.setSingleStep(100.0)
        self._max_area_spin.setValue(60000.0)
        grid_layout.addRow(self.tr("Max area (m²)"), self._max_area_spin)

        self._stream_threshold_spin = QSpinBox()
        self._stream_threshold_spin.setRange(100, 100000)
        self._stream_threshold_spin.setSingleStep(100)
        self._stream_threshold_spin.setValue(1000)
        grid_layout.addRow(self.tr("Stream threshold (cells)"), self._stream_threshold_spin)

        return group

    def _browse_dem(self) -> None:
        """Browse for DEM file."""
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            self.tr("Select DEM"),
            str(Path.home()),
            self.tr("GeoTIFF (*.tif *.tiff);;All files (*)"),
        )
        if path:
            self._tile_paths = []
            self.set_dem_path(Path(path))

    def _pick_tiles(self) -> None:
        """Open tile picker dialog to select ASC tiles from a directory."""
        from karstlab.presentation.tile_picker_dialog import TilePickerDialog

        initial = (
            self._tile_paths[0].parent
            if self._tile_paths
            else (self._dem_path.parent if self._dem_path else None)
        )
        dlg = TilePickerDialog(initial_dir=initial, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        paths = dlg.selected_paths()
        if not paths:
            QMessageBox.warning(
                self,
                self.tr("No tiles selected"),
                self.tr("Select at least one tile."),
            )
            return
        self.set_tile_paths(paths)

    def _browse_project(self) -> None:
        """Browse for project directory."""
        path = QFileDialog.getExistingDirectory(
            self,
            self.tr("Select project folder"),
            self._project_edit.text() or str(Path.home()),
        )
        if path:
            self.set_project_dir(Path(path))

    def set_dem_path(self, path: Path) -> None:
        """Set the DEM path and update display."""
        self._dem_path = path
        self._tile_paths = []
        self._dem_edit.setText(str(path))
        self.dem_path_changed.emit(path)

    def dem_path(self) -> Path | None:
        """Return the currently set DEM path, or None when tiles are active."""
        return None if self._tile_paths else self._dem_path

    def set_tile_paths(self, paths: list[Path]) -> None:
        """Set multiple ASC tile paths and update display."""
        self._tile_paths = list(paths)
        self._dem_path = None
        if paths:
            self._dem_edit.setText(
                self.tr("[{0} tiles] {1}").format(len(paths), paths[0].parent)
            )
        else:
            self._dem_edit.clear()
        self.tile_paths_changed.emit(self._tile_paths)

    def tile_paths(self) -> list[Path]:
        """Return the list of selected tile paths (empty when single DEM is used)."""
        return list(self._tile_paths)

    def set_project_dir(self, path: Path) -> None:
        """Set the project directory and update display."""
        self._project_dir = path
        self._project_edit.setText(str(path))
        self.project_dir_changed.emit(path)

    def project_dir(self) -> Path:
        """Return the project directory."""
        return Path(self._project_edit.text()) if self._project_edit.text() else Path.home()

    def set_profile(self, profile_id: str) -> None:
        """Set the current land profile by ID."""
        index = self._profile_combo.findText(profile_id)
        if index >= 0:
            self._profile_combo.setCurrentIndex(index)

    def profile_id(self) -> str:
        """Return the currently selected land profile ID."""
        return self._profile_combo.currentText()

    def analysis_params(self) -> AnalysisParams:
        """Read and return analysis parameters from spinboxes."""
        return AnalysisParams(
            contour_interval_m=self._contour_spin.value(),
            stream_threshold_cells=self._stream_threshold_spin.value(),
            doline_min_depth_m=self._min_depth_spin.value(),
            doline_max_depth_m=self._max_depth_spin.value(),
            doline_min_area_m2=self._min_area_spin.value(),
            doline_max_area_m2=self._max_area_spin.value(),
        )

    def set_analysis_params(self, params: AnalysisParams) -> None:
        """Set analysis parameter spinbox values from AnalysisParams."""
        self._contour_spin.setValue(params.contour_interval_m)
        self._stream_threshold_spin.setValue(params.stream_threshold_cells)
        self._min_depth_spin.setValue(params.doline_min_depth_m)
        self._max_depth_spin.setValue(params.doline_max_depth_m)
        self._min_area_spin.setValue(params.doline_min_area_m2)
        self._max_area_spin.setValue(params.doline_max_area_m2)

    def set_progress(self, value: int) -> None:
        """Set the progress bar value (0-100)."""
        self._progress_bar.setValue(value)

    def set_status(self, text: str) -> None:
        """Set the status label text."""
        self._status_label.setText(text)

    def set_analyze_enabled(self, enabled: bool) -> None:
        """Enable or disable the analyze button."""
        self._analyze_button.setEnabled(enabled)

    def set_cancel_enabled(self, enabled: bool) -> None:
        """Enable or disable the cancel button."""
        self._cancel_button.setEnabled(enabled)


__all__ = ["ToolsTab"]
