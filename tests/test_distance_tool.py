from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="session")
def qapp() -> Iterator[Any]:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["karstlab-tests"])
    yield app


def test_tools_tab_distance_toggle_emits_signal(qapp: Any) -> None:
    from karstlab.presentation.tools_tab import ToolsTab

    tab = ToolsTab()
    emitted: list[bool] = []
    tab.distance_mode_toggled.connect(emitted.append)

    tab._distance_button.setChecked(True)
    tab._distance_button.setChecked(False)

    assert emitted == [True, False]


def test_tools_tab_set_distance_mode_is_idempotent(qapp: Any) -> None:
    from karstlab.presentation.tools_tab import ToolsTab

    tab = ToolsTab()
    emitted: list[bool] = []
    tab.distance_mode_toggled.connect(emitted.append)

    tab.set_distance_mode(True)
    tab.set_distance_mode(True)  # no re-emit when already active
    tab.set_distance_mode(False)

    assert emitted == [True, False]


def test_map_view_distance_methods_safe_without_webengine(qapp: Any) -> None:
    from karstlab.presentation.map_view import (
        _CLEAR_DISTANCE_JS,
        _DISTANCE_HANDLER_JS,
        MapView,
    )

    # Offscreen → QTextBrowser fallback, no web view; methods must be no-ops.
    view = MapView()
    assert view._web_view is None
    view.start_distance_mode()
    view.clear_distance_mode()

    # JS payloads carry the Leaflet distance + cleanup logic.
    assert "m.distance(" in _DISTANCE_HANDLER_JS
    assert "_kl_dist_active" in _DISTANCE_HANDLER_JS
    assert "off('click'" in _CLEAR_DISTANCE_JS


def test_markers_tab_brgm_overlay_emits_department(qapp: Any) -> None:
    from karstlab.presentation.markers_tab import MarkersTab

    tab = MarkersTab()
    emitted: list[str] = []
    tab.brgm_load_requested.connect(emitted.append)

    assert tab._poi_dept_combo is not None
    index = tab._poi_dept_combo.findData("06")
    assert index >= 0
    tab._poi_dept_combo.setCurrentIndex(index)
    tab._brgm_overlay_button.click()

    assert emitted == ["06"]


def test_map_view_inject_poi_layer_safe_without_webengine(qapp: Any) -> None:
    from karstlab.presentation.map_view import _INJECT_POI_JS, MapView

    view = MapView()
    assert view._web_view is None
    view.inject_poi_layer('{"type":"FeatureCollection","features":[]}')

    assert "L.geoJSON(" in _INJECT_POI_JS
    assert "__DATA__" in _INJECT_POI_JS


def test_tools_tab_profile_toggle_emits_signal(qapp: Any) -> None:
    from karstlab.presentation.tools_tab import ToolsTab

    tab = ToolsTab()
    emitted: list[bool] = []
    tab.profile_mode_toggled.connect(emitted.append)

    tab._profile_button.setChecked(True)
    tab._profile_button.setChecked(False)

    assert emitted == [True, False]


def test_map_view_profile_methods_safe_without_webengine(qapp: Any) -> None:
    from karstlab.presentation.map_view import (
        _CLEAR_PROFILE_JS,
        _PROFILE_HANDLER_JS,
        MapView,
    )

    view = MapView()
    assert view._web_view is None
    view.start_profile_mode()
    view.clear_profile_mode()

    assert "karstlab://profile" in _PROFILE_HANDLER_JS
    assert "_kl_prof_active" in _PROFILE_HANDLER_JS
    assert "off('click'" in _CLEAR_PROFILE_JS


def test_profile_dialog_builds_with_profile_arrays(qapp: Any) -> None:
    import numpy as np

    from karstlab.presentation.profile_dialog import ProfileDialog

    distances = np.linspace(0.0, 500.0, 32)
    elevations = np.linspace(250.0, 255.0, 32)
    elevations[5] = np.nan  # nodata gap must not crash rendering

    dialog = ProfileDialog(distances, elevations, (44.1, 1.2), (44.2, 1.3))
    assert dialog.windowTitle()


def test_brgm_overlay_worker_forwards_cache_dir(qapp: Any, monkeypatch: Any, tmp_path: Any) -> None:
    import karstlab.data.poi as poi
    from karstlab.presentation.main_window import _BrgmOverlayWorker

    captured: dict[str, Any] = {}

    def fake_fetch(
        department: str, *, cache_dir: Any = None, timeout: float = 10.0
    ) -> list[Any]:
        captured["department"] = department
        captured["cache_dir"] = cache_dir
        return []

    monkeypatch.setattr(poi, "fetch_brgm_cavites", fake_fetch)

    worker = _BrgmOverlayWorker("25", cache_dir=tmp_path)
    results: list[Any] = []
    worker.finished.connect(results.append)
    worker.run()

    assert captured == {"department": "25", "cache_dir": tmp_path}
    assert results == [[]]
