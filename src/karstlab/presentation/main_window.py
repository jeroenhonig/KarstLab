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
from PySide6.QtGui import QCloseEvent, QDesktopServices
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

from karstlab.business.pipeline import run_headless_analysis
from karstlab.data.land_profiles import list_land_profile_ids, load_land_profile
from karstlab.data.project_io import canonical_output_paths, create_project, save_project
from karstlab.data.schemas import AnalysisParams, DepressionResult, PipelineResult, ProjectFile
from karstlab.infrastructure.whitebox_adapter import WhiteboxAdapter
from karstlab.version import __version__

AnalysisRunner = Callable[[ProjectFile, Callable[[str], None] | None], PipelineResult]


class AnalysisCancelled(RuntimeError):
    """Raised when the GUI requests cooperative analysis cancellation."""


class AnalysisWorker(QObject):
    """Run analysis off the UI thread and report progress through Qt signals."""

    progress = Signal(str)
    finished = Signal(object, object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        dem_path: Path,
        project_base_dir: Path,
        project_name: str,
        profile_id: str,
        analysis_params: AnalysisParams,
        runner: AnalysisRunner | None = None,
    ) -> None:
        super().__init__()
        self._dem_path = dem_path
        self._project_base_dir = project_base_dir
        self._project_name = project_name
        self._profile_id = profile_id
        self._analysis_params = analysis_params
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
            project = save_project(project.model_copy(update={"dem_paths": [self._dem_path]}))
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


class MapView(QWidget):
    """Map container using QWebEngineView when available, QTextBrowser otherwise."""

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
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except ImportError:
            self._fallback = QTextBrowser()
            self._fallback.setOpenExternalLinks(True)
            layout.addWidget(self._fallback)
        else:
            self._web_view = QWebEngineView()
            layout.addWidget(self._web_view)

    def set_empty_state(self) -> None:
        self.set_html(
            """
            <html>
              <body style="margin:0;background:#1a1f2e;color:#e8eaf0;
                           font-family:-apple-system,Segoe UI,sans-serif;">
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
        self.project_dir_edit = QLineEdit(str(_default_project_base_dir()))
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

        self._build_layout()
        self._connect_signals()
        self._populate_profiles()
        self.statusBar().showMessage("Ready")

    def set_dem_path(self, path: Path) -> None:
        self.dem_path_edit.setText(str(path))
        self.status_label.setText(f"DEM selected: {path.name}")
        self.statusBar().showMessage(f"DEM selected: {path}")

    def selected_dem_path(self) -> Path | None:
        text = self.dem_path_edit.text().strip()
        return Path(text) if text else None

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
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._map_panel())
        splitter.addWidget(self._sidebar_panel())
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        self.setCentralWidget(splitter)
        self.setStatusBar(QStatusBar())

    def _map_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.map_view)
        return panel

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
        layout.addWidget(
            _placeholder("Marker import, GPS entry, and POI tools are queued for Phase 7.")
        )
        gpx_button = QPushButton("Import GPX")
        kml_button = QPushButton("Import KML")
        gpx_button.clicked.connect(lambda: self._import_marker_file("GPX", "*.gpx"))
        kml_button.clicked.connect(lambda: self._import_marker_file("KML", "*.kml"))
        layout.addWidget(gpx_button)
        layout.addWidget(kml_button)
        layout.addWidget(self.marker_list)
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

    def _browse_project_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select project folder",
            self.project_dir_edit.text(),
        )
        if path:
            self.project_dir_edit.setText(path)

    def _start_analysis(self) -> None:
        dem_path = self.selected_dem_path()
        if dem_path is None or not dem_path.exists():
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

        worker = AnalysisWorker(
            dem_path=dem_path,
            project_base_dir=Path(self.project_dir_edit.text()).expanduser(),
            project_name=dem_path.stem,
            profile_id=self.profile_combo.currentText(),
            analysis_params=load_land_profile(self.profile_combo.currentText()).analysis_defaults,
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
        self.marker_paths.append(marker_path)
        self.marker_list.addItem(str(marker_path))
        self.statusBar().showMessage(f"Imported marker file: {marker_path.name}")

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
    return run_headless_analysis(
        project,
        hydrology_backend=WhiteboxAdapter.create(work_dir=project.output_dir / "rasters"),
        callback=callback,
    )


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
        font-family: Arial, sans-serif; font-size: 13px;
    }
    QTabWidget::pane, QGroupBox, QFrame#placeholder {
        border: 1px solid #3a4058; border-radius: 6px;
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
