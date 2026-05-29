from __future__ import annotations

import builtins
import importlib
import os
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from karstlab.data.schemas import AnalysisParams, DepressionResult

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="session")
def qapp() -> Iterator[Any]:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["karstlab-tests"])
    yield app


@pytest.fixture(autouse=True)
def no_qwebengine(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    _block_webengine_import(monkeypatch)
    sys.modules.pop("karstlab.presentation.main_window", None)
    sys.modules.pop("karstlab.presentation.app", None)
    yield


@pytest.fixture
def main_window(qapp: Any) -> Iterator[Any]:
    from karstlab.presentation.app import MainWindow

    window = MainWindow()
    yield window
    window.close()
    qapp.processEvents()


def test_main_window_exposes_expected_tabs(main_window: Any) -> None:
    tabs = _find_single_widget(main_window, QtWidgets.QTabWidget)

    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "Tools",
        "Results",
        "Layers",
        "Markers",
        "Export",
    ]


def test_dem_path_setter_updates_state(main_window: Any, tmp_path: Path) -> None:
    dem_path = tmp_path / "input-dem.tif"

    _call_first_existing(
        main_window,
        ("set_dem_path", "setDemPath", "load_dem_path", "select_dem_path"),
        dem_path,
    )

    assert _window_has_path_state(main_window, dem_path)


def test_results_table_renders_top_depressions(main_window: Any) -> None:
    depressions = [
        _depression("doline-alpha", rank=1, max_depth_m=4.25, area_m2=125.0),
        _depression("doline-beta", rank=2, max_depth_m=2.5, area_m2=80.0),
    ]

    _show_results(main_window, depressions)

    table = _find_results_table(main_window)
    rendered_text = _table_text(table)
    assert "doline-alpha" in rendered_text
    assert "doline-beta" in rendered_text
    assert "4.25" in rendered_text


def test_missing_qwebengine_fallback_does_not_crash(
    monkeypatch: pytest.MonkeyPatch, qapp: Any
) -> None:
    _block_webengine_import(monkeypatch)
    sys.modules.pop("karstlab.presentation.main_window", None)
    sys.modules.pop("karstlab.presentation.app", None)

    app_module = importlib.import_module("karstlab.presentation.app")
    window = app_module.MainWindow()
    try:
        window.show()
        qapp.processEvents()
    finally:
        window.close()


def test_close_event_ignores_when_analysis_thread_keeps_running(
    monkeypatch: pytest.MonkeyPatch, main_window: Any
) -> None:
    warnings: list[str] = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QtWidgets.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda _parent, title, _message: warnings.append(title),
    )
    event = SimpleNamespace(accepted=False, ignored=False)
    event.accept = lambda: setattr(event, "accepted", True)
    event.ignore = lambda: setattr(event, "ignored", True)
    main_window._analysis_thread = SimpleNamespace(
        isRunning=lambda: True,
        requestInterruption=lambda: None,
        quit=lambda: None,
        wait=lambda _timeout: False,
    )

    main_window.closeEvent(event)

    assert event.ignored is True
    assert event.accepted is False
    assert warnings == ["Analysis still running"]


def test_analysis_worker_logs_failure(tmp_path: Path) -> None:
    from karstlab.presentation.main_window import AnalysisWorker

    messages: list[str] = []

    def failing_runner(_project: Any, _callback: Any) -> Any:
        raise RuntimeError("synthetic failure")

    worker = AnalysisWorker(
        dem_path=tmp_path / "dem.tif",
        project_base_dir=tmp_path,
        project_name="Failure Project",
        profile_id="generic",
        analysis_params=AnalysisParams(),
        runner=failing_runner,
    )
    worker.failed.connect(messages.append)

    worker.run()

    assert len(messages) == 1
    assert "synthetic failure" in messages[0]
    log_path = Path(messages[0].rsplit("Log: ", maxsplit=1)[1])
    assert log_path.exists()
    assert "RuntimeError: synthetic failure" in log_path.read_text(encoding="utf-8")


def test_progress_percent_parser_handles_edge_inputs() -> None:
    from karstlab.presentation.main_window import _progress_value

    assert _progress_value("%") == 10
    assert _progress_value("progress: %") == 10
    assert _progress_value("Operation: 75%") == 75


def test_layer_controls_update_state(main_window: Any) -> None:
    checkbox = main_window.layer_checkboxes["Contours"]
    slider = main_window.layer_sliders["Contours"]

    checkbox.setChecked(False)
    slider.setValue(35)

    assert main_window.layer_state["Contours"] == {"visible": False, "opacity": 35}


