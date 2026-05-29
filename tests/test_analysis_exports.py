from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import gpxpy
import pytest

from karstlab.data.analysis_exports import (
    EXPORT_SCHEMA_VERSION,
    build_statistics,
    depressions_to_geodataframe,
    write_statistics,
    write_top25_vector_exports,
)
from karstlab.data.schemas import (
    AnalysisParams,
    DepressionQualityFlags,
    DepressionResult,
    DepthConfidence,
    PipelineResult,
    PipelineStatus,
)


def depression(
    rank: int | None,
    *,
    identifier: str | None = None,
    depth: float = 4.2,
    area: float = 120.0,
    edge_proximity: bool = False,
    depth_confidence: DepthConfidence = DepthConfidence.MEDIUM,
) -> DepressionResult:
    value = rank or 99
    return DepressionResult.model_validate(
        {
            "id": identifier or f"doline-{value}",
            "rank": rank,
            "max_depth_m": depth,
            "area_m2": area,
            "centroid": {"lat": 44.0 + value / 1000, "lon": 1.0 + value / 1000},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [1.0, 44.0],
                        [1.01, 44.0],
                        [1.01, 44.01],
                        [1.0, 44.01],
                        [1.0, 44.0],
                    ]
                ],
            },
            "quality_flags": DepressionQualityFlags(
                edge_proximity=edge_proximity,
                depth_confidence=depth_confidence,
            ),
        }
    )


def pipeline_result(
    depressions: list[DepressionResult],
    *,
    top_depressions: list[DepressionResult] | None = None,
) -> PipelineResult:
    return PipelineResult(
        project_id=uuid4(),
        status=PipelineStatus.SUCCESS,
        land_profile="fr",
        analysis_params=AnalysisParams(contour_interval_m=10.0),
        input_dem_paths=[Path("input/dem.tif")],
        output_dir=Path("output"),
        depressions=depressions,
        top_depressions=top_depressions or [],
        provenance={"pipeline": "unit-test", "operator": "pipeline"},
    )


def test_build_statistics_uses_pipeline_params_counts_top25_and_provenance() -> None:
    result = pipeline_result(
        [
            depression(2, edge_proximity=True, depth_confidence=DepthConfidence.HIGH),
            depression(1, depth_confidence=DepthConfidence.LOW),
            depression(None, identifier="unranked"),
        ]
    )

    payload = build_statistics(result, provenance={"operator": "override", "run_id": "abc"})

    assert payload["schema_version"] == EXPORT_SCHEMA_VERSION
    assert payload["counts"]["depressions"] == 3
    assert payload["counts"]["ranked_depressions"] == 2
    assert payload["counts"]["top25"] == 3
    assert payload["counts"]["quality_flags"]["edge_proximity"] == 1
    assert payload["counts"]["quality_flags"]["depth_confidence"] == {
        "low": 1,
        "medium": 1,
        "high": 1,
    }
    assert [item["id"] for item in payload["top25"]] == ["doline-1", "doline-2", "unranked"]
    assert payload["params"]["contour_interval_m"] == 10.0
    assert payload["provenance"] == {
        "pipeline": "unit-test",
        "operator": "override",
        "run_id": "abc",
    }


def test_build_statistics_prefers_pipeline_top_depressions() -> None:
    result = pipeline_result(
        [depression(1), depression(2)],
        top_depressions=[depression(2)],
    )

    payload = build_statistics(result)

    assert payload["counts"]["depressions"] == 2
    assert payload["counts"]["top25"] == 1
    assert [item["id"] for item in payload["top25"]] == ["doline-2"]


def test_sequence_exports_require_analysis_params() -> None:
    with pytest.raises(ValueError, match="analysis_params"):
        build_statistics([depression(1)])


def test_write_statistics_uses_stable_json(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "statistics.json"
    result = pipeline_result([depression(1)])

    output = write_statistics(result, path)

    assert output == path
    assert path.read_text(encoding="utf-8").endswith("\n")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["top25"][0]["name"] == "Doline 1"


def test_depressions_to_geodataframe_supports_footprints_and_centroids() -> None:
    item = depression(1)

    footprints = depressions_to_geodataframe([item])
    centroids = depressions_to_geodataframe([item], geometry_mode="centroid")

    assert footprints.crs == "EPSG:4326"
    assert footprints.geometry.iloc[0].geom_type == "Polygon"
    assert centroids.geometry.iloc[0].geom_type == "Point"
    assert centroids.geometry.iloc[0].x == item.centroid.lon
    assert centroids.geometry.iloc[0].y == item.centroid.lat


def test_depressions_to_geodataframe_handles_empty_results() -> None:
    frame = depressions_to_geodataframe([])

    assert frame.empty
    assert frame.crs == "EPSG:4326"
    assert frame.geometry.name == "geometry"


def test_write_top25_vector_exports_writes_geojson_kml_and_centroid_gpx(tmp_path) -> None:  # type: ignore[no-untyped-def]
    result = pipeline_result([depression(1), depression(2)])

    paths = write_top25_vector_exports(
        result,
        geojson_path=tmp_path / "top25.geojson",
        kml_path=tmp_path / "top25.kml",
        gpx_path=tmp_path / "top25.gpx",
    )

    geojson_payload = json.loads(paths.geojson.read_text(encoding="utf-8"))
    with paths.gpx.open(encoding="utf-8") as handle:
        gpx = gpxpy.parse(handle)

    assert paths.kml.exists()
    assert geojson_payload["type"] == "FeatureCollection"
    assert [feature["properties"]["name"] for feature in geojson_payload["features"]] == [
        "Doline 1",
        "Doline 2",
    ]
    assert [waypoint.name for waypoint in gpx.waypoints] == ["Doline 1", "Doline 2"]
    assert gpx.waypoints[0].longitude == result.depressions[0].centroid.lon
    assert gpx.waypoints[0].latitude == result.depressions[0].centroid.lat
