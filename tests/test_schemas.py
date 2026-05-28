from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from karstlab.data.schemas import (
    AnalysisParams,
    BoundingBox,
    DepressionResult,
    LandProfile,
    LayerConfig,
    PipelineResult,
    PipelineStatus,
    PipelineStepResult,
    ProjectFile,
    UserSettings,
)


def minimal_land_profile() -> LandProfile:
    return LandProfile.model_validate(
        {
            "id": "fr",
            "version": "1.0.0",
            "name": {"en": "France", "nl": "Frankrijk", "fr": "France"},
            "default_crs": "EPSG:2154",
            "common_crs": ["EPSG:2154", "EPSG:32631"],
            "dem_sources": [
                {
                    "name": "IGN LiDAR HD MNT",
                    "url": "https://geoservices.ign.fr/lidarhd",
                    "description": {"en": "French bare-earth DEM"},
                    "resolution_m": 1.0,
                }
            ],
            "map_layers": {
                "base": [
                    {
                        "name": "OpenStreetMap",
                        "type": "tile",
                        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                    }
                ],
                "overlays": [
                    {
                        "name": "Geology",
                        "type": "wms",
                        "url": "https://example.com/wms",
                        "layer": "geology",
                        "opacity": 0.5,
                    }
                ],
            },
            "poi_sources": [
                {
                    "name": "BRGM Cavites",
                    "type": "brgm_cavites",
                    "url": "https://georisques.gouv.fr/api/v1/cavites",
                    "departmental": True,
                }
            ],
            "analysis_defaults": {
                "contour_interval_m": 5.0,
                "stream_threshold_cells": 1000,
                "doline_min_depth_m": 0.25,
                "doline_max_depth_m": 40.0,
                "doline_min_area_m2": 1.0,
                "doline_max_area_m2": 60000.0,
            },
        }
    )