def test_marker_import_buttons_track_selected_files(
    monkeypatch: pytest.MonkeyPatch, main_window: Any, tmp_path: Path
) -> None:
    marker_path = tmp_path / "markers.gpx"
    marker_path.write_text("<gpx />", encoding="utf-8")
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(marker_path), "GPX files (*.gpx)"),
    )
    button = next(
        child
        for child in main_window.findChildren(QtWidgets.QPushButton)
        if child.text() == "Import GPX"
    )

    button.click()

    assert main_window.marker_paths == [marker_path]
    assert marker_path.name in main_window.statusBar().currentMessage()


def test_stylesheet_includes_phase4_polish_rules() -> None:
    from karstlab.presentation.main_window import _stylesheet

    qss = _stylesheet()
    assert "QSlider::handle:horizontal:hover" in qss
    assert "QScrollBar::handle:vertical:hover" in qss
    assert "QTabBar::tab:hover" in qss
    assert "QGroupBox::title" in qss


def _block_webengine_import(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def import_without_webengine(
        name: str,
        globals_: dict[str, Any] | None = None,
        locals_: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "PySide6.QtWebEngineWidgets":
            raise ImportError("Qt WebEngine intentionally unavailable in test")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", import_without_webengine)


def _call_first_existing(target: Any, names: Sequence[str], *args: Any) -> Any:
    for name in names:
        method = getattr(target, name, None)
        if callable(method):
            return method(*args)
    available = ", ".join(names)
    raise AssertionError(f"MainWindow does not expose any of: {available}")


def _show_results(window: Any, depressions: list[DepressionResult]) -> None:
    names = (
        "show_results",
        "set_results",
        "set_top_depressions",
        "render_top_depressions",
        "update_results",
        "display_results",
    )
    result = SimpleNamespace(top_depressions=depressions, depressions=depressions)
    errors: list[Exception] = []

    for name in names:
        method = getattr(window, name, None)
        if not callable(method):
            continue
        for payload in (depressions, result):
            try:
                method(payload)
                return
            except (AttributeError, TypeError) as exc:
                errors.append(exc)

    if errors:
        raise AssertionError(
            "MainWindow results method rejected depression payloads"
        ) from errors[-1]
    raise AssertionError(f"MainWindow does not expose any results renderer: {', '.join(names)}")


def _window_has_path_state(window: Any, dem_path: Path) -> bool:
    expected = str(dem_path)
    for name in ("dem_path", "dem_file", "current_dem_path", "input_dem_path"):
        if hasattr(window, name) and str(getattr(window, name)) == expected:
            return True

    for line_edit in window.findChildren(QtWidgets.QLineEdit):
        if line_edit.text() == expected:
            return True

    return False


def _find_single_widget(parent: Any, widget_type: type[Any]) -> Any:
    widgets = parent.findChildren(widget_type)
    if not widgets:
        raise AssertionError(f"Expected {widget_type.__name__} under MainWindow")
    return widgets[0]


def _find_results_table(window: Any) -> Any:
    for widget_type in (QtWidgets.QTableWidget, QtWidgets.QTableView):
        widgets = [
            widget
            for widget in window.findChildren(widget_type)
            if _table_row_count(widget) >= 2
        ]
        if widgets:
            return widgets[0]
    raise AssertionError("Expected a populated results table under MainWindow")


def _table_row_count(table: Any) -> int:
    if hasattr(table, "rowCount"):
        return int(table.rowCount())
    model = table.model()
    return int(model.rowCount()) if model is not None else 0


def _table_text(table: Any) -> str:
    if isinstance(table, QtWidgets.QTableWidget):
        values: list[str] = []
        for row in range(table.rowCount()):
            for column in range(table.columnCount()):
                item = table.item(row, column)
                if item is not None:
                    values.append(item.text())
        return "\n".join(values)

    model = table.model()
    if model is None:
        return ""

    values = []
    for row in range(model.rowCount()):
        for column in range(model.columnCount()):
            values.append(str(model.data(model.index(row, column)) or ""))
    return "\n".join(values)


def _depression(
    depression_id: str,
    *,
    rank: int,
    max_depth_m: float,
    area_m2: float,
) -> DepressionResult:
    return DepressionResult.model_validate(
        {
            "id": depression_id,
            "rank": rank,
            "max_depth_m": max_depth_m,
            "area_m2": area_m2,
            "centroid": {"lat": 44.1, "lon": 1.2},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [1.19, 44.09],
                        [1.21, 44.09],
                        [1.21, 44.11],
                        [1.19, 44.11],
                        [1.19, 44.09],
                    ]
                ],
            },
        }
    )
