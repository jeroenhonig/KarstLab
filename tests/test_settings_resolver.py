from __future__ import annotations

from karstlab.data.land_profiles import load_land_profile
from karstlab.data.project_io import create_project
from karstlab.data.schemas import AnalysisParams, UserSettings
from karstlab.data.settings_resolver import resolve_analysis_params


def test_returns_defaults_when_no_sources_provided() -> None:
    result = resolve_analysis_params()
    assert result == AnalysisParams()


def test_land_profile_defaults_override_built_in_defaults() -> None:
    profile = load_land_profile("generic")
    profile_with_custom = profile.model_copy(
        update={"analysis_defaults": AnalysisParams(contour_interval_m=2.5)}
    )
    result = resolve_analysis_params(land_profile=profile_with_custom)
    assert result.contour_interval_m == 2.5


def test_user_settings_overrides_land_profile() -> None:
    profile = load_land_profile("generic")
    profile_with_10 = profile.model_copy(
        update={"analysis_defaults": AnalysisParams(contour_interval_m=10.0)}
    )
    user = UserSettings(analysis_params=AnalysisParams(contour_interval_m=3.0))
    result = resolve_analysis_params(user_settings=user, land_profile=profile_with_10)
    assert result.contour_interval_m == 3.0


def test_project_params_override_user_settings(tmp_path) -> None:  # type: ignore[no-untyped-def]
    profile = load_land_profile("generic")
    project = create_project(
        base_dir=tmp_path,
        name="test",
        land_profile="generic",
        crs_analysis="EPSG:4326",
        analysis_params=AnalysisParams(contour_interval_m=7.0),
    )
    user = UserSettings(analysis_params=AnalysisParams(contour_interval_m=3.0))
    result = resolve_analysis_params(project=project, user_settings=user, land_profile=profile)
    assert result.contour_interval_m == 7.0


def test_ui_overrides_take_highest_priority(tmp_path) -> None:  # type: ignore[no-untyped-def]
    profile = load_land_profile("generic")
    project = create_project(
        base_dir=tmp_path,
        name="test",
        land_profile="generic",
        crs_analysis="EPSG:4326",
        analysis_params=AnalysisParams(contour_interval_m=7.0),
    )
    result = resolve_analysis_params(
        ui_overrides={"contour_interval_m": 1.0},
        project=project,
        land_profile=profile,
    )
    assert result.contour_interval_m == 1.0


def test_partial_ui_overrides_use_lower_levels_for_other_fields(tmp_path) -> None:  # type: ignore[no-untyped-def]
    project = create_project(
        base_dir=tmp_path,
        name="test",
        land_profile="generic",
        crs_analysis="EPSG:4326",
        analysis_params=AnalysisParams(stream_threshold_cells=500),
    )
    result = resolve_analysis_params(
        ui_overrides={"contour_interval_m": 1.0},
        project=project,
    )
    assert result.contour_interval_m == 1.0
    assert result.stream_threshold_cells == 500


def test_result_is_valid_analysis_params() -> None:
    result = resolve_analysis_params(
        ui_overrides={"contour_interval_m": 5.0},
        user_settings=UserSettings(analysis_params=AnalysisParams(doline_min_depth_m=0.5)),
    )
    assert isinstance(result, AnalysisParams)
    assert result.contour_interval_m == 5.0
    assert result.doline_min_depth_m == 0.5
