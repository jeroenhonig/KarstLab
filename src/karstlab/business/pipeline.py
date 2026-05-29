"""Headless analysis pipeline orchestration."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd

from karstlab.business.contours import extract_contours
from karstlab.business.depression_ranker import rank_depressions
from karstlab.business.dolines import DolineDetectionParams, detect_dolines
from karstlab.business.hydrology import HydrologyAnalyzer, HydrologyBackend
from karstlab.data.analysis_exports import (
    build_statistics,
    write_statistics,
    write_top25_vector_exports,
)
from karstlab.data.project_io import canonical_output_paths
from karstlab.data.raster_io import read_dem
from karstlab.data.schemas import (
    AnalysisParams,
    PipelineResult,
    PipelineStatus,
    PipelineStepResult,
    ProjectFile,
)
from karstlab.data.vector_io import to_geojson, to_kml
from karstlab.presentation.map_builder import render_top_depressions_map_html
from karstlab.presentation.report import write_html_report


def run_headless_analysis(
    project: ProjectFile,
    *,
    hydrology_backend: HydrologyBackend,
    callback: Callable[[str], None] | None = None,
) -> PipelineResult:
    """Run the headless DEM analysis pipeline for a project."""
    if not project.dem_paths:
        raise ValueError("project.dem_paths must contain at least one DEM path")
    if len(project.dem_paths) > 1:
        raise NotImplementedError("multi-tile analysis requires VRT assembly integration")

    started_at = datetime.now(UTC)
    steps: list[PipelineStepResult] = []
    dem_path = project.dem_paths[0]

    original_dem = read_dem(dem_path)
    steps.append(
        _completed_step(
            "read_dem",
            started_at=started_at,
            output_paths=[],
            metadata={
                "path": str(dem_path),
                "width": original_dem.metadata.width,
                "height": original_dem.metadata.height,
                "crs": original_dem.metadata.crs.to_string(),
            },
        )
    )

    hydrology_started = datetime.now(UTC)
    hydrology = HydrologyAnalyzer(whitebox=hydrology_backend)
    hydrology_outputs = hydrology.run(
        dem_path,
        project.output_dir / "rasters",
        stream_threshold=float(project.analysis_params.stream_threshold_cells),
        callback=callback,
    )
    steps.append(
        _completed_step(
            "hydrology",
            started_at=hydrology_started,
            output_paths=[
                hydrology_outputs.filled_dem,
                hydrology_outputs.d8_pointer,
                hydrology_outputs.flow_accumulation,
                hydrology_outputs.streams,
            ],
        )
    )

    fill_started = datetime.now(UTC)
    detection_filled_dem = hydrology_backend.fill_depressions(
        dem_path,
        project.output_dir / "rasters" / "depression_fill" / "dem_detection_filled.tif",
        callback=callback,
    )
    steps.append(
        _completed_step(
            "depression_fill",
            started_at=fill_started,
            output_paths=[detection_filled_dem],
        )
    )

    detection_started = datetime.now(UTC)
    filled_dem = read_dem(detection_filled_dem)
    depressions = detect_dolines(
        original_dem.array,
        filled_dem.array,
        transform=original_dem.metadata.transform,
        crs=original_dem.metadata.crs,
        nodata=original_dem.metadata.nodata,
        params=_doline_params(project.analysis_params),
    )
    top_depressions = rank_depressions(depressions)
    steps.append(
        _completed_step(
            "doline_detection",
            started_at=detection_started,
            output_paths=[],
            metadata={
                "depression_count": len(depressions),
                "top_depression_count": len(top_depressions),
            },
        )
    )

    contours_started = datetime.now(UTC)
    contours = extract_contours(
        original_dem.array,
        transform=original_dem.metadata.transform,
        interval_m=project.analysis_params.contour_interval_m,
        crs=original_dem.metadata.crs,
    )
    paths = canonical_output_paths(project)
    _write_contours(
        contours,
        geojson_path=paths["contours_geojson"],
        kml_path=paths["contours_kml"],
    )
    steps.append(
        _completed_step(
            "contours",
            started_at=contours_started,
            output_paths=[paths["contours_geojson"], paths["contours_kml"]],
            metadata={"contour_count": len(contours)},
        )
    )

    result = PipelineResult(
        project_id=project.id,
        status=PipelineStatus.SUCCESS,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        land_profile=project.land_profile,
        analysis_params=project.analysis_params,
        input_dem_paths=project.dem_paths,
        output_dir=project.output_dir,
        depressions=depressions,
        top_depressions=top_depressions,
        steps=steps,
        provenance={
            "pipeline": "headless_analysis",
            "pipeline_version": project.pipeline_version,
            "schema_version": project.schema_version,
        },
    )

    export_started = datetime.now(UTC)
    write_statistics(result, paths["statistics"])
    write_top25_vector_exports(
        result,
        geojson_path=paths["dolines_geojson"],
        kml_path=paths["dolines_kml"],
        gpx_path=paths["top_depressions_gpx"],
    )
    steps.append(
        _completed_step(
            "exports",
            started_at=export_started,
        output_paths=[
            paths["statistics"],
            paths["dolines_geojson"],
            paths["dolines_kml"],
            paths["top_depressions_gpx"],
            paths["contours_geojson"],
            paths["contours_kml"],
        ],
        )
    )

    map_started = datetime.now(UTC)
    paths["interactive_map"].parent.mkdir(parents=True, exist_ok=True)
    paths["interactive_map"].write_text(
        render_top_depressions_map_html(result.top_depressions),
        encoding="utf-8",
    )
    steps.append(
        _completed_step(
            "interactive_map",
            started_at=map_started,
            output_paths=[paths["interactive_map"]],
        )
    )

    report_started = datetime.now(UTC)
    write_html_report(
        paths["report"],
        project.analysis_params,
        result,
        statistics=build_statistics(result),
        provenance=result.provenance,
        map_html_path=paths["interactive_map"],
        map_reference=str(paths["interactive_map"]),
    )
    steps.append(
        _completed_step(
            "report",
            started_at=report_started,
            output_paths=[paths["report"]],
        )
    )

    result = result.model_copy(update={"steps": steps})
    _write_pipeline_result(result, paths["pipeline_result"])
    return result


def _doline_params(params: AnalysisParams) -> DolineDetectionParams:
    return DolineDetectionParams(
        min_depth_m=params.doline_min_depth_m,
        max_depth_m=params.doline_max_depth_m,
        min_area_m2=params.doline_min_area_m2,
        max_area_m2=params.doline_max_area_m2,
    )


def _completed_step(
    step_id: str,
    *,
    started_at: datetime,
    output_paths: list[Path],
    metadata: dict[str, Any] | None = None,
) -> PipelineStepResult:
    return PipelineStepResult(
        step_id=step_id,
        status=PipelineStatus.SUCCESS,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        output_paths=output_paths,
        metadata=metadata or {},
    )


def _write_pipeline_result(result: PipelineResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.model_dump(mode="json")
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def _write_contours(contours: gpd.GeoDataFrame, *, geojson_path: Path, kml_path: Path) -> None:
    export_frame = contours.copy()
    if "name" not in export_frame.columns:
        export_frame["name"] = [f"Contour {index + 1}" for index in range(len(export_frame))]
    to_geojson(export_frame, geojson_path)
    to_kml(export_frame, kml_path)


__all__ = ["run_headless_analysis"]
