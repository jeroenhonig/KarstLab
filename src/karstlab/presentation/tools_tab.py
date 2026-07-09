"""Tools tab for analysis configuration and DEM selection."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from karstlab.data.land_profiles import list_land_profile_ids
from karstlab.data.schemas import AnalysisParams
from karstlab.presentation.analysis_progress import AnalysisProgressPanel


def _file_picker_field(edit: QLineEdit, *buttons: QPushButton) -> QWidget:
    """Stack a path line-edit over a left-aligned row of its buttons.

    Vertical stacking keeps the buttons' labels from being clipped on the narrow
    side panel, where edit + buttons would not fit on one line beside the label.
    """
    container = QVBoxLayout()
    container.setContentsMargins(0, 0, 0, 0)
    container.setSpacing(4)
    container.addWidget(edit)
    button_row = QHBoxLayout()
    button_row.setContentsMargins(0, 0, 0, 0)
    for button in buttons:
        button_row.addWidget(button)
    button_row.addStretch(1)
    container.addLayout(button_row)
    wrapper = QWidget()
    wrapper.setLayout(container)
    return wrapper


class ToolsTab(QWidget):
    """Tab for analysis tools, DEM selection, and parameter configuration."""

    analyze_requested = Signal()
    cancel_requested = Signal()
    dem_path_changed = Signal(Path)
    tile_paths_changed = Signal(object)  # list[Path]
    project_dir_changed = Signal(Path)
    distance_mode_toggled = Signal(bool)
    profile_mode_toggled = Signal(bool)

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

        self._fault_path: Path | None = None
        self._fault_edit = QLineEdit()
        self._fault_edit.setReadOnly(True)
        self._fault_edit.setPlaceholderText(self.tr("Optional: BDCharm50 faults (.shp/.zip/dir)"))
        self._fault_browse_button = QPushButton(self.tr("Faults…"))
        self._fault_browse_button.clicked.connect(self._browse_faults)
        self._fault_clear_button = QPushButton(self.tr("Clear"))
        self._fault_clear_button.clicked.connect(self._clear_faults)

        self._caveline_path: Path | None = None
        self._caveline_edit = QLineEdit()
        self._caveline_edit.setReadOnly(True)
        self._caveline_edit.setPlaceholderText(
            self.tr("Optional: known cave survey (.gpx/.kml) → conduit projection")
        )
        self._caveline_browse_button = QPushButton(self.tr("Caveline…"))
        self._caveline_browse_button.clicked.connect(self._browse_caveline)
        self._caveline_clear_button = QPushButton(self.tr("Clear"))
        self._caveline_clear_button.clicked.connect(self._clear_caveline)
        # Which end of the survey the conduit projects FROM (userData = schema value).
        self._caveline_dir_combo = QComboBox()
        self._caveline_dir_combo.addItem(self.tr("Project from survey start"), "first")
        self._caveline_dir_combo.addItem(self.tr("Project from survey end"), "last")
        self._caveline_dir_combo.setToolTip(
            self.tr("Flip which end of the survey the predicted conduit extends from")
        )

        form_layout = QFormLayout()
        # The side panel is narrow. A file row (path edit + 2-3 buttons) cannot fit
        # on one line beside its label without clipping the button labels, so stack
        # the edit over a row of buttons; the field then needs only its own width.
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form_layout.addRow(
            self.tr("DEM"),
            _file_picker_field(self._dem_edit, self._dem_browse_button, self._dem_tiles_button),
        )
        form_layout.addRow(
            self.tr("Project folder"),
            _file_picker_field(self._project_edit, self._project_browse_button),
        )
        form_layout.addRow(self.tr("Land profile"), self._profile_combo)
        form_layout.addRow(
            self.tr("Faults"),
            _file_picker_field(
                self._fault_edit, self._fault_browse_button, self._fault_clear_button
            ),
        )
        form_layout.addRow(
            self.tr("Caveline"),
            _file_picker_field(
                self._caveline_edit, self._caveline_browse_button, self._caveline_clear_button
            ),
        )
        form_layout.addRow(self.tr("Conduit direction"), self._caveline_dir_combo)

        params_group = self._create_parameters_group()

        self._distance_button = QPushButton(self.tr("Measure distance"))
        self._distance_button.setCheckable(True)
        self._distance_button.toggled.connect(self.distance_mode_toggled.emit)
        self._profile_button = QPushButton(self.tr("Elevation profile"))
        self._profile_button.setCheckable(True)
        self._profile_button.toggled.connect(self.profile_mode_toggled.emit)
        map_tools_group = QGroupBox(self.tr("Map tools"))
        map_tools_layout = QVBoxLayout(map_tools_group)
        map_tools_layout.addWidget(self._distance_button)
        map_tools_layout.addWidget(self._profile_button)

        self._progress_panel = AnalysisProgressPanel()
        # Keep the bar/status attributes the rest of the app and the tests read
        # via ToolsTab; the panel owns the richer phase + log presentation.
        self._progress_bar = self._progress_panel.bar
        self._status_label = self._progress_panel.message_label

        self._force_recompute_checkbox = QCheckBox(
            self.tr("Force recompute (ignore cached DEM steps)")
        )
        self._force_recompute_checkbox.setToolTip(
            self.tr(
                "When off, unchanged-DEM intermediates (mosaic, terrain, hydrology "
                "fill) are reused so parameter tweaks finish much faster."
            )
        )

        self._analyze_button = QPushButton(self.tr("Analyze"))
        self._analyze_button.setObjectName("primaryButton")
        self._analyze_button.clicked.connect(self.analyze_requested.emit)

        self._cancel_button = QPushButton(self.tr("Cancel"))
        self._cancel_button.setEnabled(False)
        self._cancel_button.clicked.connect(self.cancel_requested.emit)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addLayout(form_layout)
        layout.addWidget(params_group)
        layout.addWidget(map_tools_group)
        layout.addWidget(self._progress_panel)
        layout.addWidget(self._force_recompute_checkbox)
        layout.addWidget(self._analyze_button)
        layout.addWidget(self._cancel_button)
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

    def _browse_faults(self) -> None:
        """Pick a BDCharm50 fault dataset (shapefile or zipped package)."""
        path, _filter = QFileDialog.getOpenFileName(
            self,
            self.tr("Select fault dataset"),
            str(self._fault_path.parent if self._fault_path else Path.home()),
            self.tr("Faults (*.shp *.zip);;All files (*)"),
        )
        if path:
            self._fault_path = Path(path)
            self._fault_edit.setText(self._fault_path.name)

    def _clear_faults(self) -> None:
        self._fault_path = None
        self._fault_edit.clear()

    def fault_lines_path(self) -> Path | None:
        """Return the selected fault dataset path, or ``None``."""
        return self._fault_path

    def set_fault_lines_path(self, path: Path | None) -> None:
        self._fault_path = path
        self._fault_edit.setText(path.name if path else "")

    def _browse_caveline(self) -> None:
        """Pick a known cave-survey line (GPX/KML) to enable conduit projection."""
        path, _filter = QFileDialog.getOpenFileName(
            self,
            self.tr("Select cave survey line"),
            str(self._caveline_path.parent if self._caveline_path else Path.home()),
            self.tr("Survey lines (*.gpx *.kml);;All files (*)"),
        )
        if path:
            self._caveline_path = Path(path)
            self._caveline_edit.setText(self._caveline_path.name)

    def _clear_caveline(self) -> None:
        self._caveline_path = None
        self._caveline_edit.clear()

    def caveline_path(self) -> Path | None:
        """Return the selected cave-survey line path, or ``None``."""
        return self._caveline_path

    def set_caveline_path(self, path: Path | None) -> None:
        self._caveline_path = path
        self._caveline_edit.setText(path.name if path else "")

    def caveline_downstream_end(self) -> str:
        """Return the selected projection end: "first" (survey start) or "last"."""
        value = self._caveline_dir_combo.currentData()
        return value if value in ("first", "last") else "first"

    def set_caveline_downstream_end(self, end: str) -> None:
        index = self._caveline_dir_combo.findData("last" if end == "last" else "first")
        if index >= 0:
            self._caveline_dir_combo.setCurrentIndex(index)

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
        self._progress_panel.set_percent(value)

    def set_status(self, text: str) -> None:
        """Set the status label text."""
        self._progress_panel.set_message(text)

    def force_recompute(self) -> bool:
        """Whether the user asked to ignore cached DEM intermediates."""
        return self._force_recompute_checkbox.isChecked()

    def begin_progress(self) -> None:
        """Reset the progress panel and start the live clock for a new run."""
        self._progress_panel.begin()

    def report_progress(self, message: str) -> None:
        """Feed one pipeline progress message into the phase/log panel."""
        self._progress_panel.report(message)

    def end_progress(self, summary: str, *, percent: int | None = None) -> None:
        """Stop the clock and show a terminal summary on the panel."""
        self._progress_panel.end(summary, percent=percent)

    def set_distance_mode(self, active: bool) -> None:
        """Set the measure-distance toggle state programmatically."""
        if self._distance_button.isChecked() != active:
            self._distance_button.setChecked(active)

    def set_profile_mode(self, active: bool) -> None:
        """Set the elevation-profile toggle state programmatically."""
        if self._profile_button.isChecked() != active:
            self._profile_button.setChecked(active)

    def set_analyze_enabled(self, enabled: bool) -> None:
        """Enable or disable the analyze button."""
        self._analyze_button.setEnabled(enabled)

    def set_cancel_enabled(self, enabled: bool) -> None:
        """Enable or disable the cancel button."""
        self._cancel_button.setEnabled(enabled)


__all__ = ["ToolsTab"]
