"""Headless analysis pipeline orchestration."""

from __future__ import annotations

import hashlib
import heapq
import json
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import geopandas as gpd
import numpy as np
import rasterio
from pyproj import Transformer

from karstlab.business.contours import extract_contours
from karstlab.business.depression_ranker import rank_depressions
from karstlab.business.dolines import (
    DolineDetectionParams,
    depression_depth_raster,
    detect_dolines,
)
from karstlab.business.hydrology import HydrologyAnalyzer, HydrologyBackend
from karstlab.business.marker_manager import imported_marker_color
from karstlab.business.terrain import compute_terrain_derivatives
from karstlab.data.analysis_exports import (
    build_statistics,
    write_statistics,
    write_top25_vector_exports,
)
from karstlab.data.land_profiles import load_land_profile
from karstlab.data.project_io import canonical_output_paths
from karstlab.data.raster_io import read_dem, save_geotiff
from karstlab.data.schemas import (
    AnalysisParams,
    DepressionResult,
    LandProfile,
    PipelineResult,
    PipelineStatus,
    PipelineStepResult,
    ProjectFile,
    UserSettings,
    VectorLayerConfig,
)
from karstlab.data.user_settings import load_user_settings
from karstlab.data.vector_io import (
    read_gpx_track,
    read_gpx_waypoints,
    read_kml_geometries,
    survey_line_geometry,
    to_geojson,
    to_kml,
    to_wgs84,
)
from karstlab.data.vrt_builder import assemble_geotiff, assemble_vrt
from karstlab.presentation import map_palette
from karstlab.presentation.map_builder import (
    ImageLayerSpec,
    MapLayerSpec,
    TileLayerSpec,
    WmsLayerSpec,
    render_top_depressions_map_html,
)
from karstlab.presentation.report import write_html_report

logger = logging.getLogger(__name__)


def _dem_fingerprint(dem_paths: list[Path]) -> str:
    """Hash the source DEM tiles (path + size + mtime) to detect unchanged input."""
    parts: list[str] = []
    for path in sorted(dem_paths, key=str):
        try:
            stat = Path(path).stat()
            parts.append(f"{path}:{stat.st_size}:{stat.st_mtime_ns}")
        except OSError:
            parts.append(f"{path}:missing")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


@dataclass
class _DemCache:
    """Reuse DEM-only intermediates across runs when the input DEM is unchanged.

    Mosaic, terrain derivatives and the WhiteboxTools fill/pointer/accumulation
    depend solely on the input DEM, not on the analysis parameters. Tweaking a
    parameter (stream threshold, doline filters, contour interval) therefore only
    needs the cheap downstream stages re-run, so those heavy outputs are reused
    when their on-disk fingerprint still matches.
    """

    fingerprint: str
    marker: Path
    valid: bool

    @classmethod
    def open(cls, cache_dir: Path, dem_paths: list[Path], *, force: bool) -> _DemCache:
        fingerprint = _dem_fingerprint(dem_paths)
        marker = cache_dir / "dem_stage.fingerprint"
        stored = marker.read_text(encoding="utf-8").strip() if marker.exists() else None
        valid = (not force) and stored == fingerprint
        return cls(fingerprint=fingerprint, marker=marker, valid=valid)

    def reuse(self, *outputs: Path) -> bool:
        return self.valid and all(Path(output).exists() for output in outputs)

    def commit(self) -> None:
        self.marker.parent.mkdir(parents=True, exist_ok=True)
        self.marker.write_text(self.fingerprint, encoding="utf-8")


