"""PySide6 main window for the KarstLab desktop workflow."""

from __future__ import annotations

import os
import tempfile
import traceback
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from karstlab.business.marker_manager import (
    ManualMarker,
    manual_marker_to_geodataframe,
    parse_coordinate,
    poi_records_to_geodataframe,
)
from karstlab.business.pipeline import run_headless_analysis
from karstlab.data.land_profiles import list_land_profile_ids, load_land_profile
from karstlab.data.poi import FRENCH_DEPARTMENTS, fetch_poi
from karstlab.data.project_io import (
    canonical_output_paths,
    create_project,
    load_project,
    save_project,
)
from karstlab.data.schemas import AnalysisParams, DepressionResult, PipelineResult, ProjectFile
from karstlab.data.settings_resolver import resolve_analysis_params
from karstlab.data.user_settings import add_recent_project, load_user_settings, save_user_settings
from karstlab.data.vector_io import read_gpx_waypoints, read_kml_points
from karstlab.infrastructure.whitebox_adapter import WhiteboxAdapter
from karstlab.version import __version__

AnalysisRunner = Callable[[ProjectFile, Callable[[str], None] | None], PipelineResult]


class AnalysisCancelled(RuntimeError):
    """Raised when the GUI requests cooperative analysis cancellation."""


_GUIDED_STEPS = [
    "Download DEM tiles from the land profile DEM sources.",
    "Select DEM file(s) in the Tools tab.",
    "Choose land profile and project folder.",
    "Click Analyze and wait for the pipeline to complete.",
    "Review Top 25 depressions in the Results tab.",
    "Export markers, KML, or GPX from the Export tab.",
]


