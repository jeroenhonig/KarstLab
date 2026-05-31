"""Canonical analysis statistics and Top 25 vector exports."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import geopandas as gpd
from shapely.geometry import Point, shape

from karstlab.data.schemas import AnalysisParams, DepressionResult, PipelineResult
from karstlab.data.vector_io import WGS84_CRS, to_geojson, to_gpx, to_kml

EXPORT_SCHEMA_VERSION = "0.2"
TOP_DEPRESSION_LIMIT = 25

GeometryMode = Literal["footprint", "centroid"]


@dataclass(frozen=True)
class Top25ExportPaths:
    geojson: Path
    kml: Path
    gpx: Path


def build_statistics(
    result_or_depressions: PipelineResult | Sequence[DepressionResult],
    *,
    analysis_params: AnalysisParams | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical v0.2-ish statistics payload for an analysis result."""
    depressions, top_depressions, params, result_provenance = _export_inputs(
        result_or_depressions,
        analysis_params=analysis_params,
    )
    merged_provenance = {**result_provenance, **dict(provenance or {})}

    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "counts": _counts(depressions, top_depressions),
        "top25": [_depression_summary(depression) for depression in top_depressions],
        "params": params.model_dump(mode="json"),
        "provenance": merged_provenance,
    }


def write_statistics(
    result_or_depressions: PipelineResult | Sequence[DepressionResult],
    path: Path,
    *,
    analysis_params: AnalysisParams | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> Path:
    """Write analysis statistics JSON with stable formatting."""
    payload = build_statistics(
        result_or_depressions,
        analysis_params=analysis_params,
        provenance=provenance,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def depressions_to_geodataframe(
    depressions: Sequence[DepressionResult],
    *,
    geometry_mode: GeometryMode = "footprint",
    crs: str = WGS84_CRS,
) -> gpd.GeoDataFrame:
    """Convert depression results to a GeoDataFrame suitable for vector export."""
    records = [
        {
            **_depression_summary(depression),
            "geometry": _geometry_for_mode(depression, geometry_mode),
        }
        for depression in depressions
    ]
    if not records:
        return gpd.GeoDataFrame(
            columns=[
                "id",
                "rank",
                "name",
                "max_depth_m",
                "area_m2",
                "centroid",
                "quality_flags",
                "geometry",
            ],
            geometry="geometry",
            crs=crs,
        )
    return gpd.GeoDataFrame(records, geometry="geometry", crs=crs)


def write_top25_vector_exports(
    result_or_depressions: PipelineResult | Sequence[DepressionResult],
    *,
    geojson_path: Path,
    kml_path: Path,
    gpx_path: Path,
    analysis_params: AnalysisParams | None = None,
) -> Top25ExportPaths:
    """Write Top 25 depression exports as GeoJSON, KML, and GPX."""
    _, top_depressions, _, _ = _export_inputs(
        result_or_depressions,
        analysis_params=analysis_params,
    )
    footprint_frame = depressions_to_geodataframe(top_depressions, geometry_mode="footprint")
    centroid_frame = depressions_to_geodataframe(top_depressions, geometry_mode="centroid")

    return Top25ExportPaths(
        geojson=to_geojson(footprint_frame, geojson_path),
        kml=to_kml(footprint_frame, kml_path),
        gpx=to_gpx(centroid_frame, gpx_path),
    )


def _export_inputs(
    result_or_depressions: PipelineResult | Sequence[DepressionResult],
    *,
    analysis_params: AnalysisParams | None,
) -> tuple[list[DepressionResult], list[DepressionResult], AnalysisParams, dict[str, Any]]:
    if isinstance(result_or_depressions, PipelineResult):
        depressions = list(result_or_depressions.depressions)
        top_depressions = _top_depressions(result_or_depressions)
        return (
            depressions,
            top_depressions,
            result_or_depressions.analysis_params,
            dict(result_or_depressions.provenance),
        )

    if analysis_params is None:
        raise ValueError("analysis_params is required when exporting depression sequences")

    depressions = list(result_or_depressions)
    return depressions, _ranked_top25(depressions), analysis_params, {}


def _top_depressions(result: PipelineResult) -> list[DepressionResult]:
    if result.top_depressions:
        return list(result.top_depressions[:TOP_DEPRESSION_LIMIT])
    return _ranked_top25(result.depressions)


def _ranked_top25(depressions: Sequence[DepressionResult]) -> list[DepressionResult]:
    return sorted(
        depressions,
        key=lambda depression: (
            depression.rank is None,
            depression.rank or TOP_DEPRESSION_LIMIT + 1,
            -depression.max_depth_m,
            -depression.area_m2,
            depression.id,
        ),
    )[:TOP_DEPRESSION_LIMIT]


def _counts(
    depressions: Sequence[DepressionResult],
    top_depressions: Sequence[DepressionResult],
) -> dict[str, Any]:
    return {
        "depressions": len(depressions),
        "ranked_depressions": sum(depression.rank is not None for depression in depressions),
        "top25": len(top_depressions),
        "quality_flags": {
            "edge_proximity": sum(
                depression.quality_flags.edge_proximity for depression in depressions
            ),
            "nodata_adjacent": sum(
                depression.quality_flags.nodata_adjacent for depression in depressions
            ),
            "nested": sum(depression.quality_flags.nested for depression in depressions),
            "depth_confidence": _depth_confidence_counts(depressions),
        },
    }


def _depth_confidence_counts(depressions: Sequence[DepressionResult]) -> dict[str, int]:
    counts = {"low": 0, "medium": 0, "high": 0}
    for depression in depressions:
        counts[depression.quality_flags.depth_confidence.value] += 1
    return counts


def _depression_summary(depression: DepressionResult) -> dict[str, Any]:
    return {
        "id": depression.id,
        "rank": depression.rank,
        "name": _depression_name(depression),
        "max_depth_m": depression.max_depth_m,
        "area_m2": depression.area_m2,
        "centroid": depression.centroid.model_dump(mode="json"),
        "quality_flags": depression.quality_flags.model_dump(mode="json"),
    }


def _depression_name(depression: DepressionResult) -> str:
    label = depression.rank if depression.rank is not None else depression.id
    return f"Doline {label}"


def _geometry_for_mode(depression: DepressionResult, geometry_mode: GeometryMode) -> Any:
    if geometry_mode == "centroid":
        return Point(depression.centroid.lon, depression.centroid.lat)
    return shape(depression.geometry)
