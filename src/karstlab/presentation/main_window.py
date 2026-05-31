"""PySide6 main window for the KarstLab desktop workflow."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThread, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from karstlab.business.marker_manager import (
    ManualMarker,
    manual_marker_to_geodataframe,
    parse_coordinate,
)
from karstlab.business.pipeline import run_headless_analysis
from karstlab.data.land_profiles import load_land_profile
from karstlab.data.project_io import (
    canonical_output_paths,
    load_project,
    save_project,
)
from karstlab.data.schemas import DepressionResult, PipelineResult, ProjectFile
from karstlab.data.user_settings import add_recent_project, load_user_settings, save_user_settings
from karstlab.data.vector_io import read_gpx_waypoints, read_kml_points, to_gpx
from karstlab.infrastructure.whitebox_adapter import WhiteboxAdapter
from karstlab.presentation._styles import _stylesheet
from karstlab.presentation.analysis_worker import (
    AnalysisRunner,
    AnalysisWorker,
)
from karstlab.presentation.export_tab import ExportTab
from karstlab.presentation.guided_workflow import GuidedWorkflowPanel
from karstlab.presentation.layers_tab import LayersTab
from karstlab.presentation.map_view import MapView
from karstlab.presentation.markers_tab import MarkersTab
from karstlab.presentation.results_tab import ResultsTab
from karstlab.presentation.settings_dialog import SettingsDialog
from karstlab.presentation.shortcuts_dialog import ShortcutsDialog
from karstlab.presentation.tools_tab import ToolsTab
from karstlab.presentation.update_banner import UpdateBanner
from karstlab.version import __version__


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

        self.setWindowTitle(self.tr("KarstLab {0}").format(__version__))
        self.resize(1280, 820)
        self.setMinimumSize(980, 640)
        self.setStyleSheet(_stylesheet())

        # Create all panel/tab widget instances
        self._tools_widget = ToolsTab()
        self._results_widget = ResultsTab()
        self._layers_widget = LayersTab()
        self._markers_widget = MarkersTab()
        self._export_widget = ExportTab()
        self._guided_panel = GuidedWorkflowPanel()
        self._update_banner = UpdateBanner()

        # Set default project dir from user settings
        default_project_dir = self._user_settings.last_project_dir or _default_project_base_dir()
        self._tools_widget.set_project_dir(default_project_dir)

        self.map_view = MapView()
        self.sidebar = QTabWidget()
        self.sidebar.setDocumentMode(True)
        self.sidebar.setMinimumWidth(330)

        self.export_paths: dict[str, Path] = {}

        self._build_layout()
        self._connect_signals()
        self._setup_shortcuts()
        self.map_view.marker_placed.connect(self._on_map_marker_placed)
        self.statusBar().showMessage(self.tr("Ready"))

    # ─── Backward-compat proxy properties ────────────────────────────────────

    @property
    def dem_path_edit(self) -> QLineEdit:
        return self._tools_widget._dem_edit

    @property
    def project_dir_edit(self) -> QLineEdit:
        return self._tools_widget._project_edit

    @property
    def profile_combo(self) -> QComboBox:
        return self._tools_widget._profile_combo

    @property
    def progress(self) -> QProgressBar:
        return self._tools_widget._progress_bar

    @property
    def analyze_button(self) -> QPushButton:
        return self._tools_widget._analyze_button

    @property
    def cancel_button(self) -> QPushButton:
        return self._tools_widget._cancel_button

    @property
    def status_label(self) -> QLabel:
        return self._tools_widget._status_label

    @property
    def results_table(self) -> QTableWidget:
        return self._results_widget._table

    @property
    def summary_label(self) -> QLabel:
        return self._results_widget._summary_label

    @property
    def export_buttons(self) -> list[QPushButton]:
        return self._export_widget.export_buttons()

    @property
    def marker_paths(self) -> list[Path]:
        return self._markers_widget._marker_paths

    @marker_paths.setter
    def marker_paths(self, paths: list[Path]) -> None:
        self._markers_widget.set_marker_paths(paths)

    @property
    def marker_list(self) -> QListWidget:
        return self._markers_widget.marker_list  # type: ignore[return-value]

    @property
    def layer_checkboxes(self) -> dict[str, QCheckBox]:
        return self._layers_widget.checkboxes

    @property
    def layer_sliders(self) -> dict[str, QSlider]:
        return self._layers_widget.sliders

    @property
    def layer_state(self) -> dict[str, dict[str, int | bool]]:
        return self._layers_widget.layer_state

    # ─── Public interface ─────────────────────────────────────────────────────

    def set_dem_path(self, path: Path) -> None:
        self._tools_widget.set_dem_path(path)
        self.statusBar().showMessage(self.tr("DEM selected: {0}").format(path))

    def selected_dem_path(self) -> Path | None:
        return self._tools_widget.dem_path()

    def display_results(
        self,
        result: PipelineResult | Sequence[DepressionResult],
        project: ProjectFile | None = None,
    ) -> None:
        self._current_result = result if isinstance(result, PipelineResult) else None
        self._current_project = project
        self._results_widget.display_results(result, project)
        if project is not None:
            self.export_paths = _export_paths(project)
            self._export_widget.set_export_paths(self.export_paths)
            self._export_widget.set_project(project.name)
            map_path = self.export_paths.get("Open map")
            if map_path is not None and map_path.exists():
                self.map_view.load_file(map_path)
            else:
                self.map_view.set_empty_state()
                if map_path is not None:
                    self.statusBar().showMessage(f"Map output not found: {map_path}")
        else:
            self.export_paths = {}

    # ─── Layout ──────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        self._build_menu_bar()

        map_panel = QWidget()
        map_layout = QVBoxLayout(map_panel)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(0)
        map_layout.addWidget(self._update_banner)
        map_layout.addWidget(self.map_view)
        map_layout.addWidget(self._guided_panel)

        sidebar_panel = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_panel)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(10)
        sidebar_layout.addWidget(self.sidebar)

        self.sidebar.addTab(self._tools_widget, self.tr("Tools"))
        self.sidebar.addTab(self._results_widget, self.tr("Results"))
        self.sidebar.addTab(self._layers_widget, self.tr("Layers"))
        self.sidebar.addTab(self._markers_widget, self.tr("Markers"))
        self.sidebar.addTab(self._export_widget, self.tr("Export"))

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(map_panel)
        splitter.addWidget(sidebar_panel)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        self.setCentralWidget(splitter)
        self.setStatusBar(QStatusBar())

    def _build_menu_bar(self) -> None:
        file_menu: QMenu = self.menuBar().addMenu(self.tr("File"))

        new_action = QAction(self.tr("New project"), self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._new_project)
        file_menu.addAction(new_action)

        open_action = QAction(self.tr("Open project…"), self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_project)
        file_menu.addAction(open_action)

        save_action = QAction(self.tr("Save project"), self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_project)
        file_menu.addAction(save_action)

        file_menu.addSeparator()
        self._recent_menu: QMenu = file_menu.addMenu(self.tr("Open recent"))
        self._refresh_recent_menu()

        help_menu: QMenu = self.menuBar().addMenu(self.tr("Help"))

        settings_action = QAction(self.tr("Settings…"), self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._open_settings)
        help_menu.addAction(settings_action)

        shortcuts_action = QAction(self.tr("Keyboard shortcuts"), self)
        shortcuts_action.setShortcut("Ctrl+?")
        shortcuts_action.triggered.connect(self._open_shortcuts)
        help_menu.addAction(shortcuts_action)

    def _connect_signals(self) -> None:
        self._tools_widget.analyze_requested.connect(self._start_analysis)
        self._tools_widget.cancel_requested.connect(self._cancel_analysis)
        self._tools_widget.dem_path_changed.connect(
            lambda p: self.statusBar().showMessage(f"DEM selected: {p.name}")
        )
        self._tools_widget.tile_paths_changed.connect(
            lambda paths: self.statusBar().showMessage(
                self.tr("{0} tiles selected").format(len(paths))
            )
        )
        self._tools_widget.distance_mode_toggled.connect(self._toggle_distance_mode)
        self._tools_widget.project_dir_changed.connect(
            lambda p: self._user_settings_update_project_dir(p)
        )

        self._layers_widget.layer_visibility_changed.connect(
            lambda name, visible: self.statusBar().showMessage(
                f"{name}: {'visible' if visible else 'hidden'}"
            )
        )
        self._layers_widget.layer_opacity_changed.connect(
            lambda name, value: self.statusBar().showMessage(f"{name} opacity: {value}%")
        )

        self._results_widget.depression_selected.connect(self._on_depression_selected)

        self._markers_widget.markers_changed.connect(self._on_markers_changed)
        self._markers_widget.place_on_map_toggled.connect(self._toggle_placement_mode)
        self._markers_widget.gps_marker_add_requested.connect(self._add_gps_marker)
        self._markers_widget.gpx_export_save_requested.connect(self._export_markers_gpx)
        self._markers_widget.status_updated.connect(self.statusBar().showMessage)

        self._export_widget.open_export_requested.connect(
            lambda key: self.statusBar().showMessage(f"Opened: {key}")
        )
        self._export_widget.generate_requested.connect(self._regenerate_exports)

        self._update_banner.dismissed.connect(
            lambda: self.statusBar().showMessage("Update notification dismissed")
        )

        self._guided_panel.step_changed.connect(
            lambda step: self.statusBar().showMessage(f"Guided step {step + 1}/6")
        )

    def _setup_shortcuts(self) -> None:
        from PySide6.QtGui import QShortcut

        shortcuts = [("Ctrl+1", 0), ("Ctrl+2", 1), ("Ctrl+3", 2), ("Ctrl+4", 3), ("Ctrl+5", 4)]
        for key, index in shortcuts:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(
                lambda i=index: self.sidebar.setCurrentIndex(i)
            )

        run_shortcut = QShortcut(QKeySequence("F5"), self)
        run_shortcut.activated.connect(self._start_analysis)

        run_shortcut2 = QShortcut(QKeySequence("Ctrl+R"), self)
        run_shortcut2.activated.connect(self._start_analysis)

        esc_shortcut = QShortcut(QKeySequence("Escape"), self)
        esc_shortcut.activated.connect(self._cancel_analysis)

    # ─── Menu handlers ────────────────────────────────────────────────────────

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._user_settings, parent=self)
        dialog.settings_saved.connect(self._on_settings_saved)
        dialog.exec()

    def _open_shortcuts(self) -> None:
        dialog = ShortcutsDialog(parent=self)
        dialog.exec()

    def _on_settings_saved(self, settings: Any) -> None:
        from karstlab.data.schemas import UserSettings

        if isinstance(settings, UserSettings):
            self._user_settings = save_user_settings(settings)
            self.statusBar().showMessage("Settings saved")

    # ─── Project management ───────────────────────────────────────────────────

    def _new_project(self) -> None:
        self._tools_widget.set_dem_path(Path(""))
        self._tools_widget._dem_edit.clear()
        default_dir = self._user_settings.last_project_dir or _default_project_base_dir()
        self._tools_widget.set_project_dir(default_dir)
        self._tools_widget.set_profile("generic")
        self.map_view.set_empty_state()
        self._results_widget.clear()
        self._markers_widget.set_marker_paths([])
        self._current_project = None
        self._current_result = None
        self.export_paths = {}
        self._export_widget.set_export_paths({})
        self._export_widget.set_project(None)
        self.statusBar().showMessage(self.tr("New project"))

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Open KarstLab project"),
            str(self._user_settings.last_project_dir or Path.home()),
            self.tr("KarstLab project (*.karstlab);;All files (*)"),
        )
        if not path:
            return
        self._load_project_from_path(Path(path))

    def _load_project_from_path(self, project_file: Path) -> None:
        try:
            project = load_project(project_file)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self.tr("Open project failed"), str(exc))
            return

        self._current_project = project
        self._tools_widget.set_project_dir(project.project_dir.parent)

        if project.dem_paths:
            if len(project.dem_paths) == 1:
                self._tools_widget.set_dem_path(project.dem_paths[0])
            else:
                self._tools_widget._dem_edit.setText(
                    f"[{len(project.dem_paths)} tiles] {project.dem_paths[0].parent}"
                )

        self._tools_widget.set_profile(project.land_profile)
        self._tools_widget.set_analysis_params(project.analysis_params)
        self._markers_widget.set_marker_paths(list(project.marker_paths))

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
            except Exception:  # noqa: BLE001
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
        self.statusBar().showMessage(self.tr("Opened: {0}").format(project.name))

    def _save_project(self) -> None:
        if self._current_project is None:
            self.statusBar().showMessage(self.tr("No project to save"))
            return
        try:
            self._current_project = save_project(self._current_project)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self.tr("Save project failed"), str(exc))
            return
        self.statusBar().showMessage(self.tr("Saved: {0}").format(self._current_project.name))

    def _refresh_recent_menu(self) -> None:
        self._recent_menu.clear()
        for recent_path in self._user_settings.recent_projects:
            action = QAction(str(recent_path), self)
            action.triggered.connect(
                lambda _checked=False, p=recent_path: self._load_project_from_path(p)
            )
            self._recent_menu.addAction(action)
        if not self._user_settings.recent_projects:
            placeholder = QAction(self.tr("No recent projects"), self)
            placeholder.setEnabled(False)
            self._recent_menu.addAction(placeholder)

    # ─── Analysis ────────────────────────────────────────────────────────────

    def _resolve_dem_paths(self) -> list[Path]:
        if self._current_project is not None and self._current_project.dem_paths:
            existing = [p for p in self._current_project.dem_paths if p.exists()]
            if existing:
                return existing
        tile_paths = self._tools_widget.tile_paths()
        if tile_paths:
            return [p for p in tile_paths if p.exists()]
        single = self._tools_widget.dem_path()
        if single is not None and single.exists():
            return [single]
        return []

    def _start_analysis(self) -> None:
        dem_paths = self._resolve_dem_paths()
        if not dem_paths:
            QMessageBox.warning(
                self,
                self.tr("DEM required"),
                self.tr("Select an existing GeoTIFF DEM before analysis."),
            )
            return

        self._tools_widget.set_distance_mode(False)
        self.map_view.clear_distance_mode()
        self._tools_widget.set_analyze_enabled(False)
        self._tools_widget.set_cancel_enabled(True)
        self._tools_widget.set_progress(5)
        self._tools_widget.set_status(self.tr("Analysis running"))
        self.statusBar().showMessage(self.tr("Analysis running"))

        profile = load_land_profile(self._tools_widget.profile_id())
        project_name = (
            self._current_project.name
            if self._current_project is not None
            else dem_paths[0].stem
        )
        worker = AnalysisWorker(
            dem_paths=dem_paths,
            project_base_dir=self._tools_widget.project_dir().expanduser(),
            project_name=project_name,
            profile_id=profile.id,
            analysis_params=self._tools_widget.analysis_params(),
            marker_paths=self._markers_widget._marker_paths,
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
        self._tools_widget.set_cancel_enabled(False)
        self._tools_widget.set_status(
            self.tr("Cancel requested; waiting for current analysis step")
        )
        self.statusBar().showMessage(self.tr("Cancel requested"))

    def _on_progress(self, message: str) -> None:
        if message:
            self._tools_widget.set_status(message)
            self.statusBar().showMessage(message)
            self._tools_widget.set_progress(
                max(self._tools_widget._progress_bar.value(), _progress_value(message))
            )

    def _on_analysis_finished(self, result: object, project: object) -> None:
        self._tools_widget.set_progress(100)
        self._tools_widget.set_analyze_enabled(True)
        self._tools_widget.set_cancel_enabled(False)
        self._tools_widget.set_status(self.tr("Analysis complete"))
        self.statusBar().showMessage(self.tr("Analysis complete"))
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
            self._guided_panel.advance_to(4)

    def _on_analysis_failed(self, message: str) -> None:
        self._tools_widget.set_progress(0)
        self._tools_widget.set_analyze_enabled(True)
        self._tools_widget.set_cancel_enabled(False)
        self._tools_widget.set_status(self.tr("Analysis failed"))
        self.statusBar().showMessage(self.tr("Analysis failed"))
        QMessageBox.critical(self, self.tr("Analysis failed"), message)

    def _clear_worker(self) -> None:
        self._analysis_thread = None
        self._analysis_worker = None

    # ─── Map interaction ──────────────────────────────────────────────────────

    def _on_depression_selected(self, depression_id: str, lat: float, lon: float) -> None:
        self.statusBar().showMessage(
            f"Depression {depression_id}: {lat:.6f}, {lon:.6f}"
        )

    def _toggle_placement_mode(self, active: bool) -> None:
        if active:
            self.map_view.inject_click_handler()
            self.statusBar().showMessage(
                self.tr("Click on the map to place a marker. Toggle off to cancel.")
            )
            self.sidebar.setCurrentIndex(3)
        else:
            self.map_view.clear_click_handler()
            self.statusBar().showMessage(self.tr("Placement mode off"))

    def _toggle_distance_mode(self, active: bool) -> None:
        if active:
            self.map_view.start_distance_mode()
            self.statusBar().showMessage(
                self.tr("Click two points on the map to measure distance.")
            )
        else:
            self.map_view.clear_distance_mode()
            self.statusBar().showMessage(self.tr("Distance tool off"))

    def _on_map_marker_placed(self, lat: float, lon: float) -> None:
        self._markers_widget.set_gps_coordinate(lat, lon)
        self.statusBar().showMessage(
            f"Map click: {lat:.6f}, {lon:.6f} — enter name and click Add"
        )

    # ─── Marker operations ────────────────────────────────────────────────────

    def _add_gps_marker(self, name: str, coord_text: str) -> None:
        try:
            lat, lon = parse_coordinate(coord_text)
        except ValueError as exc:
            QMessageBox.warning(self, self.tr("Invalid coordinate"), str(exc))
            return
        marker = ManualMarker(name=name, lat=lat, lon=lon)
        frame = manual_marker_to_geodataframe(marker)
        tmp_path = _manual_marker_tmp_path(name, lat, lon)
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        to_gpx(frame, tmp_path)
        if tmp_path not in self._markers_widget._marker_paths:
            self._markers_widget._marker_paths.append(tmp_path)
        self._markers_widget.refresh_list()
        self._markers_widget.markers_changed.emit(self._markers_widget._marker_paths)
        self._markers_widget.clear_gps_fields()
        self.statusBar().showMessage(self.tr("Added marker: {0} ({1}, {2})").format(name, lat, lon))

    def _on_markers_changed(self, paths: list[Path]) -> None:
        self._persist_marker_paths()

    def _persist_marker_paths(self) -> None:
        if self._current_project is None:
            return
        self._current_project = save_project(
            self._current_project.model_copy(
                update={"marker_paths": self._markers_widget._marker_paths}
            )
        )

    def _export_markers_gpx(self, save_path: str, marker_paths: list[Any]) -> None:
        if not marker_paths:
            self.statusBar().showMessage(self.tr("No markers to export"))
            return
        try:
            frames = []
            for p in marker_paths:
                path = Path(p) if not isinstance(p, Path) else p
                if not path.exists():
                    continue
                try:
                    if path.suffix.lower() == ".gpx":
                        frames.append(read_gpx_waypoints(path))
                    elif path.suffix.lower() == ".kml":
                        frames.append(read_kml_points(path))
                except Exception:  # noqa: BLE001
                    pass
            if not frames:
                self.statusBar().showMessage(self.tr("No readable markers to export"))
                return
            import geopandas as gpd

            combined = gpd.GeoDataFrame(gpd.pd.concat(frames, ignore_index=True))
            to_gpx(combined, Path(save_path))
            name = Path(save_path).name
            self.statusBar().showMessage(self.tr("Exported markers to {0}").format(name))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self.tr("Export failed"), str(exc))

    def _regenerate_exports(self) -> None:
        if self._current_project is None:
            self.statusBar().showMessage("No project to regenerate exports for")
            return
        self.statusBar().showMessage("Regenerating exports — run analysis again to refresh")

    # ─── Settings ─────────────────────────────────────────────────────────────

    def _user_settings_update_project_dir(self, path: Path) -> None:
        self._user_settings = save_user_settings(
            self._user_settings.model_copy(update={"last_project_dir": path})
        )

    # ─── Export ───────────────────────────────────────────────────────────────

    def _open_export(self, key: str) -> None:
        path = self.export_paths.get(key)
        if path is None or not path.exists():
            self.statusBar().showMessage(f"Export not available: {key}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ─── Close ────────────────────────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._analysis_thread is None or not self._analysis_thread.isRunning():
            event.accept()
            return

        reply = QMessageBox.question(
            self,
            self.tr("Analysis running"),
            self.tr("Analysis is still running. Request cancellation and close when it stops?"),
        )
        if reply != QMessageBox.StandardButton.Yes:
            event.ignore()
            return

        self._analysis_thread.requestInterruption()
        self._analysis_thread.quit()
        if not self._analysis_thread.wait(5000):
            QMessageBox.warning(
                self,
                self.tr("Analysis still running"),
                self.tr(
                    "The current analysis step is still running."
                    " Close is postponed to avoid data loss."
                ),
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


def _default_project_base_dir() -> Path:
    import tempfile

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


def _manual_marker_tmp_path(name: str, lat: float, lon: float) -> Path:
    safe_name = "".join(c if c.isalnum() else "-" for c in name)[:32]
    return (
        _default_project_base_dir()
        / "_markers"
        / f"manual-{safe_name}-{lat:.4f}-{lon:.4f}.gpx"
    )




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




__all__ = [
    "AnalysisRunner",
    "AnalysisWorker",
    "MainWindow",
    "MapView",
    "_default_analysis_runner",
    "_progress_value",
    "_stylesheet",
]