def run_headless_analysis(
    project: ProjectFile,
    *,
    hydrology_backend: HydrologyBackend,
    callback: Callable[[str], None] | None = None,
    user_settings: UserSettings | None = None,
    force_recompute: bool = False,
) -> PipelineResult:
    """Run the headless DEM analysis pipeline for a project."""
    if not project.dem_paths:
        raise ValueError("project.dem_paths must contain at least one DEM path")

    settings = user_settings or load_user_settings()
    started_at = datetime.now(UTC)
    steps: list[PipelineStepResult] = []
    paths = canonical_output_paths(project)
    cache = _DemCache.open(project.cache_dir, list(project.dem_paths), force=force_recompute)
    if cache.valid:
        _notify(callback, "Reusing cached DEM intermediates (unchanged input)")
    dem_path = _analysis_dem_path(
        project, paths, steps=steps, user_settings=settings, callback=callback, cache=cache
    )

    _notify(callback, "Reading DEM")
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
                "crs": (
                    original_dem.metadata.crs.to_string()
                    if original_dem.metadata.crs
                    else "unknown"
                ),
            },
            callback=callback,
        )
    )

    # The terrain derivatives and contours are pure NumPy work, while the
    # hydrology and detection-fill steps run inside the WhiteboxTools subprocess.
    # The two tracks only depend on the input DEM, so overlap them: NumPy runs on
    # a worker thread (its heavy ufuncs release the GIL) while Whitebox crunches
    # in its own process. Progress markers stay monotonic because the GUI takes
    # the max of any reported phase value.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="karstlab-numpy") as executor:
        numpy_future = executor.submit(
            _run_numpy_track, original_dem, paths, project, callback=callback, cache=cache
        )

        _notify(callback, "Running hydrology analysis")
        hydrology_started = datetime.now(UTC)
        hydrology = HydrologyAnalyzer(whitebox=hydrology_backend)
        hydrology_outputs = hydrology.run(
            dem_path,
            project.output_dir / "rasters",
            stream_threshold=float(project.analysis_params.stream_threshold_cells),
            callback=callback,
            reuse=cache.reuse,
        )
        hydrology_step = _completed_step(
            "hydrology",
            started_at=hydrology_started,
            output_paths=[
                hydrology_outputs.filled_dem,
                hydrology_outputs.d8_pointer,
                hydrology_outputs.flow_accumulation,
                hydrology_outputs.streams,
            ],
            callback=callback,
        )

        _notify(callback, "Filling depressions")
        fill_started = datetime.now(UTC)
        detection_filled_dem = _fill_depressions_for_detection(
            original_dem,
            dem_path=dem_path,
            output_path=project.output_dir
            / "rasters"
            / "depression_fill"
            / "dem_detection_filled.tif",
            hydrology_backend=hydrology_backend,
            callback=callback,
            cache=cache,
        )
        fill_step = _completed_step(
            "depression_fill",
            started_at=fill_started,
            output_paths=[detection_filled_dem],
            callback=callback,
        )

        # Re-raises any exception (including AnalysisCancelled) from the NumPy track.
        numpy_track = numpy_future.result()

    steps.append(numpy_track.terrain_step)
    steps.append(hydrology_step)
    steps.append(fill_step)

    _notify(callback, "Detecting dolines")
    detection_started = datetime.now(UTC)
    filled_dem = read_dem(detection_filled_dem)
    depression_depth = depression_depth_raster(
        original_dem.array,
        filled_dem.array,
        nodata=original_dem.metadata.nodata,
    )
    depth_path = save_geotiff(
        paths["depression_depth"],
        depression_depth.astype("float32"),
        crs=original_dem.metadata.crs,
        transform=original_dem.metadata.transform,
        nodata=None,
        dtype="float32",
    )
    depressions = detect_dolines(
        original_dem.array,
        filled_dem.array,
        transform=original_dem.metadata.transform,
        crs=original_dem.metadata.crs,
        nodata=original_dem.metadata.nodata,
        params=_doline_params(project.analysis_params),
        depth=depression_depth,
    )
    # Detection and the depth export are the last consumers of the filled DEM
    # and the depth raster; release them so they do not sit alongside the
    # terrain derivatives and contours for the rest of the run.
    del filled_dem, depression_depth
    # Annotate distance/orientation-to-nearest-fault before ranking so the top set
    # carries it; keep the fault lines for the interactive-map fault layer.
    depressions, fault_lines = _annotate_fault_distances(depressions, project, callback=callback)
    top_depressions = rank_depressions(depressions)
    steps.append(
        _completed_step(
            "doline_detection",
            started_at=detection_started,
            output_paths=[depth_path],
            metadata={
                "depression_count": len(depressions),
                "top_depression_count": len(top_depressions),
            },
            callback=callback,
        )
    )

    steps.append(numpy_track.contours_step)

    conduit_summary, conduit_contours_path, conduit_candidates = _run_conduit_stage(
        project, depressions, paths, callback=callback
    )

    provenance: dict[str, Any] = {
        "pipeline": "headless_analysis",
        "pipeline_version": project.pipeline_version,
        "schema_version": project.schema_version,
        "source_dem_paths": [str(path) for path in project.dem_paths],
    }
    if conduit_summary is not None:
        provenance["conduit"] = conduit_summary

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
        provenance=provenance,
    )

    _notify(callback, "Writing exports")
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
            callback=callback,
        )
    )

    _notify(callback, "Rendering interactive map")
    map_started = datetime.now(UTC)
    paths["interactive_map"].parent.mkdir(parents=True, exist_ok=True)
    wgs84_bounds = _wgs84_bounds(
        original_dem.metadata.bounds, original_dem.metadata.crs.to_string()
    )
    stream_overlay = _streams_overlay(hydrology_outputs.streams, bounds=wgs84_bounds)
    contours_labeled = numpy_track.contours_labeled
    land_profile = _load_project_profile(project)
    vector_overlays = _profile_vector_overlays(
        land_profile,
        dem_bounds=original_dem.metadata.bounds,
        dem_crs=original_dem.metadata.crs.to_string(),
        cache_dir=project.cache_dir,
        callback=callback,
    )
    paths["interactive_map"].write_text(
        render_top_depressions_map_html(
            result.top_depressions,
            vector_layers=vector_overlays,
            hillshade_layers=[
                ImageLayerSpec(
                    "Hillshade",
                    _hillshade_overlay_rgba(numpy_track.hillshade_array),
                    bounds=wgs84_bounds,
                    opacity=_HILLSHADE_OVERLAY_OPACITY,
                    show=True,
                ),
            ],
            contour_layers=[
                MapLayerSpec(
                    "Contours",
                    _simplify_for_map(contours_labeled),
                    show=False,
                    # Topographic brown (central palette) — distinct from the
                    # doline-distance ramp. Thin lines so a fine interval stays
                    # legible rather than flooding the map.
                    style={
                        "color": map_palette.CONTOURS,
                        "weight": 1,
                        "opacity": 0.75,
                        "fillOpacity": 0.0,
                    },
                )
            ],
            stream_image_layers=[stream_overlay] if stream_overlay is not None else [],
            all_depressions=result.depressions,
            fault_geojson=_faults_geojson(
                fault_lines,
                dem_bounds=original_dem.metadata.bounds,
                dem_crs=original_dem.metadata.crs.to_string(),
            ),
            conduit_geojson=_load_conduit_geojson(conduit_contours_path),
            conduit_candidates=conduit_candidates,
            imported_marker_layers=_imported_marker_layers(
                project, marker_colors=settings.marker_colors
            ),
            extra_tile_layers=_profile_extra_tile_layers(land_profile),
            wms_layers=_profile_wms_layers(land_profile),
            tiles=_profile_tile_url(land_profile),
            tile_attribution=_profile_tile_attribution(land_profile),
        ),
        encoding="utf-8",
    )
    map_size_bytes = paths["interactive_map"].stat().st_size
    _notify(callback, f"Interactive map: {map_size_bytes / 1024 / 1024:.1f} MB")
    steps.append(
        _completed_step(
            "interactive_map",
            started_at=map_started,
            output_paths=[paths["interactive_map"]],
            metadata={"file_size_kb": round(map_size_bytes / 1024, 1)},
            callback=callback,
        )
    )

    _notify(callback, "Writing report")
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
            callback=callback,
        )
    )

    result = result.model_copy(update={"steps": steps})
    # Stamp the DEM fingerprint so the next run with the same input can reuse the
    # heavy DEM-only intermediates just produced.
    cache.commit()
    _emit_timing_summary(
        callback, steps, total_started=started_at, total_finished=datetime.now(UTC)
    )
    _write_pipeline_result(result, paths["pipeline_result"])
    return result


