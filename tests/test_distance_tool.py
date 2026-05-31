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
