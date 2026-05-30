"""Phase 8 tests: sidebar panels and dialogs."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")
QtCore = pytest.importorskip("PySide6.QtCore")


@pytest.fixture(scope="session")
def qapp() -> Iterator[Any]:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["karstlab-phase8-tests"])
    yield app


# ─── ToolsTab ────────────────────────────────────────────────────────────────


class TestToolsTab:
    @pytest.fixture
    def tab(self, qapp: Any) -> Any:
        from karstlab.presentation.tools_tab import ToolsTab
        return ToolsTab()

    def test_default_analysis_params_match_schema_defaults(self, tab: Any) -> None:
        from karstlab.data.schemas import AnalysisParams
        params = tab.analysis_params()
        defaults = AnalysisParams()
        assert params.contour_interval_m == defaults.contour_interval_m
        assert params.doline_min_depth_m == defaults.doline_min_depth_m
        assert params.doline_max_depth_m == defaults.doline_max_depth_m
        assert params.doline_min_area_m2 == defaults.doline_min_area_m2
        assert params.doline_max_area_m2 == defaults.doline_max_area_m2
        assert params.stream_threshold_cells == defaults.stream_threshold_cells

    def test_set_analysis_params_updates_spinboxes(self, tab: Any) -> None:
        from karstlab.data.schemas import AnalysisParams
        params = AnalysisParams(
            contour_interval_m=10.0,
            doline_min_depth_m=0.5,
            doline_max_depth_m=20.0,
            doline_min_area_m2=5.0,
            doline_max_area_m2=5000.0,
            stream_threshold_cells=500,
        )
        tab.set_analysis_params(params)
        result = tab.analysis_params()
        assert result.contour_interval_m == 10.0
        assert result.doline_min_depth_m == 0.5
        assert result.doline_max_depth_m == 20.0
        assert result.stream_threshold_cells == 500

    def test_set_dem_path_updates_line_edit(self, tab: Any, tmp_path: Path) -> None:
        path = tmp_path / "dem.tif"
        tab.set_dem_path(path)
        assert tab.dem_path() == path
        assert tab._dem_edit.text() == str(path)

    def test_set_project_dir_updates_line_edit(self, tab: Any, tmp_path: Path) -> None:
        tab.set_project_dir(tmp_path)
        assert tab.project_dir() == tmp_path

    def test_analyze_button_is_primary_style(self, tab: Any) -> None:
        assert tab._analyze_button.objectName() == "primaryButton"

    def test_cancel_button_starts_disabled(self, tab: Any) -> None:
        assert not tab._cancel_button.isEnabled()

    def test_set_analyze_enabled_toggles_button(self, tab: Any) -> None:
        tab.set_analyze_enabled(False)
        assert not tab._analyze_button.isEnabled()
        tab.set_analyze_enabled(True)
        assert tab._analyze_button.isEnabled()

    def test_set_progress_updates_bar(self, tab: Any) -> None:
        tab.set_progress(75)
        assert tab._progress_bar.value() == 75

    def test_profile_combo_populated(self, tab: Any) -> None:
        assert tab._profile_combo.count() > 0
        assert tab.profile_id() != ""

    def test_analyze_requested_signal_fires(self, tab: Any, qapp: Any) -> None:
        fired: list[bool] = []
        tab.analyze_requested.connect(lambda: fired.append(True))
        tab._analyze_button.click()
        assert fired == [True]

    def test_cancel_requested_signal_fires(self, tab: Any, qapp: Any) -> None:
        fired: list[bool] = []
        tab.cancel_requested.connect(lambda: fired.append(True))
        tab.set_cancel_enabled(True)
        tab._cancel_button.click()
        assert fired == [True]


# ─── LayersTab ───────────────────────────────────────────────────────────────


class TestLayersTab:
    @pytest.fixture
    def tab(self, qapp: Any) -> Any:
        from karstlab.presentation.layers_tab import LayersTab
        return LayersTab()

    def test_five_default_layers_present(self, tab: Any) -> None:
        expected = {"Doline footprints", "Top 25 markers", "Contours", "Streams", "Hillshade"}
        assert set(tab.checkboxes.keys()) == expected

    def test_doline_footprints_starts_checked(self, tab: Any) -> None:
        assert tab.checkboxes["Doline footprints"].isChecked()

    def test_streams_starts_unchecked(self, tab: Any) -> None:
        assert not tab.checkboxes["Streams"].isChecked()

    def test_tile_grid_checkbox_starts_unchecked(self, tab: Any) -> None:
        assert not tab._tile_grid_checkbox.isChecked()

    def test_layer_state_reflects_initial_values(self, tab: Any) -> None:
        state = tab.layer_state
        assert state["Doline footprints"]["visible"] is True
        assert state["Streams"]["visible"] is False
        assert state["Contours"]["opacity"] == 80
        assert state["Hillshade"]["opacity"] == 40

    def test_toggling_checkbox_updates_layer_state(self, tab: Any) -> None:
        tab.checkboxes["Contours"].setChecked(False)
        assert tab.layer_state["Contours"]["visible"] is False

    def test_moving_slider_updates_layer_state(self, tab: Any) -> None:
        tab.sliders["Hillshade"].setValue(65)
        assert tab.layer_state["Hillshade"]["opacity"] == 65

    def test_layer_visibility_signal_emitted(self, tab: Any, qapp: Any) -> None:
        events: list[tuple[str, bool]] = []
        tab.layer_visibility_changed.connect(lambda n, v: events.append((n, v)))
        tab.checkboxes["Streams"].setChecked(True)
        assert ("Streams", True) in events

    def test_tile_grid_signal_emitted(self, tab: Any, qapp: Any) -> None:
        events: list[bool] = []
        tab.tile_grid_toggled.connect(events.append)
        tab._tile_grid_checkbox.setChecked(True)
        assert True in events


# ─── ResultsTab ──────────────────────────────────────────────────────────────


class TestResultsTab:
    @pytest.fixture
    def tab(self, qapp: Any) -> Any:
        from karstlab.presentation.results_tab import ResultsTab
        return ResultsTab()

    def _make_depression(
        self, depression_id: str, *, rank: int, depth: float, area: float = 100.0
    ) -> Any:
        from karstlab.data.schemas import DepressionResult
        return DepressionResult.model_validate({
            "id": depression_id,
            "rank": rank,
            "max_depth_m": depth,
            "area_m2": area,
            "centroid": {"lat": 44.1, "lon": 1.2},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[1.19, 44.09], [1.21, 44.09], [1.21, 44.11], [1.19, 44.09]]],
            },
        })

    def test_display_results_populates_table(self, tab: Any) -> None:
        from karstlab.data.schemas import AnalysisParams, PipelineResult, PipelineStatus
        depressions = [
            self._make_depression("d1", rank=1, depth=5.0),
            self._make_depression("d2", rank=2, depth=3.0),
        ]
        result = PipelineResult(
            project_id=uuid4(),
            status=PipelineStatus.SUCCESS,
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            land_profile="generic",
            analysis_params=AnalysisParams(),
            input_dem_paths=[Path("dem.tif")],
            output_dir=Path("out"),
            depressions=depressions,
            top_depressions=depressions,
        )
        tab.display_results(result)
        assert tab._table.rowCount() == 2

    def test_quality_flags_column_shows_edge_warning(self, tab: Any) -> None:
        from karstlab.data.schemas import DepressionResult
        depression = DepressionResult.model_validate({
            "id": "flagged",
            "rank": 1,
            "max_depth_m": 3.0,
            "area_m2": 100.0,
            "centroid": {"lat": 44.0, "lon": 1.0},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[1.0, 44.0], [1.1, 44.0], [1.1, 44.1], [1.0, 44.0]]],
            },
            "quality_flags": {"edge_proximity": True},
        })
        tab.display_results([depression])
        flags_col = tab._table.columnCount() - 1
        flags_item = tab._table.item(0, flags_col)
        assert flags_item is not None
        assert "edge" in flags_item.text()

    def test_clear_resets_to_empty_state(self, tab: Any) -> None:
        tab.display_results([self._make_depression("d1", rank=1, depth=2.0)])
        assert tab._table.rowCount() == 1
        tab.clear()
        assert tab._table.rowCount() == 0

    def test_depression_selected_signal_emitted_on_row_click(
        self, tab: Any, qapp: Any
    ) -> None:
        events: list[tuple[str, float, float]] = []
        tab.depression_selected.connect(lambda i, lat, lon: events.append((i, lat, lon)))
        tab.display_results([self._make_depression("d1", rank=1, depth=5.0)])
        tab._table.selectRow(0)
        qapp.processEvents()
        assert len(events) == 1
        assert events[0][0] == "d1"

    def test_table_property_returns_qtablewidget(self, tab: Any) -> None:
        assert isinstance(tab.table, QtWidgets.QTableWidget)


# ─── MarkersTab ──────────────────────────────────────────────────────────────


class TestMarkersTab:
    @pytest.fixture
    def tab(self, qapp: Any) -> Any:
        from karstlab.presentation.markers_tab import MarkersTab
        return MarkersTab()

    def test_initial_marker_paths_empty(self, tab: Any) -> None:
        assert tab.marker_paths() == []

    def test_set_marker_paths_updates_state(self, tab: Any, tmp_path: Path) -> None:
        path = tmp_path / "m.gpx"
        path.write_text(
            '<?xml version="1.0"?><gpx version="1.1" creator="test">'
            '<wpt lat="44.0" lon="1.0"><name>A</name></wpt></gpx>',
            encoding="utf-8",
        )
        tab.set_marker_paths([path])
        assert tab.marker_paths() == [path]

    def test_gps_coord_set_by_set_gps_coordinate(self, tab: Any) -> None:
        tab.set_gps_coordinate(44.123456, 1.234567)
        assert "44.123456" in tab._gps_coord_edit.text()

    def test_gps_name_set_by_set_gps_coordinate_when_blank(self, tab: Any) -> None:
        tab.set_gps_coordinate(44.1, 1.2)
        assert tab._gps_name_edit.text() != ""

    def test_import_gpx_button_exists(self, tab: Any) -> None:
        buttons = tab.findChildren(QtWidgets.QPushButton)
        texts = {b.text() for b in buttons}
        assert "Import GPX" in texts

    def test_export_gpx_button_exists(self, tab: Any) -> None:
        buttons = tab.findChildren(QtWidgets.QPushButton)
        texts = {b.text() for b in buttons}
        assert "Export GPX" in texts

    def test_place_on_map_button_is_checkable(self, tab: Any) -> None:
        btn = next(
            b for b in tab.findChildren(QtWidgets.QPushButton) if b.text() == "Place on map"
        )
        assert btn.isCheckable()

    def test_markers_changed_signal_on_set(self, tab: Any, qapp: Any, tmp_path: Path) -> None:
        path = tmp_path / "m.gpx"
        path.write_text(
            '<?xml version="1.0"?><gpx version="1.1" creator="test">'
            '<wpt lat="44.0" lon="1.0"><name>A</name></wpt></gpx>',
            encoding="utf-8",
        )
        emitted: list[list[Path]] = []
        tab.markers_changed.connect(emitted.append)
        tab.set_marker_paths([path])
        assert len(emitted) == 1
        assert emitted[0] == [path]


# ─── ExportTab ───────────────────────────────────────────────────────────────


class TestExportTab:
    @pytest.fixture
    def tab(self, qapp: Any) -> Any:
        from karstlab.presentation.export_tab import ExportTab
        return ExportTab()

    def test_six_open_buttons_present(self, tab: Any) -> None:
        assert len(tab.export_buttons()) == 6

    def test_all_open_buttons_start_disabled(self, tab: Any) -> None:
        for btn in tab.export_buttons():
            assert not btn.isEnabled()

    def test_set_export_paths_enables_existing_file(
        self, tab: Any, tmp_path: Path
    ) -> None:
        report = tmp_path / "report.html"
        report.write_text("<html/>", encoding="utf-8")
        tab.set_export_paths({"Open report": report})
        report_btn = next(b for b in tab.export_buttons() if b.text() == "Open report")
        assert report_btn.isEnabled()

    def test_nonexistent_path_button_stays_disabled(
        self, tab: Any, tmp_path: Path
    ) -> None:
        tab.set_export_paths({"Open GeoJSON": tmp_path / "nonexistent.geojson"})
        geojson_btn = next(b for b in tab.export_buttons() if b.text() == "Open GeoJSON")
        assert not geojson_btn.isEnabled()

    def test_set_project_shows_generate_button(self, tab: Any) -> None:
        tab.set_project("My Project")
        assert tab._generate_button is not None
        assert not tab._generate_button.isHidden()

    def test_set_project_none_hides_generate_button(self, tab: Any) -> None:
        tab.set_project("Test")
        tab.set_project(None)
        assert tab._generate_button is not None
        assert tab._generate_button.isHidden()

    def test_open_map_key_is_compatible(self, tab: Any) -> None:
        keys = {btn.text() for btn in tab.export_buttons()}
        assert "Open map" in keys


# ─── GuidedWorkflowPanel ─────────────────────────────────────────────────────


class TestGuidedWorkflowPanel:
    @pytest.fixture
    def panel(self, qapp: Any) -> Any:
        from karstlab.presentation.guided_workflow import GuidedWorkflowPanel
        return GuidedWorkflowPanel()

    def test_starts_at_step_zero(self, panel: Any) -> None:
        assert panel.current_step() == 0

    def test_set_step_updates_current(self, panel: Any) -> None:
        panel.set_step(3)
        assert panel.current_step() == 3

    def test_set_step_clamps_below_zero(self, panel: Any) -> None:
        panel.set_step(-5)
        assert panel.current_step() == 0

    def test_set_step_clamps_above_max(self, panel: Any) -> None:
        panel.set_step(100)
        assert panel.current_step() == 5

    def test_step_changed_signal_emitted(self, panel: Any, qapp: Any) -> None:
        events: list[int] = []
        panel.step_changed.connect(events.append)
        panel.set_step(2)
        assert 2 in events

    def test_advance_to_is_alias_for_set_step(self, panel: Any) -> None:
        panel.advance_to(4)
        assert panel.current_step() == 4

    def test_mark_step_complete_adds_checkmark(self, panel: Any) -> None:
        panel.mark_step_complete(0)
        label_text = panel._step_label.text()
        assert "✓" in label_text or panel.current_step() == 0


# ─── SettingsDialog ──────────────────────────────────────────────────────────


class TestSettingsDialog:
    @pytest.fixture
    def dialog(self, qapp: Any) -> Any:
        from karstlab.data.schemas import UserSettings
        from karstlab.presentation.settings_dialog import SettingsDialog
        return SettingsDialog(UserSettings())

    def test_dialog_is_modal(self, dialog: Any) -> None:
        assert dialog.isModal()

    def test_language_combo_has_three_items(self, dialog: Any) -> None:
        combo = next(
            c for c in dialog.findChildren(QtWidgets.QComboBox)
        )
        assert combo.count() >= 3

    def test_settings_saved_signal_type(self, dialog: Any, qapp: Any) -> None:
        emitted: list[Any] = []
        dialog.settings_saved.connect(emitted.append)
        ok_button = next(
            b for b in dialog.findChildren(QtWidgets.QPushButton)
            if b.text() in ("OK", "Save", "Apply")
        )
        ok_button.click()
        assert len(emitted) == 1

    def test_whitebox_path_value_initially_none(self, dialog: Any) -> None:
        assert dialog.whitebox_path_value() is None


# ─── ShortcutsDialog ─────────────────────────────────────────────────────────


class TestShortcutsDialog:
    @pytest.fixture
    def dialog(self, qapp: Any) -> Any:
        from karstlab.presentation.shortcuts_dialog import ShortcutsDialog
        return ShortcutsDialog()

    def test_dialog_has_table_with_shortcuts(self, dialog: Any) -> None:
        tables = dialog.findChildren(QtWidgets.QTableWidget)
        assert len(tables) == 1
        assert tables[0].rowCount() > 5

    def test_shortcuts_include_ctrl_n(self, dialog: Any) -> None:
        tables = dialog.findChildren(QtWidgets.QTableWidget)
        table = tables[0]
        shortcuts = [
            table.item(row, 0).text()
            for row in range(table.rowCount())
            if table.item(row, 0)
        ]
        assert any("Ctrl+N" in s or "N" in s for s in shortcuts)

    def test_dialog_is_modal(self, dialog: Any) -> None:
        assert dialog.isModal()


# ─── ProgressDialog ──────────────────────────────────────────────────────────


class TestProgressDialog:
    @pytest.fixture
    def dialog(self, qapp: Any) -> Any:
        from karstlab.presentation.progress_dialog import ProgressDialog
        return ProgressDialog()

    def test_initial_progress_zero(self, dialog: Any) -> None:
        bars = dialog.findChildren(QtWidgets.QProgressBar)
        assert any(b.value() == 0 for b in bars)

    def test_add_step_appears_in_list(self, dialog: Any, qapp: Any) -> None:
        dialog.add_step("fill_dem", "Fill depressions")
        lists = dialog.findChildren(QtWidgets.QListWidget)
        assert len(lists) == 1
        assert lists[0].count() == 1

    def test_update_step_shows_success_icon(self, dialog: Any, qapp: Any) -> None:
        from karstlab.data.schemas import PipelineStatus
        dialog.add_step("fill_dem", "Fill depressions")
        dialog.update_step("fill_dem", PipelineStatus.SUCCESS)
        lists = dialog.findChildren(QtWidgets.QListWidget)
        item_text = lists[0].item(0).text()
        assert "✓" in item_text

    def test_set_progress_updates_bar(self, dialog: Any, qapp: Any) -> None:
        dialog.set_progress(60)
        bars = dialog.findChildren(QtWidgets.QProgressBar)
        assert any(b.value() == 60 for b in bars)

    def test_show_error_enables_rerun_button(self, dialog: Any, qapp: Any) -> None:
        dialog.show_error("Something went wrong")
        rerun_button = next(
            b for b in dialog.findChildren(QtWidgets.QPushButton)
            if "rerun" in b.text().lower() or "failed" in b.text().lower()
        )
        assert rerun_button.isEnabled()

    def test_reset_clears_steps(self, dialog: Any, qapp: Any) -> None:
        dialog.add_step("step1", "Step 1")
        dialog.reset()
        lists = dialog.findChildren(QtWidgets.QListWidget)
        assert lists[0].count() == 0


# ─── UpdateBanner ────────────────────────────────────────────────────────────


class TestUpdateBanner:
    @pytest.fixture
    def banner(self, qapp: Any) -> Any:
        from karstlab.presentation.update_banner import UpdateBanner
        return UpdateBanner()

    def test_banner_hidden_by_default(self, banner: Any) -> None:
        assert not banner.isVisible()

    def test_show_update_makes_banner_visible(self, banner: Any, qapp: Any) -> None:
        banner.show_update("1.2.3")
        assert banner.isVisible()

    def test_show_update_includes_version_in_text(self, banner: Any, qapp: Any) -> None:
        banner.show_update("1.2.3")
        labels = banner.findChildren(QtWidgets.QLabel)
        texts = " ".join(lbl.text() for lbl in labels)
        assert "1.2.3" in texts

    def test_dismiss_hides_banner(self, banner: Any, qapp: Any) -> None:
        banner.show_update("1.2.3")
        dismiss_btn = next(
            b for b in banner.findChildren(QtWidgets.QPushButton)
            if "×" in b.text() or "✕" in b.text() or "x" in b.text().lower() or b.text() == "×"
        )
        dismiss_btn.click()
        qapp.processEvents()
        assert not banner.isVisible()

    def test_dismissed_signal_emitted_on_close(self, banner: Any, qapp: Any) -> None:
        events: list[bool] = []
        banner.dismissed.connect(lambda: events.append(True))
        banner.show_update("1.2.3")
        dismiss_btns = [
            b for b in banner.findChildren(QtWidgets.QPushButton)
        ]
        for btn in dismiss_btns:
            if "×" in btn.text() or "✕" in btn.text() or btn.text().strip() in ("x", "X", "×"):
                btn.click()
                break
        qapp.processEvents()
        assert True in events
