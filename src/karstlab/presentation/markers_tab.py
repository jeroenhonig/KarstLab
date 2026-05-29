"""Marker management tab widget for KarstLab."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from karstlab.business.marker_manager import poi_records_to_geodataframe
from karstlab.data.poi import FRENCH_DEPARTMENTS, fetch_poi
from karstlab.data.vector_io import read_gpx_waypoints, read_kml_points, to_gpx


class PoiFetchWorker(QObject):
    """Fetch POI records off the UI thread."""

    finished = Signal(list)
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


class MarkersTab(QWidget):
    """Marker management tab for importing, creating, and exporting markers."""

    markers_changed = Signal(list)
    place_on_map_toggled = Signal(bool)
    gps_marker_add_requested = Signal(str, str)
    gpx_export_save_requested = Signal(str, list)
    status_updated = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._marker_paths: list[Path] = []
        self._poi_thread: QThread | None = None
        self._placement_button: QPushButton | None = None
        self._gps_name_edit: QLineEdit | None = None
        self._gps_coord_edit: QLineEdit | None = None
        self._poi_source_combo: QComboBox | None = None
        self._poi_dept_combo: QComboBox | None = None
        self._poi_fetch_button: QPushButton | None = None
        self.marker_list: QListWidget | None = None
        self._build_layout()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(self._gps_group())
        layout.addLayout(self._import_row())
        layout.addWidget(self._poi_group())

        layout.addWidget(QLabel("Imported markers:"))
        self.marker_list = QListWidget()
        layout.addWidget(self.marker_list)

        delete_button = QPushButton("Remove selected")
        delete_button.clicked.connect(self._remove_selected)
        layout.addWidget(delete_button)
        layout.addStretch(1)

    def _gps_group(self) -> QGroupBox:
        group = QGroupBox("Add marker by coordinate")
        form = QFormLayout(group)
        self._gps_name_edit = QLineEdit()
        self._gps_name_edit.setPlaceholderText("Marker name")
        self._gps_coord_edit = QLineEdit()
        self._gps_coord_edit.setPlaceholderText("44.1234, 1.5678  or  44°07′N 1°34′E")
        gps_add_button = QPushButton("Add")
        gps_add_button.clicked.connect(self._add_gps_marker)
        form.addRow("Name", self._gps_name_edit)
        form.addRow("Coordinate", self._gps_coord_edit)
        form.addRow("", gps_add_button)
        return group

    def _import_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        gpx_button = QPushButton("Import GPX")
        kml_button = QPushButton("Import KML")
        export_gpx_button = QPushButton("Export GPX")
        gpx_button.clicked.connect(lambda: self._import_marker_file("GPX", "*.gpx"))
        kml_button.clicked.connect(lambda: self._import_marker_file("KML", "*.kml"))
        export_gpx_button.clicked.connect(self._export_gpx)
        self._placement_button = QPushButton("Place on map")
        self._placement_button.setCheckable(True)
        self._placement_button.toggled.connect(self._on_placement_toggled)
        row.addWidget(gpx_button)
        row.addWidget(kml_button)
        row.addWidget(self._placement_button)
        row.addWidget(export_gpx_button)
        return row

    def _poi_group(self) -> QGroupBox:
        group = QGroupBox("Load POI from online source")
        form = QFormLayout(group)
        self._poi_source_combo = QComboBox()
        self._poi_source_combo.addItem("BRGM Cavités Géorisques", "brgm_cavites")
        self._poi_source_combo.addItem("Spélébase (stub)", "spelebase")
        self._poi_dept_combo = QComboBox()
        for code, name in sorted(FRENCH_DEPARTMENTS.items()):
            self._poi_dept_combo.addItem(f"{code} — {name}", code)
        self._poi_fetch_button = QPushButton("Fetch")
        self._poi_fetch_button.clicked.connect(self._fetch_poi)
        form.addRow("Source", self._poi_source_combo)
        form.addRow("Department", self._poi_dept_combo)
        form.addRow("", self._poi_fetch_button)
        return group

    def set_marker_paths(self, paths: list[Path]) -> None:
        """Set marker paths and refresh display."""
        self._marker_paths = list(paths)
        self.refresh_list()
        self.markers_changed.emit(self._marker_paths)

    def marker_paths(self) -> list[Path]:
        """Return current marker paths."""
        return list(self._marker_paths)

    def refresh_list(self) -> None:
        """Rebuild marker list from current paths."""
        if self.marker_list is None:
            return
        self.marker_list.clear()
        for marker_path in self._marker_paths:
            if not marker_path.exists():
                self.marker_list.addItem(f"[Missing] {marker_path.name}")
                continue
            try:
                markers = self._read_marker_points(marker_path)
            except Exception:  # noqa: BLE001
                self.marker_list.addItem(f"[Error] {marker_path.name}")
            else:
                self.marker_list.addItem(self._marker_list_label(marker_path, markers))

    def set_poi_fetch_enabled(self, enabled: bool) -> None:
        """Enable or disable POI fetch button."""
        if self._poi_fetch_button is not None:
            self._poi_fetch_button.setEnabled(enabled)

    def placement_button(self) -> QPushButton | None:
        """Return placement toggle button."""
        return self._placement_button

    def _add_gps_marker(self) -> None:
        if self._gps_coord_edit is None or self._gps_name_edit is None:
            return
        coord_text = self._gps_coord_edit.text().strip()
        name = self._gps_name_edit.text().strip() or "Marker"
        if coord_text:
            self.gps_marker_add_requested.emit(name, coord_text)

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
            markers = self._read_marker_points(marker_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, f"Import {label} failed", str(exc))
            return
        if len(markers) == 0:
            QMessageBox.warning(
                self,
                f"No markers in {label}",
                f"{marker_path.name} contains no readable waypoints or placemarks.",
            )
            return
        if marker_path not in self._marker_paths:
            self._marker_paths.append(marker_path)
        self.refresh_list()
        self.markers_changed.emit(self._marker_paths)
        count = len(markers)
        suffix = "marker" if count == 1 else "markers"
        self.status_updated.emit(f"Imported {count} {suffix}: {marker_path.name}")

    def _export_gpx(self) -> None:
        if not self._marker_paths:
            return
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export markers to GPX",
            str(Path.home() / "markers.gpx"),
            "GPX (*.gpx);;All files (*)",
        )
        if path:
            self.gpx_export_save_requested.emit(path, self._marker_paths)

    def _remove_selected(self) -> None:
        if self.marker_list is None:
            return
        selected = self.marker_list.currentRow()
        if 0 <= selected < len(self._marker_paths):
            self._marker_paths.pop(selected)
            self.refresh_list()
            self.markers_changed.emit(self._marker_paths)

    def _fetch_poi(self) -> None:
        if self._poi_fetch_button is None or self._poi_dept_combo is None or self._poi_source_combo is None:
            return
        if self._poi_thread is not None and self._poi_thread.isRunning():
            return
        department = self._poi_dept_combo.currentData()
        source = self._poi_source_combo.currentData()
        self._poi_fetch_button.setEnabled(False)
        worker = PoiFetchWorker(department, [source])
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda recs: self._on_poi_finished(recs, source))
        worker.failed.connect(self._on_poi_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_poi_thread)
        self._poi_thread = thread
        thread.start()

    def _on_poi_finished(self, records: list[Any], source: str) -> None:
        if self._poi_fetch_button is not None:
            self._poi_fetch_button.setEnabled(True)
        if not records:
            return
        frame = poi_records_to_geodataframe(records)
        import tempfile
        safe_source = "".join(c if c.isalnum() else "-" for c in source)[:32]
        tmp_path = Path(tempfile.gettempdir()) / "karstlab-gui-projects" / "_poi" / f"{safe_source}.gpx"
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        to_gpx(frame, tmp_path)
        if tmp_path not in self._marker_paths:
            self._marker_paths.append(tmp_path)
        self.refresh_list()
        self.markers_changed.emit(self._marker_paths)

    def _on_poi_failed(self, message: str) -> None:
        if self._poi_fetch_button is not None:
            self._poi_fetch_button.setEnabled(True)

    def _clear_poi_thread(self) -> None:
        self._poi_thread = None

    def _on_placement_toggled(self, active: bool) -> None:
        self.place_on_map_toggled.emit(active)

    def set_gps_coordinate(self, lat: float, lon: float, name: str = "") -> None:
        """Set GPS coordinate field (called from map click)."""
        if self._gps_coord_edit is not None:
            self._gps_coord_edit.setText(f"{lat:.6f}, {lon:.6f}")
        if self._gps_name_edit is not None:
            if not name.strip():
                self._gps_name_edit.setText(f"Marker {lat:.4f},{lon:.4f}")
            else:
                self._gps_name_edit.setText(name)
            self._gps_name_edit.setFocus()

    def clear_gps_fields(self) -> None:
        """Clear GPS entry fields."""
        if self._gps_coord_edit is not None:
            self._gps_coord_edit.clear()
        if self._gps_name_edit is not None:
            self._gps_name_edit.clear()

    @staticmethod
    def _read_marker_points(path: Path) -> Any:
        suffix = path.suffix.lower().lstrip(".")
        if suffix == "gpx":
            return read_gpx_waypoints(path)
        if suffix == "kml":
            return read_kml_points(path)
        raise ValueError(f"Unsupported marker format: {suffix}")

    @staticmethod
    def _marker_list_label(path: Path, markers: Any) -> str:
        count = len(markers)
        suffix = "marker" if count == 1 else "markers"
        names: list[str] = []
        if "name" in markers:
            names = [str(name) for name in markers["name"].dropna().head(3).to_list()]
        name_preview = f": {', '.join(names)}" if names else ""
        return f"{path.name} ({count} {suffix}){name_preview}"


__all__ = ["MarkersTab", "PoiFetchWorker"]