def minimal_depression(rank: int = 1) -> DepressionResult:
    return DepressionResult.model_validate(
        {
            "id": f"doline-{rank}",
            "rank": rank,
            "max_depth_m": 4.2,
            "area_m2": 120.0,
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


def test_analysis_params_defaults_match_french_aris_compatible_profile() -> None:
    params = AnalysisParams()

    assert params.contour_interval_m == 5.0
    assert params.stream_threshold_cells == 1000
    assert params.doline_min_depth_m == 0.25
    assert params.doline_max_depth_m == 40.0
    assert params.doline_min_area_m2 == 1.0
    assert params.doline_max_area_m2 == 60000.0


def test_analysis_params_reject_invalid_ranges() -> None:
    with pytest.raises(ValidationError, match="doline_min_depth_m"):
        AnalysisParams(doline_min_depth_m=10.0, doline_max_depth_m=2.0)

    with pytest.raises(ValidationError, match="doline_min_area_m2"):
        AnalysisParams(doline_min_area_m2=100.0, doline_max_area_m2=25.0)


def test_land_profile_validates_required_defaults_and_layers() -> None:
    profile = minimal_land_profile()

    assert profile.id == "fr"
    assert profile.default_crs == "EPSG:2154"
    assert profile.map_layers.base[0].name == "OpenStreetMap"
    assert profile.poi_sources[0].departmental is True


def test_land_profile_requires_default_crs_in_common_crs() -> None:
    data = minimal_land_profile().model_dump(mode="json")
    data["default_crs"] = "EPSG:9999"

    with pytest.raises(ValidationError, match="default_crs"):
        LandProfile.model_validate(data)


def test_wms_and_wmts_layers_require_layer_name() -> None:
    with pytest.raises(ValidationError, match="layer name"):
        LayerConfig.model_validate(
            {
                "name": "Broken WMS",
                "type": "wms",
                "url": "https://example.com/wms",
            }
        )


def test_static_poi_sources_require_path() -> None:
    data = minimal_land_profile().model_dump(mode="json")
    data["poi_sources"] = [{"name": "Known caves", "type": "geojson"}]

    with pytest.raises(ValidationError, match="path"):
        LandProfile.model_validate(data)


def test_project_file_contains_required_directories() -> None:
    project = ProjectFile(
        name="Trou du Vent",
        slug="trou-du-vent",
        project_dir=Path("/tmp/trou-du-vent"),
        input_dir=Path("/tmp/trou-du-vent/input"),
        output_dir=Path("/tmp/trou-du-vent/output"),
        export_dir=Path("/tmp/trou-du-vent/export"),
        map_dir=Path("/tmp/trou-du-vent/map"),
        cache_dir=Path("/tmp/trou-du-vent/cache"),
        crs_analysis="EPSG:2154",
    )

    assert project.schema_version == "1.0.0"
    assert project.pipeline_version == "1.0.0"
    assert project.land_profile == "generic"
    assert project.crs_display == "EPSG:4326"
    assert project.input_dir.name == "input"
    assert project.map_dir.name == "map"


def test_pipeline_result_limits_top_depressions_to_25() -> None:
    with pytest.raises(ValidationError):
        PipelineResult(
            project_id=uuid4(),
            status=PipelineStatus.SUCCESS,
            land_profile="fr",
            analysis_params=AnalysisParams(),
            input_dem_paths=[Path("input/dem.tif")],
            output_dir=Path("output"),
            top_depressions=[minimal_depression(rank=i + 1) for i in range(26)],
        )


def test_failed_pipeline_requires_failed_step() -> None:
    with pytest.raises(ValidationError, match="failed pipeline"):
        PipelineResult(
            project_id=uuid4(),
            status=PipelineStatus.FAILED,
            land_profile="fr",
            analysis_params=AnalysisParams(),
            input_dem_paths=[Path("input/dem.tif")],
            output_dir=Path("output"),
        )


def test_depression_geometry_requires_geojson_shape() -> None:
    data = minimal_depression().model_dump(mode="json")
    data["geometry"] = {"type": "Triangle", "coordinates": []}

    with pytest.raises(ValidationError, match="geometry.type"):
        DepressionResult.model_validate(data)


def test_user_settings_and_json_schemas_are_exportable() -> None:
    settings_schema = UserSettings.model_json_schema()
    profile_schema = LandProfile.model_json_schema()
    project_schema = ProjectFile.model_json_schema()

    assert settings_schema["title"] == "UserSettings"
    assert profile_schema["title"] == "LandProfile"
    assert project_schema["title"] == "ProjectFile"


def test_datetime_fields_accept_timezone_aware_values() -> None:
    timestamp = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    project = ProjectFile(
        name="Aven Test",
        slug="aven-test",
        created=timestamp,
        modified=timestamp,
        project_dir=Path("/tmp/aven-test"),
        input_dir=Path("/tmp/aven-test/input"),
        output_dir=Path("/tmp/aven-test/output"),
        export_dir=Path("/tmp/aven-test/export"),
        map_dir=Path("/tmp/aven-test/map"),
        cache_dir=Path("/tmp/aven-test/cache"),
        crs_analysis="EPSG:2154",
    )

    assert project.created == timestamp


def test_strict_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AnalysisParams.model_validate({"contour_interval_m": 5.0, "unknown": True})


def test_pipeline_step_failed_status_requires_error_message() -> None:
    with pytest.raises(ValidationError, match="failed steps require error_message"):
        PipelineStepResult(step_id="fill_dem", status=PipelineStatus.FAILED)


def test_pipeline_step_accepts_completed_status_and_warnings() -> None:
    step = PipelineStepResult(
        step_id="fill_dem",
        status=PipelineStatus.COMPLETED,
        warnings=["DEM contains edge artifacts"],
    )

    assert step.status == PipelineStatus.COMPLETED
    assert step.warnings == ["DEM contains edge artifacts"]


def test_project_file_rejects_invalid_slug_patterns() -> None:
    with pytest.raises(ValidationError):
        ProjectFile(
            name="Invalid",
            slug="Has Spaces",
            project_dir=Path("/tmp/invalid"),
            input_dir=Path("/tmp/invalid/input"),
            output_dir=Path("/tmp/invalid/output"),
            export_dir=Path("/tmp/invalid/export"),
            map_dir=Path("/tmp/invalid/map"),
            cache_dir=Path("/tmp/invalid/cache"),
            crs_analysis="EPSG:2154",
        )


def test_bounding_box_rejects_invalid_extent() -> None:
    with pytest.raises(ValidationError, match="min_x"):
        BoundingBox(min_x=10.0, min_y=0.0, max_x=5.0, max_y=1.0, crs="EPSG:2154")


def test_remote_poi_sources_require_url() -> None:
    data = minimal_land_profile().model_dump(mode="json")
    data["poi_sources"] = [{"name": "Remote caves", "type": "wfs"}]

    with pytest.raises(ValidationError, match="url"):
        LandProfile.model_validate(data)


def test_round_trip_json_serialization_for_persisted_contracts() -> None:
    project = ProjectFile(
        name="Trou du Vent",
        slug="trou-du-vent",
        project_dir=Path("/tmp/trou-du-vent"),
        input_dir=Path("/tmp/trou-du-vent/input"),
        output_dir=Path("/tmp/trou-du-vent/output"),
        export_dir=Path("/tmp/trou-du-vent/export"),
        map_dir=Path("/tmp/trou-du-vent/map"),
        cache_dir=Path("/tmp/trou-du-vent/cache"),
        crs_analysis="EPSG:2154",
    )
    settings = UserSettings(
        land_profile="fr",
        crs_override="EPSG:2154",
        last_project_dir=Path("/tmp"),
    )
    profile = minimal_land_profile()

    assert ProjectFile.model_validate(project.model_dump(mode="json")) == project
    assert UserSettings.model_validate(settings.model_dump(mode="json")) == settings
    assert LandProfile.model_validate(profile.model_dump(mode="json")) == profile


def test_user_settings_recent_projects_limit() -> None:
    with pytest.raises(ValidationError):
        UserSettings(recent_projects=[Path(f"/tmp/project-{index}") for index in range(11)])
