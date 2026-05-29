"""Headless analysis pipeline orchestration."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
from pyproj import Transformer
from rasterio.features import shapes
from shapely.geometry import shape

from karstlab.business.contours import extract_contours
from karstlab.business.depression_ranker import rank_depressions
from karstlab.business.dolines import DolineDetectionParams, detect_dolines
from karstlab.business.hydrology import HydrologyAnalyzer, HydrologyBackend
from karstlab.business.terrain import curvature, hillshade, slope
from karstlab.data.analysis_exports import (
    build_statistics,
    write_statistics,
    write_top25_vector_exports,
)
from karstlab.data.project_io import canonical_output_paths
from karstlab.data.raster_io import read_dem, save_geotiff
from karstlab.data.schemas import (
    AnalysisParams,
    PipelineResult,
    PipelineStatus,
    PipelineStepResult,
    ProjectFile,
)
from karstlab.data.vector_io import read_gpx_waypoints, read_kml_points, to_geojson, to_kml
from karstlab.data.vrt_builder import assemble_geotiff, assemble_vrt
from karstlab.presentation.map_builder import (
    ImageLayerSpec,
    MapLayerSpec,
    render_top_depressions_map_html,
)
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

    started_at = datetime.now(UTC)
    steps: list[PipelineStepResult] = []
    paths = canonical_output_paths(project)
    dem_path = _analysis_dem_path(project, paths, steps=steps)

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

    terrain_started = datetime.now(UTC)
    terrain_paths = _write_terrain_derivatives(original_dem, paths)
    steps.append(
        _completed_step(
            "terrain",
            started_at=terrain_started,
            output_paths=list(terrain_paths.values()),
            metadata={"derivatives": sorted(terrain_paths)},
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
        input_dem_paths=[dem_path],
        output_dir=project.output_dir,
        depressions=depressions,
        top_depressions=top_depressions,
        steps=steps,
        provenance={
            "pipeline": "headless_analysis",
            "pipeline_version": project.pipeline_version,
            "schema_version": project.schema_version,
            "source_dem_paths": [str(path) for path in project.dem_paths],
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
    streams = _stream_raster_to_geodataframe(hydrology_outputs.streams)
    contours_labeled = _label_contours(contours)
    paths["interactive_map"].write_text(
        render_top_depressions_map_html(
            result.top_depressions,
            hillshade_layers=[
                ImageLayerSpec(
                    "Hillshade",
                    read_dem(paths["hillshade"]).array,
                    bounds=_wgs84_bounds(
                        original_dem.metadata.bounds,
                        original_dem.metadata.crs.to_string(),
                    ),
                    opacity=0.45,
                    show=True,
                ),
            ],
            contour_layers=[
                MapLayerSpec(
                    "Contours",
                    contours_labeled,
                    show=False,
                    style={"color": "#f0c040", "weight": 1, "fillOpacity": 0.0},
                )
            ],
            stream_layers=[
                MapLayerSpec(
                    "Streams",
                    streams,
                    show=False,
                    style={"color": "#4a90d9", "weight": 2, "fillOpacity": 0.15},
                )
            ],
            imported_marker_layers=_imported_marker_layers(project),
        ),
        encoding="utf-8",
    )
    map_size_bytes = paths["interactive_map"].stat().st_size
    steps.append(
        _completed_step(
            "interactive_map",
            started_at=map_started,
            output_paths=[paths["interactive_map"]],
            metadata={"file_size_kb": round(map_size_bytes / 1024, 1)},
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


def _analysis_dem_path(
    project: ProjectFile,
    paths: dict[str, Path],
    *,
    steps: list[PipelineStepResult],
) -> Path:
    if len(project.dem_paths) == 1:
        return project.dem_paths[0]

    vrt_started = datetime.now(UTC)
    vrt_path = project.cache_dir / "assembled_dem.vrt"
    mosaic = assemble_vrt(project.dem_paths, vrt_path)
    assembled_dem = assemble_geotiff(mosaic.path, paths["assembled_dem"])
    steps.append(
        _completed_step(
            "vrt_assembly",
            started_at=vrt_started,
            output_paths=[mosaic.path, assembled_dem],
            metadata={
                "tile_count": len(mosaic.tiles),
                "width": mosaic.width,
                "height": mosaic.height,
                "assembled_dem": str(assembled_dem),
            },
        )
    )
    return assembled_dem


def _write_terrain_derivatives(original_dem: Any, paths: dict[str, Path]) -> dict[str, Path]:
    transform = original_dem.metadata.transform
    crs = original_dem.metadata.crs
    nodata = original_dem.metadata.nodata
    array = original_dem.array.astype("float64", copy=False)
    if nodata is not None:
        array = np.where(array == nodata, np.nan, array)

    derivatives = {
        "hillshade": hillshade(array, cell_size=transform),
        "slope": slope(array, cell_size=transform),
        "curvature": curvature(array, cell_size=transform),
    }
    return {
        name: save_geotiff(
            paths[name],
            values.astype("float32"),
            crs=crs,
            transform=transform,
            nodata=np.nan,
            dtype="float32",
        )
        for name, values in derivatives.items()
    }


_STREAM_SIMPLIFY_TOLERANCE = 5.0


def _stream_raster_to_geodataframe(streams_path: Path) -> gpd.GeoDataFrame:
    streams = read_dem(streams_path)
    array = streams.array
    mask = np.isfinite(array) & (array > 0)
    if streams.metadata.nodata is not None:
        mask &= array != streams.metadata.nodata

    records = []
    for geometry, value in shapes(
        mask.astype("uint8"),
        mask=mask,
        transform=streams.metadata.transform,
    ):
        if value != 0:
            geom = shape(geometry).simplify(_STREAM_SIMPLIFY_TOLERANCE, preserve_topology=True)
            if geom.is_valid and not geom.is_empty:
                records.append({"value": float(value), "geometry": geom})
    return gpd.GeoDataFrame(records, geometry="geometry", crs=streams.metadata.crs)


def _imported_marker_layers(project: ProjectFile) -> list[MapLayerSpec]:
    layers: list[MapLayerSpec] = []
    for marker_path in project.marker_paths:
        if not marker_path.exists():
            continue
        try:
            suffix = marker_path.suffix.lower()
            if suffix == ".gpx":
                markers = read_gpx_waypoints(marker_path)
            elif suffix == ".kml":
                markers = read_kml_points(marker_path)
            else:
                continue
        except Exception:  # noqa: BLE001 - skip unreadable marker files silently
            continue
        if markers.empty:
            continue
        layers.append(
            MapLayerSpec(
                name=marker_path.stem,
                data=markers,
                show=True,
                style={"color": "#f0c040", "weight": 3},
            )
        )
    return layers


def _wgs84_bounds(
    bounds: tuple[float, float, float, float],
    crs: str,
) -> list[list[float]]:
    left, bottom, right, top = bounds
    transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    west, south = transformer.transform(left, bottom)
    east, north = transformer.transform(right, top)
    return [[south, west], [north, east]]


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


def _label_contours(contours: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return contours with a human-readable 'name' column derived from elevation_m."""
    labeled = contours.copy()
    if "name" not in labeled.columns:
        if "elevation_m" in labeled.columns:
            labeled["name"] = labeled["elevation_m"].apply(lambda e: f"{e:.0f} m")
        else:
            labeled["name"] = [f"Contour {i + 1}" for i in range(len(labeled))]
    return labeled


def _write_contours(contours: gpd.GeoDataFrame, *, geojson_path: Path, kml_path: Path) -> None:
    to_geojson(_label_contours(contours), geojson_path)
    to_kml(_label_contours(contours), kml_path)


__all__ = ["run_headless_analysis"]