# Longest-side pixel budget for the hillshade *map overlay*. Folium embeds the
# overlay as a base64 PNG inside the HTML; a full-resolution multi-tile mosaic
# would inflate the document to tens of megabytes and stall both writing and the
# QWebEngine load. The full-resolution hillshade GeoTIFF is still written
# separately, so this only affects the interactive preview.
_MAP_OVERLAY_MAX_PX = 2048


def _overview_array(array: np.ndarray, *, max_px: int = _MAP_OVERLAY_MAX_PX) -> np.ndarray:
    """Stride-decimate a 2D array so its longest side is at most ``max_px``."""
    if array.ndim != 2:
        return array
    longest = max(array.shape[0], array.shape[1])
    if max_px <= 0 or longest <= max_px:
        return array
    factor = int(np.ceil(longest / max_px))
    return array[::factor, ::factor]


# Faint relief: the hillshade is context behind the basemap, not a foreground
# layer. Rendering it as an explicit grayscale RGBA with fully transparent
# nodata (instead of a 2D float array, which folium rendered near-black and
# painted the nodata border solid) keeps the basemap clearly readable.
_HILLSHADE_OVERLAY_OPACITY = 0.35


def _hillshade_overlay_rgba(array: np.ndarray) -> np.ndarray:
    """Decimate a 0-255 hillshade to a grayscale RGBA overlay, nodata transparent."""
    arr = _overview_array(array)
    finite = np.isfinite(arr)
    gray = np.clip(np.where(finite, arr, 0.0), 0.0, 255.0).astype(np.uint8)
    rgba = np.zeros((*arr.shape, 4), dtype=np.uint8)
    rgba[..., 0] = gray
    rgba[..., 1] = gray
    rgba[..., 2] = gray
    rgba[..., 3] = np.where(finite, 255, 0).astype(np.uint8)
    return rgba


