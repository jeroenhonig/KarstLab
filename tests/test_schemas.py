from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from karstlab.data.schemas import (
    AnalysisParams,
    DepressionResult,
    LandProfile,
    LayerConfig,
    PipelineResult,
    PipelineStatus,
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
        cache_dir=Path("/tmp/trou-du-vent/cache"),
    )

    assert project.schema_version == "1.0"
    assert project.land_profile_id == "generic"
    assert project.input_dir.name == "input"


def test_pipeline_result_limits_top_depressions_to_25() -> None:
    with pytest.raises(ValidationError):
        PipelineResult(
            project_id=uuid4(),
            status=PipelineStatus.SUCCESS,
            params=AnalysisParams(),
            input_dem_paths=[Path("input/dem.tif")],
            output_dir=Path("output"),
            top_depressions=[minimal_depression(rank=i + 1) for i in range(26)],
        )


def test_failed_pipeline_requires_failed_step() -> None:
    with pytest.raises(ValidationError, match="failed pipeline"):
        PipelineResult(
            project_id=uuid4(),
            status=PipelineStatus.FAILED,
            params=AnalysisParams(),
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
        created_at=timestamp,
        updated_at=timestamp,
        project_dir=Path("/tmp/aven-test"),
        input_dir=Path("/tmp/aven-test/input"),
        output_dir=Path("/tmp/aven-test/output"),
        export_dir=Path("/tmp/aven-test/export"),
        cache_dir=Path("/tmp/aven-test/cache"),
    )

    assert project.created_at == timestamp