class PoiFetchWorker(QObject):
    """Fetch POI records off the UI thread."""

    finished = Signal(list)  # list[PoiRecord]
    failed = Signal(str)

    def __init__(
        self,
        department: str,
        sources: list[str],
        *,
        cache_dir: Path | None = None,
        timeout: float = 10.0,
    ) -> None:
        super().__init__()
        self._department = department
        self._sources = sources
        self._cache_dir = cache_dir
        self._timeout = timeout

    def run(self) -> None:
        try:
            records = fetch_poi(
                self._department,
                self._sources,
                timeout=self._timeout,
                cache_dir=self._cache_dir,
            )
            self.finished.emit(records)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class AnalysisWorker(QObject):
    """Run analysis off the UI thread and report progress through Qt signals."""

    progress = Signal(str)
    finished = Signal(object, object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        dem_paths: list[Path],
        project_base_dir: Path,
        project_name: str,
        profile_id: str,
        analysis_params: AnalysisParams,
        marker_paths: Sequence[Path] = (),
        runner: AnalysisRunner | None = None,
    ) -> None:
        super().__init__()
        self._dem_paths = dem_paths
        self._project_base_dir = project_base_dir
        self._project_name = project_name
        self._profile_id = profile_id
        self._analysis_params = analysis_params
        self._marker_paths = list(marker_paths)
        self._runner = runner

    def run(self) -> None:
        project: ProjectFile | None = None
        try:
            profile = load_land_profile(self._profile_id)
            project = create_project(
                base_dir=self._project_base_dir,
                name=self._project_name,
                land_profile=profile.id,
                crs_analysis=profile.default_crs,
                analysis_params=self._analysis_params,
                overwrite=True,
            )
            project = save_project(
                project.model_copy(
                    update={
                        "dem_paths": self._dem_paths,
                        "marker_paths": self._marker_paths,
                    }
                )
            )
            runner = self._runner or _default_analysis_runner
            result = runner(project, self._emit_progress)
            project = save_project(
                project.model_copy(
                    update={
                        "last_pipeline_result": canonical_output_paths(project)[
                            "pipeline_result"
                        ]
                    }
                )
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as actionable GUI failure text.
            log_path = _write_failure_log(
                project=project,
                fallback_dir=self._project_base_dir,
                project_name=self._project_name,
                error=exc,
            )
            self.failed.emit(f"{exc}\n\nLog: {log_path}")
            return

        self.finished.emit(result, project)

    def _emit_progress(self, message: str) -> None:
        if QThread.currentThread().isInterruptionRequested():
            raise AnalysisCancelled("Analysis cancelled by user")
        self.progress.emit(message)


_CLICK_HANDLER_JS = """
(function() {
    if (window._karstlab_click_active) return;
    window._karstlab_click_active = true;
    for (var k in window) {
        try {
            var o = window[k];
            if (o && typeof o === 'object' && o._leaflet_id !== undefined
                    && typeof o.on === 'function') {
                o.on('click', function(e) {
                    window.location.href = 'karstlab://addmarker?lat='
                        + e.latlng.lat.toFixed(6) + '&lon='
                        + e.latlng.lng.toFixed(6);
                });
            }
        } catch (_) {}
    }
})();
"""

_CLEAR_CLICK_JS = """
(function() {
    window._karstlab_click_active = false;
    for (var k in window) {
        try {
            var o = window[k];
            if (o && typeof o === 'object' && o._leaflet_id !== undefined
                    && typeof o.off === 'function') {
                o.off('click');
            }
        } catch (_) {}
    }
})();
"""


class MapView(QWidget):
    """Map container using QWebEngineView when available, QTextBrowser otherwise."""

    marker_placed = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._web_view: Any | None = None
        self._fallback: QTextBrowser | None = None

        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            self._fallback = QTextBrowser()
            self._fallback.setOpenExternalLinks(True)
            layout.addWidget(self._fallback)
        else:
            self._init_web_view(layout)

        self.set_empty_state()

    def _init_web_view(self, layout: QVBoxLayout) -> None:
        try:
            from PySide6.QtCore import QUrlQuery
            from PySide6.QtWebEngineCore import QWebEnginePage
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except ImportError:
            self._fallback = QTextBrowser()
            self._fallback.setOpenExternalLinks(True)
            layout.addWidget(self._fallback)
            return

        outer = self

        class _KarstLabPage(QWebEnginePage):
            def acceptNavigationRequest(
                self_page,
                url: Any,
                nav_type: Any,
                is_main_frame: bool,
            ) -> bool:
                if url.scheme() == "karstlab" and url.host() == "addmarker":
                    q = QUrlQuery(url.query())
                    try:
                        lat = float(q.queryItemValue("lat"))
                        lon = float(q.queryItemValue("lon"))
                        outer.marker_placed.emit(lat, lon)
                    except ValueError:
                        pass
                    return False
                result: bool = super().acceptNavigationRequest(url, nav_type, is_main_frame)
                return result

        self._web_view = QWebEngineView()
        self._web_view.setPage(_KarstLabPage(self._web_view))
        layout.addWidget(self._web_view)

    def inject_click_handler(self) -> None:
        if self._web_view is not None:
            self._web_view.page().runJavaScript(_CLICK_HANDLER_JS)

    def clear_click_handler(self) -> None:
        if self._web_view is not None:
            self._web_view.page().runJavaScript(_CLEAR_CLICK_JS)

    def set_empty_state(self) -> None:
        self.set_html(
            """
            <html>
                <body style="margin:0;background:#1a1f2e;color:#e8eaf0;
                           font-family:Arial;">
                <div style="height:100vh;display:flex;align-items:center;
                            justify-content:center;text-align:center;">
                  <div>
                    <h1 style="font-size:20px;margin:0 0 8px;">KarstLab</h1>
                    <p style="color:#9ca3b8;margin:0;">Select a DEM and run analysis.</p>
                  </div>
                </div>
              </body>
            </html>
            """
        )

    def load_file(self, path: Path) -> None:
        if self._web_view is not None:
            self._web_view.setUrl(QUrl.fromLocalFile(str(path)))
            return

        if self._fallback is not None:
            self._fallback.setSource(path.as_uri())

    def set_html(self, html: str) -> None:
        if self._web_view is not None:
            self._web_view.setHtml(html)
        elif self._fallback is not None:
            self._fallback.setHtml(html)


class MainWindow(QMainWindow):
    """Map-centric KarstLab main window."""

    def __init__(self, *, analysis_runner: AnalysisRunner | None = None) -> None:
        super().__init__()
        self._analysis_runner = analysis_runner
        self._analysis_thread: QThread | None = None
        self._analysis_worker: AnalysisWorker | None = None
        self._current_result: PipelineResult | None = None
        self._current_project: ProjectFile | None = None
        self._user_settings = load_user_settings()

        self.setWindowTitle(f"KarstLab {__version__}")
        self.resize(1280, 820)
        self.setMinimumSize(980, 640)
        self.setStyleSheet(_stylesheet())

        self.map_view = MapView()
        self.sidebar = QTabWidget()
        self.sidebar.setDocumentMode(True)
        self.sidebar.setMinimumWidth(330)

        self.dem_path_edit = QLineEdit()
        self.dem_path_edit.setReadOnly(True)
        self.profile_combo = QComboBox()
        default_project_dir = self._user_settings.last_project_dir or _default_project_base_dir()
        self.project_dir_edit = QLineEdit(str(default_project_dir))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.analyze_button = QPushButton("Analyze")
        self.analyze_button.setObjectName("primaryButton")
        self.status_label = QLabel("Ready")
        self.results_table = QTableWidget(0, 5)
        self.summary_label = QLabel("No analysis results")
        self.export_buttons: list[QPushButton] = []
        self.export_paths: dict[str, Path] = {}
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.layer_state: dict[str, dict[str, int | bool]] = {}
        self.layer_checkboxes: dict[str, QCheckBox] = {}
        self.layer_sliders: dict[str, QSlider] = {}
        self.marker_paths: list[Path] = []
        self.marker_list = QListWidget()
        self._poi_thread: QThread | None = None
        self._guided_step: int = 0
        self._placement_mode: bool = False
        self._placement_button: QPushButton | None = None

        self._build_layout()
        self._connect_signals()
        self._populate_profiles()
        self.map_view.marker_placed.connect(self._on_map_marker_placed)
        self.statusBar().showMessage("Ready")

    def set_dem_path(self, path: Path) -> None:
        self.dem_path_edit.setText(str(path))
        self.status_label.setText(f"DEM selected: {path.name}")
        self.statusBar().showMessage(f"DEM selected: {path}")

    def selected_dem_path(self) -> Path | None:
        text = self.dem_path_edit.text().strip()
        return Path(text) if text else None

    def _resolve_dem_paths(self) -> list[Path]:
        """Return DEM paths for the next analysis run.

        Uses the loaded project's dem_paths when available (preserves multi-tile
        context), otherwise falls back to the single path in the QLineEdit.
        """
        if self._current_project is not None and self._current_project.dem_paths:
            existing = [p for p in self._current_project.dem_paths if p.exists()]
            if existing:
                return existing
        single = self.selected_dem_path()
        if single is not None and single.exists():
            return [single]
        return []

    def display_results(
        self,
        result: PipelineResult | Sequence[DepressionResult],
        project: ProjectFile | None = None,
    ) -> None:
        self._current_result = result if isinstance(result, PipelineResult) else None
        self._current_project = project
        depressions = result.depressions if isinstance(result, PipelineResult) else list(result)
        top = result.top_depressions if isinstance(result, PipelineResult) else list(result)
        self.summary_label.setText(
            f"{len(depressions)} depressions detected; {len(top)} ranked results"
        )
        self.results_table.setRowCount(len(top))
        for row, depression in enumerate(top):
            values = [
                str(depression.rank if depression.rank is not None else row + 1),
                depression.id,
                f"{depression.max_depth_m:.2f}",
                f"{depression.area_m2:.1f}",
                f"{depression.centroid.lat:.6f}, {depression.centroid.lon:.6f}",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.results_table.setItem(row, column, item)

        for button in self.export_buttons:
            button.setEnabled(project is not None)

        if project is not None:
            self.export_paths = _export_paths(project)
            for button in self.export_buttons:
                path = self.export_paths.get(button.text())
                button.setEnabled(path is not None and path.exists())
                button.setToolTip(str(path) if path is not None else "")

            map_path = self.export_paths["Open map"]
            if map_path.exists():
                self.map_view.load_file(map_path)
            else:
                self.map_view.set_empty_state()
                self.statusBar().showMessage(f"Map output not found: {map_path}")
        else:
            self.export_paths = {}

    def _build_layout(self) -> None:
        self._build_menu_bar()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._map_panel())
        splitter.addWidget(self._sidebar_panel())
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        self.setCentralWidget(splitter)
        self.setStatusBar(QStatusBar())

    def _build_menu_bar(self) -> None:
        file_menu: QMenu = self.menuBar().addMenu("File")

        new_action = QAction("New project", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._new_project)
        file_menu.addAction(new_action)

        open_action = QAction("Open project…", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_project)
        file_menu.addAction(open_action)

        save_action = QAction("Save project", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_project)
        file_menu.addAction(save_action)

        file_menu.addSeparator()
        self._recent_menu: QMenu = file_menu.addMenu("Open recent")
        self._refresh_recent_menu()

    def _map_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.map_view)
        layout.addWidget(self._guided_workflow_bar())
        return panel

    def _guided_workflow_bar(self) -> QWidget:
        self._guided_bar = QFrame()
        self._guided_bar.setObjectName("guidedBar")
        bar_layout = QHBoxLayout(self._guided_bar)
        bar_layout.setContentsMargins(12, 8, 12, 8)
        self._guided_label = QLabel(self._guided_step_text())
        self._guided_label.setObjectName("secondaryText")
        self._guided_label.setWordWrap(True)
        prev_btn = QPushButton("◀")
        prev_btn.setFixedWidth(32)
        prev_btn.clicked.connect(self._guided_prev)
        next_btn = QPushButton("▶")
        next_btn.setFixedWidth(32)
        next_btn.clicked.connect(self._guided_next)
        bar_layout.addWidget(prev_btn)
        bar_layout.addWidget(self._guided_label, 1)
        bar_layout.addWidget(next_btn)
        return self._guided_bar

    def _guided_step_text(self) -> str:
        step = self._guided_step
        total = len(_GUIDED_STEPS)
        return f"Step {step + 1}/{total}: {_GUIDED_STEPS[step]}"

    def _guided_prev(self) -> None:
        if self._guided_step > 0:
            self._guided_step -= 1
            self._guided_label.setText(self._guided_step_text())

    def _guided_next(self) -> None:
        if self._guided_step < len(_GUIDED_STEPS) - 1:
            self._guided_step += 1
            self._guided_label.setText(self._guided_step_text())

    def _sidebar_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(self.sidebar)

        self.sidebar.addTab(self._tools_tab(), "Tools")
        self.sidebar.addTab(self._results_tab(), "Results")
        self.sidebar.addTab(self._layers_tab(), "Layers")
        self.sidebar.addTab(self._markers_tab(), "Markers")
        self.sidebar.addTab(self._export_tab(), "Export")
        return panel

    def _tools_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        file_row = QHBoxLayout()
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._browse_dem)
        file_row.addWidget(self.dem_path_edit)
        file_row.addWidget(browse_button)

        form = QFormLayout()
        form.addRow("DEM", _wrap_layout(file_row))
        project_row = QHBoxLayout()
        project_button = QPushButton("Browse")
        project_button.clicked.connect(self._browse_project_dir)
        project_row.addWidget(self.project_dir_edit)
        project_row.addWidget(project_button)
        form.addRow("Project folder", _wrap_layout(project_row))
        form.addRow("Land profile", self.profile_combo)

        params = _parameter_group()
        layout.addLayout(form)
        layout.addWidget(params)
        layout.addWidget(self.progress)
        layout.addWidget(self.analyze_button)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        return tab

    def _results_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(self.summary_label)
        self.results_table.setHorizontalHeaderLabels(
            ["Rank", "ID", "Depth m", "Area m2", "Lat, Lon"]
        )
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.results_table)
        return tab

    def _layers_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        for label, checked in (
            ("Doline footprints", True),
            ("Top 25 markers", True),
            ("Contours", True),
            ("Streams", False),
            ("Hillshade", False),
        ):
            row = QHBoxLayout()
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(80 if checked else 40)
            self.layer_state[label] = {"visible": checked, "opacity": slider.value()}
            self.layer_checkboxes[label] = checkbox
            self.layer_sliders[label] = slider
            checkbox.toggled.connect(
                lambda visible, layer=label: self._set_layer_visible(layer, visible)
            )
            slider.valueChanged.connect(
                lambda value, layer=label: self._set_layer_opacity(layer, value)
            )
            row.addWidget(checkbox)
            row.addWidget(slider)
            layout.addLayout(row)
        layout.addStretch(1)
        return tab

    def _markers_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # --- GPS coordinate entry ---
        gps_group = QGroupBox("Add marker by coordinate")
        gps_form = QFormLayout(gps_group)
        self._gps_name_edit = QLineEdit()
        self._gps_name_edit.setPlaceholderText("Marker name")
        self._gps_coord_edit = QLineEdit()
        self._gps_coord_edit.setPlaceholderText("44.1234, 1.5678  or  44°07′N 1°34′E")
        gps_add_button = QPushButton("Add")
        gps_add_button.clicked.connect(self._add_gps_marker)
        gps_form.addRow("Name", self._gps_name_edit)
        gps_form.addRow("Coordinate", self._gps_coord_edit)
        gps_form.addRow("", gps_add_button)
        layout.addWidget(gps_group)

        # --- File import + map placement ---
        import_row = QHBoxLayout()
        gpx_button = QPushButton("Import GPX")
        kml_button = QPushButton("Import KML")
        gpx_button.clicked.connect(lambda: self._import_marker_file("GPX", "*.gpx"))
        kml_button.clicked.connect(lambda: self._import_marker_file("KML", "*.kml"))
        self._placement_button = QPushButton("Place on map")
        self._placement_button.setCheckable(True)
        self._placement_button.toggled.connect(self._toggle_placement_mode)
        import_row.addWidget(gpx_button)
        import_row.addWidget(kml_button)
        import_row.addWidget(self._placement_button)
        layout.addLayout(import_row)

        # --- POI panel ---
        poi_group = QGroupBox("Load POI from online source")
        poi_form = QFormLayout(poi_group)
        self._poi_source_combo = QComboBox()
        self._poi_source_combo.addItem("BRGM Cavités Géorisques", "brgm_cavites")
        self._poi_source_combo.addItem("Spélébase (stub)", "spelebase")
        self._poi_dept_combo = QComboBox()
        for code, name in sorted(FRENCH_DEPARTMENTS.items()):
            self._poi_dept_combo.addItem(f"{code} — {name}", code)
        self._poi_fetch_button = QPushButton("Fetch")
        self._poi_fetch_button.clicked.connect(self._fetch_poi)
        poi_form.addRow("Source", self._poi_source_combo)
        poi_form.addRow("Department", self._poi_dept_combo)
        poi_form.addRow("", self._poi_fetch_button)
        layout.addWidget(poi_group)

        # --- Marker list ---
        layout.addWidget(QLabel("Imported markers:"))
        layout.addWidget(self.marker_list)

        # Delete selected button
        delete_button = QPushButton("Remove selected")
        delete_button.clicked.connect(self._remove_selected_marker)
        layout.addWidget(delete_button)
        layout.addStretch(1)
        return tab

    def _export_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        for label in (
            "Open report",
            "Open GeoJSON",
            "Open KML",
            "Open GPX",
            "Open statistics JSON",
        ):
            button = QPushButton(label)
            button.setEnabled(False)
            button.clicked.connect(lambda _checked=False, key=label: self._open_export(key))
            self.export_buttons.append(button)
            layout.addWidget(button)
        layout.addStretch(1)
        return tab

    def _connect_signals(self) -> None:
        self.analyze_button.clicked.connect(self._start_analysis)
        self.cancel_button.clicked.connect(self._cancel_analysis)

    def _populate_profiles(self) -> None:
        self.profile_combo.addItems(list_land_profile_ids())
        generic_index = self.profile_combo.findText("generic")
        if generic_index >= 0:
            self.profile_combo.setCurrentIndex(generic_index)

    def _browse_dem(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Select DEM",
            str(Path.home()),
            "GeoTIFF (*.tif *.tiff);;All files (*)",
        )
        if path:
            self.set_dem_path(Path(path))

    def _new_project(self) -> None:
        self.dem_path_edit.clear()
        default_dir = self._user_settings.last_project_dir or _default_project_base_dir()
        self.project_dir_edit.setText(str(default_dir))
        self.profile_combo.setCurrentIndex(self.profile_combo.findText("generic"))
        self.map_view.set_empty_state()
        self.results_table.setRowCount(0)
        self.summary_label.setText("No analysis results")
        self.marker_paths.clear()
        self._refresh_marker_list()
        self._current_project = None
        self._current_result = None
        self.export_paths = {}
        for button in self.export_buttons:
            button.setEnabled(False)
        self.statusBar().showMessage("New project")

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open KarstLab project",
            str(self._user_settings.last_project_dir or Path.home()),
            "KarstLab project (*.karstlab);;All files (*)",
        )
        if not path:
            return
        self._load_project_from_path(Path(path))

    def _load_project_from_path(self, project_file: Path) -> None:
        try:
            project = load_project(project_file)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Open project failed", str(exc))
            return

        self._current_project = project
        self.project_dir_edit.setText(str(project.project_dir.parent))

        if project.dem_paths:
            if len(project.dem_paths) == 1:
                self.dem_path_edit.setText(str(project.dem_paths[0]))
            else:
                self.dem_path_edit.setText(
                    f"[{len(project.dem_paths)} tiles] {project.dem_paths[0].parent}"
                )

        profile_index = self.profile_combo.findText(project.land_profile)
        if profile_index >= 0:
            self.profile_combo.setCurrentIndex(profile_index)

        self.marker_paths = list(project.marker_paths)
        self._refresh_marker_list()

        if project.last_pipeline_result and project.last_pipeline_result.exists():
            try:
                import json as _json

                from karstlab.data.schemas import PipelineResult as _PR

                payload = _json.loads(
                    project.last_pipeline_result.read_text(encoding="utf-8")
                )
                result = _PR.model_validate(payload)
                self.display_results(result, project)
                self.sidebar.setCurrentIndex(1)
            except Exception:  # noqa: BLE001 - non-fatal, just show empty state
                self.map_view.set_empty_state()

        self._user_settings = save_user_settings(
            add_recent_project(
                self._user_settings.model_copy(
                    update={"last_project_dir": project.project_dir.parent}
                ),
                project_file,
            )
        )
        self._refresh_recent_menu()
        self.statusBar().showMessage(f"Opened: {project.name}")

    def _save_project(self) -> None:
        if self._current_project is None:
            self.statusBar().showMessage("No project to save")
            return
        try:
            self._current_project = save_project(self._current_project)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save project failed", str(exc))
            return
        self.statusBar().showMessage(f"Saved: {self._current_project.name}")

    def _refresh_recent_menu(self) -> None:
        self._recent_menu.clear()
        for recent_path in self._user_settings.recent_projects:
            action = QAction(str(recent_path), self)
            action.triggered.connect(
                lambda _checked=False, p=recent_path: self._load_project_from_path(p)
            )
            self._recent_menu.addAction(action)
        if not self._user_settings.recent_projects:
            placeholder = QAction("No recent projects", self)
            placeholder.setEnabled(False)
            self._recent_menu.addAction(placeholder)

    def _browse_project_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select project folder",
            self.project_dir_edit.text(),
        )
        if path:
            self.project_dir_edit.setText(path)
            self._user_settings = save_user_settings(
                self._user_settings.model_copy(update={"last_project_dir": Path(path)})
            )

    def _start_analysis(self) -> None:
        dem_paths = self._resolve_dem_paths()
        if not dem_paths:
            QMessageBox.warning(
                self,
                "DEM required",
                "Select an existing GeoTIFF DEM before analysis.",
            )
            return

        self.analyze_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(5)
        self.status_label.setText("Analysis running")
        self.statusBar().showMessage("Analysis running")

        profile = load_land_profile(self.profile_combo.currentText())
        project_name = (
            self._current_project.name
            if self._current_project is not None
            else dem_paths[0].stem
        )
        worker = AnalysisWorker(
            dem_paths=dem_paths,
            project_base_dir=Path(self.project_dir_edit.text()).expanduser(),
            project_name=project_name,
            profile_id=profile.id,
            analysis_params=resolve_analysis_params(
                project=self._current_project,
                user_settings=self._user_settings,
                land_profile=profile,
            ),
            marker_paths=self.marker_paths,
            runner=self._analysis_runner,
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_analysis_finished)
        worker.failed.connect(self._on_analysis_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_worker)
        self._analysis_thread = thread
        self._analysis_worker = worker
        thread.start()

    def _cancel_analysis(self) -> None:
        if self._analysis_thread is None:
            return
        self._analysis_thread.requestInterruption()
        self.cancel_button.setEnabled(False)
        self.status_label.setText("Cancel requested; waiting for current analysis step")
        self.statusBar().showMessage("Cancel requested")

    def _open_export(self, key: str) -> None:
        path = self.export_paths.get(key)
        if path is None or not path.exists():
            self.statusBar().showMessage(f"Export not available: {key}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _set_layer_visible(self, layer: str, visible: bool) -> None:
        self.layer_state.setdefault(layer, {"visible": visible, "opacity": 100})[
            "visible"
        ] = visible
        self.statusBar().showMessage(f"{layer}: {'visible' if visible else 'hidden'}")

    def _set_layer_opacity(self, layer: str, value: int) -> None:
        self.layer_state.setdefault(layer, {"visible": True, "opacity": value})[
            "opacity"
        ] = value
        self.statusBar().showMessage(f"{layer} opacity: {value}%")

    def _toggle_placement_mode(self, active: bool) -> None:
        self._placement_mode = active
        if active:
            self.map_view.inject_click_handler()
            self.statusBar().showMessage(
                "Click on the map to place a marker. Toggle off to cancel."
            )
            self.sidebar.setCurrentIndex(3)  # Markers tab
        else:
            self.map_view.clear_click_handler()
            self.statusBar().showMessage("Placement mode off")

    def _on_map_marker_placed(self, lat: float, lon: float) -> None:
        self._gps_coord_edit.setText(f"{lat:.6f}, {lon:.6f}")
        if not self._gps_name_edit.text().strip():
            self._gps_name_edit.setText(f"Marker {lat:.4f},{lon:.4f}")
        self._gps_name_edit.setFocus()
        self.statusBar().showMessage(f"Map click: {lat:.6f}, {lon:.6f} — enter name and click Add")

    def _add_gps_marker(self) -> None:
        coord_text = self._gps_coord_edit.text().strip()
        name = self._gps_name_edit.text().strip() or "Marker"
        try:
            lat, lon = parse_coordinate(coord_text)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid coordinate", str(exc))
            return
        marker = ManualMarker(name=name, lat=lat, lon=lon)
        frame = manual_marker_to_geodataframe(marker)
        tmp_path = _manual_marker_tmp_path(name, lat, lon)
        from karstlab.data.vector_io import to_gpx as _to_gpx

        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        _to_gpx(frame, tmp_path)
        if tmp_path not in self.marker_paths:
            self.marker_paths.append(tmp_path)
        self._refresh_marker_list()
        self._persist_marker_paths()
        self._gps_coord_edit.clear()
        self._gps_name_edit.clear()
        self.statusBar().showMessage(f"Added marker: {name} ({lat:.6f}, {lon:.6f})")

    def _fetch_poi(self) -> None:
        if self._poi_thread is not None and self._poi_thread.isRunning():
            self.statusBar().showMessage("POI fetch already running")
            return
        department = self._poi_dept_combo.currentData()
        source = self._poi_source_combo.currentData()
        self._poi_fetch_button.setEnabled(False)
        self.statusBar().showMessage(f"Fetching {source} POI for department {department}…")
        cache_dir = (
            self._current_project.cache_dir if self._current_project is not None else None
        )
        worker = PoiFetchWorker(department, [source], cache_dir=cache_dir)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda recs: self._on_poi_finished(recs, department, source))
        worker.failed.connect(self._on_poi_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_poi_thread)
        self._poi_thread = thread
        thread.start()

    def _on_poi_finished(self, records: list[Any], department: str, source: str) -> None:
        self._poi_fetch_button.setEnabled(True)
        if not records:
            self.statusBar().showMessage(
                f"No POI found for {source} / department {department}"
            )
            return
        frame = poi_records_to_geodataframe(records)
        cache_dir = (
            self._current_project.cache_dir if self._current_project is not None else None
        )
        tmp_path = _poi_tmp_path(source, department, cache_dir)
        from karstlab.data.vector_io import to_gpx as _to_gpx

        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        _to_gpx(frame, tmp_path)
        if tmp_path not in self.marker_paths:
            self.marker_paths.append(tmp_path)
        self._refresh_marker_list()
        self._persist_marker_paths()
        self.statusBar().showMessage(
            f"Loaded {len(records)} POI from {source} / department {department}"
        )

    def _on_poi_failed(self, message: str) -> None:
        self._poi_fetch_button.setEnabled(True)
        self.statusBar().showMessage(f"POI fetch failed: {message}")

    def _clear_poi_thread(self) -> None:
        self._poi_thread = None

    def _remove_selected_marker(self) -> None:
        selected = self.marker_list.currentRow()
        if selected < 0 or selected >= len(self.marker_paths):
            return
        removed = self.marker_paths.pop(selected)
        self._refresh_marker_list()
        self._persist_marker_paths()
        self.statusBar().showMessage(f"Removed marker: {removed.name}")

    def _import_marker_file(self, label: str, pattern: str) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            f"Import {label}",
            str(Path.home()),
            f"{label} files ({pattern});;All files (*)",
        )
        if not path:
            return
        marker_path = Path(path)
        try:
            markers = _read_marker_points(label, marker_path)
        except Exception as exc:  # noqa: BLE001 - parse errors need to reach the user.
            QMessageBox.warning(self, f"Import {label} failed", str(exc))
            return

        if len(markers) == 0:
            QMessageBox.warning(
                self,
                f"No markers in {label}",
                f"{marker_path.name} contains no readable waypoints or placemarks.",
            )
            return

        if marker_path not in self.marker_paths:
            self.marker_paths.append(marker_path)
        self._refresh_marker_list()
        self._persist_marker_paths()
        count = len(markers)
        suffix = "marker" if count == 1 else "markers"
        self.statusBar().showMessage(f"Imported {count} {suffix}: {marker_path.name}")

    def _refresh_marker_list(self) -> None:
        self.marker_list.clear()
        for marker_path in self.marker_paths:
            if not marker_path.exists():
                self.marker_list.addItem(f"[Missing] {marker_path.name}")
                continue
            try:
                markers = _read_marker_points(marker_path.suffix.lstrip("."), marker_path)
            except Exception:  # noqa: BLE001 - keep stale/broken paths visible in state.
                self.marker_list.addItem(f"[Error] {marker_path.name}")
            else:
                self.marker_list.addItem(_marker_list_label(marker_path, markers))

    def _persist_marker_paths(self) -> None:
        if self._current_project is None:
            return
        self._current_project = save_project(
            self._current_project.model_copy(update={"marker_paths": self.marker_paths})
        )

    def _on_progress(self, message: str) -> None:
        if message:
            self.status_label.setText(message)
            self.statusBar().showMessage(message)
            self.progress.setValue(max(self.progress.value(), _progress_value(message)))

    def _on_analysis_finished(self, result: object, project: object) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.analyze_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status_label.setText("Analysis complete")
        self.statusBar().showMessage("Analysis complete")
        self.display_results(result, project)  # type: ignore[arg-type]
        self.sidebar.setCurrentIndex(1)
        if isinstance(project, ProjectFile):
            project_file = project.project_dir / "project.karstlab"
            if project_file.exists():
                self._user_settings = save_user_settings(
                    add_recent_project(
                        self._user_settings.model_copy(
                            update={"last_project_dir": project.project_dir.parent}
                        ),
                        project_file,
                    )
                )
                self._refresh_recent_menu()

    def _on_analysis_failed(self, message: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.analyze_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status_label.setText("Analysis failed")
        self.statusBar().showMessage("Analysis failed")
        QMessageBox.critical(self, "Analysis failed", message)

    def _clear_worker(self) -> None:
        self._analysis_thread = None
        self._analysis_worker = None

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._analysis_thread is None or not self._analysis_thread.isRunning():
            event.accept()
            return

        reply = QMessageBox.question(
            self,
            "Analysis running",
            "Analysis is still running. Request cancellation and close when it stops?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            event.ignore()
            return

        self._analysis_thread.requestInterruption()
        self._analysis_thread.quit()
        if not self._analysis_thread.wait(5000):
            QMessageBox.warning(
                self,
                "Analysis still running",
                "The current analysis step is still running. "
                "Close is postponed to avoid data loss.",
            )
            event.ignore()
            return
        event.accept()


def _default_analysis_runner(
    project: ProjectFile,
    callback: Callable[[str], None] | None,
) -> PipelineResult:
    result = run_headless_analysis(
        project,
        hydrology_backend=WhiteboxAdapter.create(work_dir=project.output_dir / "rasters"),
        callback=callback,
    )
    return result


def _read_marker_points(label: str, path: Path) -> Any:
    normalized_label = label.upper()
    if normalized_label == "GPX":
        return read_gpx_waypoints(path)
    if normalized_label == "KML":
        return read_kml_points(path)
    raise ValueError(f"Unsupported marker format: {label}")


def _marker_list_label(path: Path, markers: Any) -> str:
    count = len(markers)
    suffix = "marker" if count == 1 else "markers"
    names: list[str] = []
    if "name" in markers:
        names = [str(name) for name in markers["name"].dropna().head(3).to_list()]
    name_preview = f": {', '.join(names)}" if names else ""
    return f"{path.name} ({count} {suffix}){name_preview}"


def _manual_marker_tmp_path(name: str, lat: float, lon: float) -> Path:
    safe_name = "".join(c if c.isalnum() else "-" for c in name)[:32]
    return _default_project_base_dir() / "_markers" / f"manual-{safe_name}-{lat:.4f}-{lon:.4f}.gpx"


def _poi_tmp_path(source: str, department: str, cache_dir: Path | None) -> Path:
    base = cache_dir if cache_dir else _default_project_base_dir() / "_poi"
    return base / "poi" / f"{source}_{department}.gpx"


def _default_project_base_dir() -> Path:
    return Path(tempfile.gettempdir()) / "karstlab-gui-projects"


def _export_paths(project: ProjectFile) -> dict[str, Path]:
    paths = canonical_output_paths(project)
    return {
        "Open report": paths["report"],
        "Open GeoJSON": paths["dolines_geojson"],
        "Open KML": paths["dolines_kml"],
        "Open GPX": paths["top_depressions_gpx"],
        "Open statistics JSON": paths["statistics"],
        "Open map": paths["interactive_map"],
    }


def _write_failure_log(
    *,
    project: ProjectFile | None,
    fallback_dir: Path,
    project_name: str,
    error: Exception,
) -> Path:
    logs_dir = project.logs_dir if project is not None else fallback_dir / "_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(char if char.isalnum() or char in "-_" else "-" for char in project_name)
    path = logs_dir / f"analysis-error-{safe_name or 'project'}-{timestamp}.log"
    path.write_text(
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        encoding="utf-8",
    )
    return path


def _progress_value(message: str) -> int:
    if "analysis complete" in message.lower():
        return 100
    for marker, value in (
        ("BreachDepressions", 15),
        ("D8Pointer", 30),
        ("D8FlowAccumulation", 45),
        ("ExtractStreams", 60),
        ("FillDepressions", 70),
        ("Saving data", 80),
        ("Output file written", 85),
    ):
        if marker.lower() in message.lower():
            return value
    if "%" in message:
        return min(90, max(10, _extract_percent(message)))
    return 10


def _extract_percent(message: str) -> int:
    tokens = message.rsplit("%", maxsplit=1)[0].split()
    if not tokens:
        return 10
    try:
        return int(float(tokens[-1]))
    except ValueError:
        return 10


def _parameter_group() -> QGroupBox:
    group = QGroupBox("Analysis parameters")
    grid = QGridLayout(group)
    for row, label in enumerate(
        (
            "Contour interval",
            "Min depth",
            "Max depth",
            "Min area",
            "Max area",
            "Stream threshold",
        )
    ):
        value = QLabel("Profile default")
        value.setObjectName("secondaryText")
        grid.addWidget(QLabel(label), row, 0)
        grid.addWidget(value, row, 1)
    return group


def _placeholder(text: str) -> QFrame:
    frame = QFrame()
    frame.setObjectName("placeholder")
    layout = QVBoxLayout(frame)
    label = QLabel(text)
    label.setWordWrap(True)
    layout.addWidget(label)
    return frame


def _wrap_layout(layout: QHBoxLayout) -> QWidget:
    widget = QWidget()
    widget.setLayout(layout)
    return widget


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


__all__ = ["AnalysisRunner", "AnalysisWorker", "MainWindow", "MapView"]