def _notify(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is not None:
        callback(message)


def _analysis_dem_path(
    project: ProjectFile,
    paths: dict[str, Path],
    *,
    steps: list[PipelineStepResult],
    user_settings: UserSettings,
    callback: Callable[[str], None] | None = None,
    cache: _DemCache,
) -> Path:
    fallback_crs = project.crs_analysis

    if (
        len(project.dem_paths) == 1
        and not _needs_vrt_for_crs_fallback(project.dem_paths[0])
        and not _single_tile_exceeds_large_dem_threshold(
            project.dem_paths[0], user_settings=user_settings
        )
    ):
        # Small GeoTIFF with embedded CRS — use directly, no VRT needed.
        return project.dem_paths[0]

    # Reuse a previously assembled GeoTIFF mosaic when the input tiles are
    # unchanged (the assembled_dem only exists for the multi-tile geotiff mode).
    if cache.reuse(paths["assembled_dem"]):
        _notify(callback, "Reusing cached DEM mosaic")
        steps.append(
            _completed_step(
                "vrt_assembly",
                started_at=datetime.now(UTC),
                output_paths=[paths["assembled_dem"]],
                metadata={"reused_cache": True},
                callback=callback,
            )
        )
        return paths["assembled_dem"]

    _notify(callback, f"Assembling {len(project.dem_paths)} DEM tiles")
    vrt_started = datetime.now(UTC)
    vrt_path = project.cache_dir / "assembled_dem.vrt"
    mosaic = assemble_vrt(project.dem_paths, vrt_path, fallback_crs=fallback_crs)
    use_vrt_for_analysis = _mosaic_exceeds_large_dem_threshold(mosaic, user_settings=user_settings)
    if not use_vrt_for_analysis:
        _notify(callback, "Building analysis GeoTIFF mosaic")
    output_paths = [mosaic.path]
    metadata = {
        "tile_count": len(mosaic.tiles),
        "width": mosaic.width,
        "height": mosaic.height,
        "analysis_dem_mode": "vrt" if use_vrt_for_analysis else "geotiff",
    }
    if use_vrt_for_analysis:
        analysis_dem = mosaic.path
    else:
        analysis_dem = assemble_geotiff(mosaic.path, paths["assembled_dem"])
        output_paths.append(analysis_dem)
        metadata["assembled_dem"] = str(analysis_dem)
    steps.append(
        _completed_step(
            "vrt_assembly",
            started_at=vrt_started,
            output_paths=output_paths,
            metadata=metadata,
            callback=callback,
        )
    )
    return analysis_dem


def _needs_vrt_for_crs_fallback(dem_path: Path) -> bool:
    try:
        with rasterio.open(dem_path) as dataset:
            return dataset.crs is None
    except Exception:  # noqa: BLE001 - let VRT assembly report the detailed raster error later
        return False


def _single_tile_exceeds_large_dem_threshold(
    dem_path: Path, *, user_settings: UserSettings
) -> bool:
    try:
        with rasterio.open(dem_path) as dataset:
            estimated = _estimated_raster_bytes(
                width=dataset.width,
                height=dataset.height,
                count=1,
                dtype=dataset.dtypes[0],
            )
    except Exception:  # noqa: BLE001 - let VRT assembly report the detailed raster error later
        return False
    return estimated > user_settings.large_dem_threshold_mb * 1024 * 1024


def _mosaic_exceeds_large_dem_threshold(mosaic: Any, *, user_settings: UserSettings) -> bool:
    threshold_bytes = user_settings.large_dem_threshold_mb * 1024 * 1024
    return _estimated_raster_bytes(
        width=mosaic.width,
        height=mosaic.height,
        count=1,
        dtype=mosaic.dtype,
    ) > threshold_bytes


def _estimated_raster_bytes(*, width: int, height: int, count: int, dtype: str) -> int:
    return width * height * count * np.dtype(dtype).itemsize


@dataclass(frozen=True)
class _NumpyTrackResult:
    """Outputs of the NumPy analysis track (terrain derivatives + contours)."""

    terrain_step: PipelineStepResult
    hillshade_array: np.ndarray
    contours: gpd.GeoDataFrame
    contours_labeled: gpd.GeoDataFrame
    contours_step: PipelineStepResult


def _run_numpy_track(
    original_dem: Any,
    paths: dict[str, Path],
    project: ProjectFile,
    *,
    callback: Callable[[str], None] | None,
    cache: _DemCache,
) -> _NumpyTrackResult:
    """Run the pure-NumPy analysis steps (terrain derivatives, then contours).

    Executed on a worker thread so it overlaps the WhiteboxTools hydrology and
    fill steps, which run in a separate process.
    """
    _notify(callback, "Computing terrain derivatives")
    terrain_started = datetime.now(UTC)
    terrain_paths, hillshade_array = _write_terrain_derivatives(
        original_dem, paths, cache=cache, callback=callback
    )
    terrain_step = _completed_step(
        "terrain",
        started_at=terrain_started,
        output_paths=list(terrain_paths.values()),
        metadata={"derivatives": sorted(terrain_paths)},
        callback=callback,
    )

    _notify(callback, "Extracting contours")
    contours_started = datetime.now(UTC)
    contours = extract_contours(
        original_dem.array,
        transform=original_dem.metadata.transform,
        interval_m=project.analysis_params.contour_interval_m,
        crs=original_dem.metadata.crs,
        nodata=original_dem.metadata.nodata,
        callback=callback,
    )
    # Label the contours once and reuse the result for both vector exports and
    # the interactive map, instead of relabelling (with a full GeoDataFrame
    # copy) three separate times.
    contours_labeled = _label_contours(contours)
    _write_contours(
        contours_labeled,
        geojson_path=paths["contours_geojson"],
        kml_path=paths["contours_kml"],
    )
    contours_step = _completed_step(
        "contours",
        started_at=contours_started,
        output_paths=[paths["contours_geojson"], paths["contours_kml"]],
        metadata={"contour_count": len(contours)},
        callback=callback,
    )
    return _NumpyTrackResult(
        terrain_step=terrain_step,
        hillshade_array=hillshade_array,
        contours=contours,
        contours_labeled=contours_labeled,
        contours_step=contours_step,
    )


_TERRAIN_DERIVATIVES = ("hillshade", "hillshade_multi", "slope", "curvature")


def _write_terrain_derivatives(
    original_dem: Any,
    paths: dict[str, Path],
    *,
    cache: _DemCache,
    callback: Callable[[str], None] | None = None,
) -> tuple[dict[str, Path], np.ndarray]:
    transform = original_dem.metadata.transform
    crs = original_dem.metadata.crs
    nodata = original_dem.metadata.nodata

    terrain_paths = {name: paths[name] for name in _TERRAIN_DERIVATIVES}
    if cache.reuse(*terrain_paths.values()):
        _notify(callback, "Reusing cached terrain derivatives")
        return terrain_paths, read_dem(terrain_paths["hillshade"]).array
    # Compute terrain derivatives in the DEM's native precision. A float32 tile
    # stays float32 through the whole derivative chain (and is written as
    # float32 below), so upcasting to float64 here only doubled memory and
    # arithmetic for no gain. Non-float inputs are promoted so NaN masking works.
    source = original_dem.array
    if np.issubdtype(source.dtype, np.floating):
        array = source.astype(source.dtype, copy=True)
    else:
        array = source.astype("float64")
    if nodata is not None:
        array[array == nodata] = np.nan

    derivatives = compute_terrain_derivatives(array, cell_size=transform)
    written: dict[str, Path] = {}
    hillshade_array: np.ndarray | None = None
    for name, values in derivatives.items():
        values_float32 = values.astype("float32")
        if name == "hillshade":
            hillshade_array = values_float32
        written[name] = save_geotiff(
            paths[name],
            values_float32,
            crs=crs,
            transform=transform,
            nodata=np.nan,
            dtype="float32",
        )
    assert hillshade_array is not None  # compute_terrain_derivatives always yields it
    return written, hillshade_array


def _fill_depressions_for_detection(
    original_dem: Any,
    *,
    dem_path: Path,
    output_path: Path,
    hydrology_backend: HydrologyBackend,
    callback: Callable[[str], None] | None,
    cache: _DemCache,
) -> Path:
    # The detection fill depends only on the DEM, so reuse it when the input is
    # unchanged instead of re-running WhiteboxTools FillDepressions.
    if cache.reuse(output_path):
        _notify(callback, "Reusing cached detection fill")
        return output_path
    # Remove stale output so WhiteboxTools doesn't reuse a cached file from
    # a previous run that may have had different DEM dimensions.
    output_path.unlink(missing_ok=True)
    try:
        return hydrology_backend.fill_depressions(
            dem_path,
            output_path,
            callback=callback,
        )
    except (RuntimeError, OSError) as exc:
        if callback is not None:
            callback(f"Whitebox FillDepressions failed; using Python fallback: {exc}")
        return _write_priority_flood_fill(original_dem, output_path)


def _write_priority_flood_fill(original_dem: Any, output_path: Path) -> Path:
    array = original_dem.array.astype("float64", copy=True)
    nodata = original_dem.metadata.nodata
    valid = np.isfinite(array)
    if nodata is not None:
        valid &= array != nodata

    filled = array.copy()
    visited = np.zeros(array.shape, dtype=bool)
    heap: list[tuple[float, int, int]] = []
    rows, cols = array.shape

    def push(row: int, col: int) -> None:
        if valid[row, col] and not visited[row, col]:
            visited[row, col] = True
            heapq.heappush(heap, (float(filled[row, col]), row, col))

    for row in range(rows):
        push(row, 0)
        push(row, cols - 1)
    for col in range(1, cols - 1):
        push(0, col)
        push(rows - 1, col)

    neighbours = ((-1, 0), (1, 0), (0, -1), (0, 1))
    while heap:
        elevation, row, col = heapq.heappop(heap)
        for drow, dcol in neighbours:
            next_row = row + drow
            next_col = col + dcol
            if not (0 <= next_row < rows and 0 <= next_col < cols):
                continue
            if visited[next_row, next_col] or not valid[next_row, next_col]:
                continue
            visited[next_row, next_col] = True
            next_elevation = max(float(array[next_row, next_col]), elevation)
            filled[next_row, next_col] = next_elevation
            heapq.heappush(heap, (next_elevation, next_row, next_col))

    if nodata is not None:
        filled = np.where(valid, filled, nodata)

    return save_geotiff(
        output_path,
        filled.astype("float32"),
        crs=original_dem.metadata.crs,
        transform=original_dem.metadata.transform,
        nodata=nodata,
        dtype="float32",
    )


# Streams are rendered as a decimated raster overlay, not vectorised. A fine
# (0.5 m) stream raster holds millions of stream pixels; ``shapes()`` would emit
# a polygon per pixel and inflate the map's inline GeoJSON to hundreds of MB —
# the exact failure that left the map blank. Max-pooling the mask keeps the
# one-pixel-wide stream lines visible after decimation.
_STREAM_OVERLAY_MAX_PX = 2048
# Cyan (central palette) — kept clear of the muted ``>250m`` doline blue.
_STREAM_RGBA: tuple[int, int, int, int] = map_palette.STREAMS_RGBA


def _max_pool_or(mask: np.ndarray, factor: int) -> np.ndarray:
    """Downsample a boolean mask by ``factor`` keeping any True cell in each block."""
    if factor <= 1:
        return mask
    height, width = mask.shape
    pooled = np.zeros((-(-height // factor), -(-width // factor)), dtype=bool)
    for dy in range(factor):
        for dx in range(factor):
            sub = mask[dy::factor, dx::factor]
            pooled[: sub.shape[0], : sub.shape[1]] |= sub
    return pooled


def _streams_overlay(
    streams_path: Path, *, bounds: list[list[float]]
) -> ImageLayerSpec | None:
    """Build a decimated RGBA stream overlay, or ``None`` when there are no streams."""
    streams = read_dem(streams_path)
    array = streams.array
    mask = np.isfinite(array) & (array > 0)
    if streams.metadata.nodata is not None and np.isfinite(streams.metadata.nodata):
        mask &= array != streams.metadata.nodata
    if not mask.any():
        return None

    longest = max(mask.shape)
    factor = 1
    if longest > _STREAM_OVERLAY_MAX_PX:
        factor = int(np.ceil(longest / _STREAM_OVERLAY_MAX_PX))
    mask = _max_pool_or(mask, factor)

    rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
    rgba[mask] = _STREAM_RGBA
    return ImageLayerSpec("Streams", rgba, bounds=bounds, opacity=0.9, show=False)


def _imported_marker_layers(
    project: ProjectFile, *, marker_colors: dict[str, str] | None = None
) -> list[MapLayerSpec]:
    overrides = marker_colors or {}
    layers: list[MapLayerSpec] = []
    for marker_path in project.marker_paths:
        if not marker_path.exists():
            continue
        try:
            suffix = marker_path.suffix.lower()
            if suffix == ".gpx":
                markers = read_gpx_waypoints(marker_path)
            elif suffix == ".kml":
                markers = read_kml_geometries(marker_path)
            else:
                continue
        except Exception:  # noqa: BLE001 - skip unreadable marker files silently
            continue
        if markers.empty:
            continue
        color = imported_marker_color(marker_path.name, overrides)
        layers.append(
            MapLayerSpec(
                name=marker_path.stem,
                data=markers,
                show=True,
                style={"color": color, "fillColor": color, "weight": 3},
            )
        )
    return layers


def _load_project_profile(project: ProjectFile) -> LandProfile | None:
    try:
        return load_land_profile(project.land_profile, fallback=True)
    except Exception:  # noqa: BLE001
        return None


def _profile_tile_url(profile: LandProfile | None) -> str:
    """Return a Folium tiles string from the profile's first XYZ tile layer.

    WMTS and WMS layers require API keys or custom setup — skip them and use
    the first plain tile layer instead. Falls back to OpenStreetMap.
    """
    if profile is None:
        return "OpenStreetMap"
    from karstlab.data.schemas import LayerType

    for layer in profile.map_layers.base:
        if layer.type == LayerType.TILE:
            return _folium_tile_url(str(layer.url))
    return "OpenStreetMap"


def _folium_tile_url(url: str) -> str:
    return url.replace("%7B", "{").replace("%7D", "}").replace("%7b", "{").replace("%7d", "}")


def _profile_tile_attribution(profile: LandProfile | None) -> str | None:
    if profile is None:
        return None
    from karstlab.data.schemas import LayerType

    for layer in profile.map_layers.base:
        if layer.type == LayerType.TILE:
            return layer.attribution
    return None


def _profile_extra_tile_layers(profile: LandProfile | None) -> list[TileLayerSpec]:
    """Build extra XYZ basemaps from the region's tile layers (skip the primary).

    Only ``tile`` layers with an XYZ template are usable as Folium basemaps;
    ``wmts`` endpoints require keys/custom matrix sets and are skipped (the
    same rule ``_profile_tile_url`` applies).
    """
    if profile is None:
        return []
    from karstlab.data.schemas import LayerType

    tile_layers = [layer for layer in profile.map_layers.base if layer.type == LayerType.TILE]
    # First tile layer is rendered as the primary base map via `tiles=`.
    return [
        TileLayerSpec(name=layer.name, url=str(layer.url), attribution=layer.attribution or "")
        for layer in tile_layers[1:]
    ]


def _bounds_in_crs(
    bounds: tuple[float, float, float, float], src_crs: str, dst_crs: str
) -> tuple[float, float, float, float]:
    """Reproject an (xmin, ymin, xmax, ymax) extent between CRSs (corner-sampled)."""
    if src_crs == dst_crs:
        return bounds
    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    left, bottom, right, top = bounds
    xs: list[float] = []
    ys: list[float] = []
    for x, y in [(left, bottom), (right, bottom), (right, top), (left, top)]:
        tx, ty = transformer.transform(x, y)
        xs.append(tx)
        ys.append(ty)
    return (min(xs), min(ys), max(xs), max(ys))


def _annotate_fault_distances(
    depressions: list[DepressionResult],
    project: ProjectFile,
    *,
    callback: Callable[[str], None] | None = None,
) -> tuple[list[DepressionResult], Any]:
    """Attach distance/orientation-to-nearest-fault when a fault dataset is set.

    Returns ``(depressions, fault_lines)`` where ``fault_lines`` is the loaded
    GeoDataFrame (for the map fault layer) or ``None``. Best-effort: a
    missing/unreadable fault file leaves the depressions unchanged and never
    blocks the analysis.
    """
    if project.fault_lines_path is None or not depressions:
        return depressions, None
    from karstlab.business.faults import (
        annotate_fault_distances,
        caveline_bearing,
        load_fault_lines,
    )

    _notify(callback, "Computing distance to faults")
    faults = load_fault_lines(project.fault_lines_path)
    if faults is None or faults.empty:
        _notify(callback, "Fault dataset unavailable; skipping distance-to-fault")
        return depressions, None
    cave_bearing = _caveline_bearing(project, caveline_bearing)
    annotated = annotate_fault_distances(depressions, faults, cave_bearing=cave_bearing)
    note = f"({len(faults)} fault lines"
    note += f", cave line {cave_bearing:.0f}°)" if cave_bearing is not None else ")"
    _notify(callback, f"Distance to faults computed {note}")
    return annotated, faults


# ─── Conduit projection (optional: requires a known cave-survey line) ──────────
_CONDUIT_MAP_CANDIDATES = 10  # top corridor-ranked dolines marked on the map


def _load_caveline(path: Path, *, downstream_end: str = "first") -> Any:
    """Load a known cave-survey line (GPX/KML) as one WGS84 LineString.

    A clean, end-to-end survey goes through :func:`survey_line_geometry`. Real
    cave surveys are usually branching networks of disjoint legs (the combined
    Fourbanne/En-Versenne KML has ~185), which that strict extractor rejects — so
    we fall back to stitching what connects and taking the longest passage.
    ``downstream_end`` ("first"/"last") selects which end the corridor projects
    FROM, letting the operator flip the projection sense.
    """
    end: Literal["first", "last"] = "last" if downstream_end == "last" else "first"
    frame = read_gpx_track(path) if path.suffix.lower() == ".gpx" else read_kml_geometries(path)
    lines = frame[frame.geometry.geom_type == "LineString"]
    if not lines.empty:
        try:
            return survey_line_geometry(lines, downstream_end=end)
        except ValueError:
            return _longest_connected_line(lines, downstream_end=end)
    # No centreline geometry: some surveys are drawn as passage-footprint polygons
    # (the Fourbanne KML is 44). Derive the dominant trend axis as the caveline.
    return _caveline_principal_axis(frame, downstream_end=end)


def _longest_connected_line(frame: gpd.GeoDataFrame, *, downstream_end: str) -> Any:
    """Stitch connected survey legs and return the longest passage as one LineString."""
    from shapely.geometry import LineString
    from shapely.ops import linemerge

    merged = linemerge(list(frame.geometry))
    line = (
        max(merged.geoms, key=lambda g: g.length)
        if merged.geom_type == "MultiLineString"
        else merged
    )
    coords = list(line.coords)
    if downstream_end == "last":
        coords = coords[::-1]
    return LineString(coords)


def _survey_vertices(frame: gpd.GeoDataFrame) -> list[tuple[float, float]]:
    """Collect all WGS84 (lon, lat) vertices from polygon/point survey geometry."""
    coords: list[tuple[float, float]] = []
    for geom in frame.geometry:
        if geom is None:
            continue
        if geom.geom_type == "Polygon":
            coords.extend((x, y) for x, y, *_ in geom.exterior.coords)
        elif geom.geom_type == "MultiPolygon":
            coords.extend((x, y) for g in geom.geoms for x, y, *_ in g.exterior.coords)
        elif geom.geom_type == "Point":
            coords.append((geom.x, geom.y))
    return coords


def _caveline_principal_axis(frame: gpd.GeoDataFrame, *, downstream_end: str) -> Any:
    """Approximate a caveline as the dominant trend axis of a footprint-polygon survey.

    Surveys drawn as passage footprints (polygons) carry no centreline, but their
    vertices still encode the main trend. We take the principal axis (longitude
    scaled by cos(latitude) so the PCA is not skewed by the lon/lat aspect ratio)
    and return the segment between its extreme projections — a clean terminus +
    heading proxy for the corridor model.
    """
    from shapely.geometry import LineString

    coords = _survey_vertices(frame)
    if len(coords) < 2:
        raise ValueError("survey geometry has too few vertices for a caveline")
    arr = np.asarray(coords, dtype=float)
    mean = arr.mean(axis=0)
    coslat = float(np.cos(np.radians(mean[1]))) or 1.0
    scaled = (arr - mean) * np.array([coslat, 1.0])
    _u, _s, vh = np.linalg.svd(scaled, full_matrices=False)
    axis = vh[0]
    proj = scaled @ axis
    unscale = np.array([1.0 / coslat, 1.0])
    low = mean + (axis * float(proj.min())) * unscale
    high = mean + (axis * float(proj.max())) * unscale
    ends = [tuple(low), tuple(high)]
    if downstream_end == "last":
        ends.reverse()
    return LineString(ends)


def _marker_target_points(project: ProjectFile) -> list[Any]:
    """Imported marker Points (WGS84) reused as conduit targets when none are set."""
    from shapely.geometry import Point

    points: list[Any] = []
    for path in project.marker_paths:
        try:
            frame = (
                read_gpx_waypoints(path)
                if path.suffix.lower() == ".gpx"
                else read_kml_geometries(path)
            )
        except Exception as exc:
            logger.warning("Skipping marker file %s for conduit targets: %s", path, exc)
            continue
        points.extend(
            Point(geom.x, geom.y)
            for geom in frame.geometry
            if geom is not None and geom.geom_type == "Point"
        )
    return points


def _run_conduit_stage(
    project: ProjectFile,
    depressions: list[DepressionResult],
    paths: dict[str, Path],
    *,
    callback: Callable[[str], None] | None,
) -> tuple[dict[str, Any] | None, Path | None, list[DepressionResult]]:
    """Optional conduit stage: doline alignment → corridor likelihood → backtest.

    Runs only when the project carries a known cave-survey line. Returns
    ``(summary, contours_path, candidate_dolines)`` for the map + provenance, or
    ``(None, None, [])`` when skipped.
    """
    if project.caveline_path is None:
        return None, None, []
    if not depressions:
        logger.warning("Conduit projection skipped: no depressions detected")
        return None, None, []

    # why: conduit projection is an optional, best-effort enrichment — a bad survey
    # file or degenerate geometry must not abort the core doline analysis.
    try:
        from shapely.geometry import Point

        from karstlab.business.alignment import detect_doline_alignment
        from karstlab.business.conduit import project_conduit

        _notify(callback, "Projecting conduit corridor")
        caveline = _load_caveline(
            project.caveline_path, downstream_end=project.caveline_downstream_end
        )
        rosettes = detect_doline_alignment(
            depressions, crs=project.crs_analysis, rosette_dir=paths["rosette_dir"]
        )
        # Explicit targets win; otherwise reuse imported marker points (e.g. a
        # neighbouring cave entrance) so the heading can bend toward them.
        target_list = [Point(c.lon, c.lat) for c in project.conduit_target_points]
        if not target_list:
            target_list = _marker_target_points(project)
        targets = target_list or None
        conduit = project_conduit(
            caveline,
            depressions,
            rosettes,
            crs=project.crs_analysis,
            output_dir=project.output_dir,
            slug=project.slug,
            target_points=targets,
        )
    except Exception as exc:
        logger.warning("Conduit projection skipped: %s", exc, exc_info=True)
        return None, None, []

    candidates = conduit.candidates[:_CONDUIT_MAP_CANDIDATES]
    summary: dict[str, Any] = {
        "heading_deg": round(conduit.heading_deg, 1),
        "heading_provenance": {
            "conduit_component_deg": round(conduit.heading_provenance.conduit_component_deg, 1),
            "alignment_component_deg": conduit.heading_provenance.alignment_component_deg,
            "target_component_deg": conduit.heading_provenance.target_component_deg,
        },
        "candidates": [
            {"id": c.depression.id, "rank": c.rank, "corridor_score": round(c.corridor_score, 4)}
            for c in candidates
        ],
        "raster": str(conduit.raster_path),
        "contours": str(conduit.contours_path),
        "barriers_applied": conduit.barriers_applied,
    }

    # Backtest validates the model against the known survey; also optional.
    try:
        from karstlab.business.backtest import run_backtest

        _notify(callback, "Backtesting conduit model")
        backtest = run_backtest(
            caveline,
            depressions,
            rosettes,
            crs=project.crs_analysis,
            output_dir=project.output_dir,
            slug=project.slug,
            target_points=targets,
        )
        summary["backtest"] = {
            "is_sufficient": backtest.is_sufficient,
            "insufficiency_reason": backtest.insufficiency_reason,
            "valid_splits": len(backtest.valid_splits),
            "report": str(backtest.report_path),
            "figure": str(backtest.figure_path) if backtest.figure_path else None,
        }
    except Exception as exc:
        logger.warning("Conduit backtest skipped: %s", exc, exc_info=True)

    return summary, conduit.contours_path, [c.depression for c in candidates]


def _load_conduit_geojson(path: Path | None) -> dict[str, Any] | None:
    """Read the conduit corridor isolines (already WGS84) for the interactive map."""
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _faults_geojson(
    fault_lines: Any, *, dem_bounds: tuple[float, float, float, float], dem_crs: str
) -> dict[str, Any] | None:
    """Build the WGS84 fault-line GeoJSON for the map (clipped to the DEM extent).

    Distance analysis uses every fault; the map layer only needs the faults in/near
    the analysis area, so clip to the DEM bbox to keep the document small.
    """
    if fault_lines is None or fault_lines.empty:
        return None
    from karstlab.business.faults import faults_to_geojson

    xmin, ymin, xmax, ymax = _bounds_in_crs(dem_bounds, dem_crs, "EPSG:2154")
    clipped = fault_lines.cx[xmin:xmax, ymin:ymax]
    if clipped.empty:
        return None
    return faults_to_geojson(clipped)


def _caveline_bearing(
    project: ProjectFile, bearing_fn: Callable[[Any], float | None]
) -> float | None:
    """Folded bearing of the imported cave line (first marker file with lines)."""
    for marker_path in project.marker_paths:
        if marker_path.suffix.lower() != ".kml" or not marker_path.exists():
            continue
        try:
            lines = read_kml_geometries(marker_path)
        except Exception:  # noqa: BLE001 - skip unreadable marker file
            continue
        line_only = lines[lines.geom_type.isin(["LineString", "MultiLineString"])]
        bearing = bearing_fn(line_only)
        if bearing is not None:
            return bearing
    return None


def fetch_vector_overlay(
    vec: VectorLayerConfig,
    *,
    dem_bounds: tuple[float, float, float, float],
    dem_crs: str,
    cache_dir: Path | None,
    callback: Callable[[str], None] | None = None,
) -> dict[str, Any] | None:
    """Fetch one WFS vector overlay as a WGS84 GeoJSON dict (bbox = DEM extent).

    Server-side, bbox-limited, never raises. Shared by the baked-overlay path and
    the on-demand GUI fetch so both behave identically.
    """
    from karstlab.data.geodata_service import fetch_wfs_geojson

    bbox = _bounds_in_crs(dem_bounds, dem_crs, vec.srs) if vec.bbox_filter else None
    _notify(callback, f"Fetching {vec.name}")
    return fetch_wfs_geojson(
        base_url=str(vec.url),
        typename=vec.typename,
        version=vec.version,
        output_format=vec.output_format,
        srs=vec.srs,
        bbox=bbox,
        bbox_srs=vec.srs,
        max_features=vec.max_features,
        cql_filter=vec.cql_filter,
        geometry_name=vec.geometry_name,
        cache_dir=cache_dir,
    )


def _profile_vector_overlays(
    profile: LandProfile | None,
    *,
    dem_bounds: tuple[float, float, float, float],
    dem_crs: str,
    cache_dir: Path,
    callback: Callable[[str], None] | None = None,
) -> list[MapLayerSpec]:
    """Fetch the profile's bakeable WFS vector overlays as map layers (best-effort)."""
    if profile is None:
        return []
    specs: list[MapLayerSpec] = []
    for vec in profile.map_layers.vector_overlays:
        if not vec.bake:
            continue
        collection = fetch_vector_overlay(
            vec, dem_bounds=dem_bounds, dem_crs=dem_crs, cache_dir=cache_dir, callback=callback
        )
        if not collection or not collection.get("features"):
            _notify(callback, f"{vec.name}: no data (skipped)")
            continue
        specs.append(
            MapLayerSpec(
                name=vec.name,
                data=collection,
                show=False,
                style=vec.style or {"color": map_palette.VECTOR_OVERLAY_DEFAULT, "weight": 2},
            )
        )
    return specs


def _profile_wms_layers(profile: LandProfile | None) -> list[WmsLayerSpec]:
    if profile is None:
        return []
    from karstlab.data.schemas import LayerType

    return [
        WmsLayerSpec(
            name=layer.name,
            url=str(layer.url),
            layers=layer.layer or "",
            attribution=layer.attribution or "",
            opacity=layer.opacity if layer.opacity is not None else 0.6,
        )
        for layer in profile.map_layers.overlays
        if layer.type == LayerType.WMS and layer.layer
    ]


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


# Human labels for the per-phase timing readout (the step_ids themselves are
# machine identifiers). Used for both the live "✓ done" lines and the final
# breakdown so the user can see exactly where a long run spends its time.
_STEP_LABELS: dict[str, str] = {
    "vrt_assembly": "Assemble tiles",
    "read_dem": "Read DEM",
    "terrain": "Terrain derivatives",
    "contours": "Contours",
    "hydrology": "Hydrology (Whitebox)",
    "depression_fill": "Fill depressions",
    "doline_detection": "Detect dolines",
    "exports": "Write exports",
    "interactive_map": "Render map",
    "report": "Write report",
}


def _seconds_between(started_at: datetime | None, finished_at: datetime | None) -> float:
    if started_at is None or finished_at is None:
        return 0.0
    return (finished_at - started_at).total_seconds()


def _completed_step(
    step_id: str,
    *,
    started_at: datetime,
    output_paths: list[Path],
    metadata: dict[str, Any] | None = None,
    callback: Callable[[str], None] | None = None,
) -> PipelineStepResult:
    finished_at = datetime.now(UTC)
    step = PipelineStepResult(
        step_id=step_id,
        status=PipelineStatus.SUCCESS,
        started_at=started_at,
        finished_at=finished_at,
        output_paths=output_paths,
        metadata=metadata or {},
    )
    if callback is not None:
        label = _STEP_LABELS.get(step_id, step_id)
        _notify(callback, f"✓ {label} ({_seconds_between(started_at, finished_at):.1f}s)")
    return step


def _emit_timing_summary(
    callback: Callable[[str], None] | None,
    steps: list[PipelineStepResult],
    *,
    total_started: datetime,
    total_finished: datetime,
) -> None:
    """Emit a slowest-first per-phase timing breakdown through the callback.

    The NumPy and WhiteboxTools tracks overlap, so individual phase durations
    can sum to more than the wall-clock total; the breakdown is for spotting the
    dominant phase, not for exact accounting.
    """
    if callback is None:
        return
    rows = sorted(
        (
            (
                _STEP_LABELS.get(step.step_id, step.step_id),
                _seconds_between(step.started_at, step.finished_at),
            )
            for step in steps
        ),
        key=lambda row: row[1],
        reverse=True,
    )
    total = _seconds_between(total_started, total_finished)
    _notify(callback, f"Timing breakdown (wall-clock {total:.1f}s):")
    for label, seconds in rows:
        share = f" ({seconds / total * 100:.0f}%)" if total > 0 else ""
        _notify(callback, f"  {label}: {seconds:.1f}s{share}")


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


# Vertex-simplification tolerance (CRS units, i.e. metres for projected DEMs)
# for the interactive-map contour layer only. The full-resolution contours are
# still written to GeoJSON/KML; this just keeps the inline map layer small so
# the HTML stays light and loads quickly even with a fine (1 m) interval.
_MAP_CONTOUR_SIMPLIFY_TOLERANCE = 3.0


def _simplify_for_map(contours: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return a vertex-thinned, WGS84 copy of the contours for the interactive map.

    Simplification runs in the source (projected, metric) CRS so the tolerance is
    in metres, then the result is reprojected to WGS84 — Leaflet expects lat/lon
    and would otherwise plot metric coordinates far outside the visible extent.
    """
    if contours.empty:
        return contours
    simplified = contours.copy()
    simplified["geometry"] = simplified.geometry.simplify(
        _MAP_CONTOUR_SIMPLIFY_TOLERANCE, preserve_topology=False
    )
    return to_wgs84(simplified)


def _write_contours(
    labeled_contours: gpd.GeoDataFrame, *, geojson_path: Path, kml_path: Path
) -> None:
    """Write already-labelled contours to GeoJSON and KML.

    The caller is responsible for labelling (via :func:`_label_contours`) so the
    label column is computed a single time and shared with the interactive map.
    """
    to_geojson(labeled_contours, geojson_path)
    to_kml(labeled_contours, kml_path)


__all__ = ["run_headless_analysis"]
