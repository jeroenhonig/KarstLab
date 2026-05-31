"""Conduit prediction corridor.

Predicts a karst conduit continuation as a *relative model likelihood*
corridor downstream of a known cave survey. The output is NOT a calibrated
probability: values are a fixed analytical model field normalised to a peak of
1.0 at the survey terminus. All user-facing labels and exports must say
"relative model likelihood", never "probability" and never "50%/80%/95%".

Geometry convention: every geometric input is WGS84; all analytical
computation happens after reprojection to the metric analysis CRS via the
shared helpers in ``data/crs.py``. GeoTIFF output is written in the analysis
CRS; the contour GeoJSON is written in WGS84 (RFC 7946).

Line barriers: shapely 2.x geometries are immutable and cannot carry the
``blocked_side_point`` attribute the original plan described, so line barriers
are passed as :class:`LineBarrier` instances (WGS84 line + WGS84 reference
point marking the blocked side). Polygon barriers are passed as plain shapely
geometries.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import shapely.geometry
from affine import Affine
from numpy.typing import NDArray
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely.ops import substring
from skimage.measure import find_contours

from karstlab.business.alignment import AlignmentMode, RosetteResult
from karstlab.data.crs import (
    fold_bearing,
    is_metric_crs,
    project_geometry,
    unproject_geometry,
)
from karstlab.data.project_io import canonical_output_paths
from karstlab.data.raster_io import save_geotiff
from karstlab.data.schemas import DepressionResult, PipelineResult, ProjectFile


@dataclass(frozen=True)
class ConduitProjectionParams:
    sigma_m: float = 500.0
    decay_lambda: float = 0.001
    max_projection_distance_m: float = 5000.0
    raster_resolution_m: float = 10.0
    isoline_values: tuple[float, ...] = (0.5, 0.2, 0.05)
    terminal_length_m: float = 200.0
    override_heading_deg: float | None = None
    heading_angle_tolerance_deg: float = 40.0
    conduit_weight: float = 0.6
    alignment_weight: float = 0.25
    target_weight: float = 0.15
    barrier_line_buffer_m: float = 0.0


@dataclass(frozen=True)
class LineBarrier:
    """A WGS84 line barrier with a reference point on the blocked side.

    Corridor cells that fall on the same side of ``line`` as
    ``blocked_side_point`` are masked to 0.0.
    """

    line: shapely.geometry.LineString
    blocked_side_point: shapely.geometry.Point


@dataclass(frozen=True)
class HeadingProvenance:
    combined_deg: float
    conduit_component_deg: float
    conduit_was_overridden: bool
    alignment_component_deg: float | None
    target_component_deg: float | None
    target_point_used: shapely.geometry.Point | None
    weights: tuple[float, float, float]


@dataclass(frozen=True)
class CandidateEntrance:
    depression: DepressionResult
    corridor_score: float
    rank: int


@dataclass(frozen=True)
class ConduitProjectionResult:
    candidates: list[CandidateEntrance]
    raster_path: Path
    contours_path: Path
    heading_deg: float
    heading_provenance: HeadingProvenance
    alignment_modes_used: list[AlignmentMode]
    barriers_applied: int
    barrier_paths: tuple[Path, ...]


def corridor_field_value(
    d_along: np.ndarray | float,
    d_perp: np.ndarray | float,
    params: ConduitProjectionParams,
) -> np.ndarray:
    """Continuous corridor field, normalised to a peak of 1.0 at the terminus.

    ``p = exp(-0.5 * (d_perp / sigma)^2) * exp(-decay_lambda * d_along)`` for
    ``0 <= d_along <= max_projection_distance_m``; 0 elsewhere.
    """
    along = np.asarray(d_along, dtype=np.float64)
    perp = np.asarray(d_perp, dtype=np.float64)
    value = np.exp(-0.5 * (perp / params.sigma_m) ** 2) * np.exp(
        -params.decay_lambda * along
    )
    in_range = (along >= 0.0) & (along <= params.max_projection_distance_m)
    return np.where(in_range, value, 0.0)


@dataclass(frozen=True)
class CorridorContext:
    """Reusable heading + field-evaluation context for a known caveline.

    Encapsulates the projection terminus, forward/perp unit vectors, barriers,
    and heading provenance so callers (``project_conduit`` and
    ``business/backtest.py``) share one analytical field instead of
    re-deriving heading or re-implementing the field formula.
    """

    terminus: np.ndarray
    forward: np.ndarray
    perp: np.ndarray
    crs: CRS | str
    params: ConduitProjectionParams
    barriers: list[tuple[str, Any]]
    heading_provenance: HeadingProvenance

    def along_perp(self, coords_metric: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        rel = np.asarray(coords_metric, dtype=np.float64) - self.terminus
        d_along = rel[:, 0] * self.forward[0] + rel[:, 1] * self.forward[1]
        d_perp = rel[:, 0] * self.perp[0] + rel[:, 1] * self.perp[1]
        return d_along, d_perp

    def field_at_metric(self, coords_metric: np.ndarray) -> np.ndarray:
        coords = np.asarray(coords_metric, dtype=np.float64)
        if coords.size == 0:
            return np.asarray([], dtype=np.float64)
        d_along, d_perp = self.along_perp(coords)
        values = corridor_field_value(d_along, d_perp, self.params)
        if self.barriers:
            for index, row in enumerate(coords):
                if _point_blocked(
                    row, self.barriers, buffer_m=self.params.barrier_line_buffer_m
                ):
                    values[index] = 0.0
        return values

    def field_at_wgs84(self, points: list[shapely.geometry.Point]) -> np.ndarray:
        if not points:
            return np.asarray([], dtype=np.float64)
        coords = np.asarray(
            [project_geometry(point, crs=self.crs).coords[0][:2] for point in points],
            dtype=np.float64,
        )
        return self.field_at_metric(coords)


def corridor_axis(
    known_caveline: shapely.geometry.LineString,
    rosette_results: list[RosetteResult],
    *,
    crs: CRS | str,
    target_points: list[shapely.geometry.Point] | None = None,
    barrier_geometries: list[shapely.geometry.base.BaseGeometry | LineBarrier] | None = None,
    params: ConduitProjectionParams | None = None,
) -> CorridorContext:
    """Derive the heading + field context for ``known_caveline`` (WGS84)."""
    resolved = params or ConduitProjectionParams()
    if not is_metric_crs(crs):
        raise ValueError(f"crs is not metric: {crs}")

    proj_line = project_geometry(known_caveline, crs=crs)
    terminus = np.asarray(proj_line.coords[-1][:2], dtype=np.float64)
    projected_targets = _project_targets(target_points, crs=crs)
    provenance, forward = _derive_heading(
        proj_line,
        terminus=terminus,
        rosette_results=rosette_results,
        projected_targets=projected_targets,
        original_targets=target_points or [],
        params=resolved,
    )
    perp = np.array([-forward[1], forward[0]], dtype=np.float64)
    barriers = _project_barriers(barrier_geometries or [], crs=crs)
    return CorridorContext(
        terminus=terminus,
        forward=forward,
        perp=perp,
        crs=crs,
        params=resolved,
        barriers=barriers,
        heading_provenance=provenance,
    )


def project_conduit(
    known_caveline: shapely.geometry.LineString,
    depressions: list[DepressionResult],
    rosette_results: list[RosetteResult],
    *,
    crs: CRS | str,
    output_dir: Path,
    slug: str,
    target_points: list[shapely.geometry.Point] | None = None,
    barrier_geometries: list[shapely.geometry.base.BaseGeometry | LineBarrier] | None = None,
    barrier_source_paths: tuple[Path, ...] = (),
    params: ConduitProjectionParams | None = None,
) -> ConduitProjectionResult:
    """Predict a karst conduit continuation as a relative likelihood corridor."""
    resolved = params or ConduitProjectionParams()
    context = corridor_axis(
        known_caveline,
        rosette_results,
        crs=crs,
        target_points=target_points,
        barrier_geometries=barrier_geometries,
        params=resolved,
    )
    terminus = context.terminus
    forward = context.forward
    perp = context.perp
    provenance = context.heading_provenance
    barriers = context.barriers

    field, transform, width, height = _build_field(
        terminus=terminus,
        forward=forward,
        perp=perp,
        params=resolved,
    )
    field = _apply_barriers(
        field,
        transform=transform,
        width=width,
        height=height,
        barriers=barriers,
        buffer_m=resolved.barrier_line_buffer_m,
    )

    raster_path = output_dir / "rasters" / "conduit_probability.tif"
    save_geotiff(
        raster_path,
        field.astype("float32"),
        crs=crs,
        transform=transform,
        nodata=None,
        dtype="float32",
    )

    contours_path = output_dir / "export" / f"conduit_contours_{slug}.geojson"
    _write_contours(
        field,
        transform=transform,
        crs=crs,
        isoline_values=resolved.isoline_values,
        output_path=contours_path,
    )

    candidates = _score_candidates(
        depressions,
        crs=crs,
        terminus=terminus,
        forward=forward,
        perp=perp,
        barriers=barriers,
        buffer_m=resolved.barrier_line_buffer_m,
        params=resolved,
    )

    matched_mode = _mode_by_index(rosette_results, provenance.alignment_component_deg)
    alignment_modes_used = [matched_mode] if matched_mode is not None else []

    return ConduitProjectionResult(
        candidates=candidates,
        raster_path=raster_path,
        contours_path=contours_path,
        heading_deg=provenance.combined_deg,
        heading_provenance=provenance,
        alignment_modes_used=alignment_modes_used,
        barriers_applied=len(barriers),
        barrier_paths=tuple(barrier_source_paths),
    )


def run_conduit_analysis(
    project: ProjectFile,
    known_caveline: shapely.geometry.LineString,
    rosette_results: list[RosetteResult],
    prior_pipeline_result: PipelineResult,
    *,
    target_points: list[shapely.geometry.Point] | None = None,
    barrier_geometries: list[shapely.geometry.base.BaseGeometry | LineBarrier] | None = None,
    barrier_source_paths: tuple[Path, ...] = (),
    params: ConduitProjectionParams | None = None,
) -> ConduitProjectionResult:
    """Orchestrate conduit analysis on doline results from a prior DEM run.

    Does NOT re-run doline detection: it reuses
    ``prior_pipeline_result.depressions`` verbatim.
    """
    if not prior_pipeline_result.depressions:
        raise ValueError("prior_pipeline_result.depressions must be non-empty")

    paths = canonical_output_paths(project)
    raster_path = paths["conduit_probability"]
    contours_path = paths["conduit_contours"]

    result = project_conduit(
        known_caveline,
        prior_pipeline_result.depressions,
        rosette_results,
        crs=project.crs_analysis,
        output_dir=project.output_dir,
        slug=project.slug,
        target_points=target_points,
        barrier_geometries=barrier_geometries,
        barrier_source_paths=barrier_source_paths,
        params=params,
    )
    # canonical_output_paths is the single source of truth for these paths;
    # project_conduit derives the same locations from output_dir/slug.
    assert result.raster_path == raster_path
    assert result.contours_path == contours_path
    return result


def _derive_heading(
    proj_line: shapely.geometry.LineString,
    *,
    terminus: np.ndarray,
    rosette_results: list[RosetteResult],
    projected_targets: list[np.ndarray],
    original_targets: list[shapely.geometry.Point],
    params: ConduitProjectionParams,
) -> tuple[HeadingProvenance, np.ndarray]:
    terminal_forward = _terminal_forward_vector(proj_line, params.terminal_length_m)
    terminal_az = _vector_azimuth(terminal_forward)

    override = params.override_heading_deg
    conduit_overridden = override is not None
    conduit_axial = fold_bearing(override) if override is not None else fold_bearing(terminal_az)

    alignment_axial = _alignment_component(
        rosette_results,
        reference_axial=conduit_axial,
        tolerance_deg=params.heading_angle_tolerance_deg,
    )

    target_axial, target_point = _target_component(
        projected_targets,
        original_targets,
        terminus=terminus,
        reference_axial=conduit_axial,
        tolerance_deg=params.heading_angle_tolerance_deg,
    )

    components: list[tuple[float, float]] = [(conduit_axial, params.conduit_weight)]
    weight_alignment = 0.0
    weight_target = 0.0
    if alignment_axial is not None:
        components.append((alignment_axial, params.alignment_weight))
        weight_alignment = params.alignment_weight
    if target_axial is not None:
        components.append((target_axial, params.target_weight))
        weight_target = params.target_weight

    total_weight = params.conduit_weight + weight_alignment + weight_target
    weights = (
        params.conduit_weight / total_weight,
        weight_alignment / total_weight,
        weight_target / total_weight,
    )

    combined_axial = _weighted_axial_mean(components)
    forward = _orient_axial(combined_axial, terminal_forward)

    provenance = HeadingProvenance(
        combined_deg=combined_axial,
        conduit_component_deg=conduit_axial,
        conduit_was_overridden=conduit_overridden,
        alignment_component_deg=alignment_axial,
        target_component_deg=target_axial,
        target_point_used=target_point,
        weights=weights,
    )
    return provenance, forward


def _terminal_forward_vector(
    proj_line: shapely.geometry.LineString, terminal_length_m: float
) -> np.ndarray:
    total = proj_line.length
    start = max(0.0, total - terminal_length_m)
    segment = substring(proj_line, start, total)
    coords = list(segment.coords)
    if len(coords) < 2:
        coords = list(proj_line.coords)
    p0 = np.asarray(coords[0][:2], dtype=np.float64)
    p1 = np.asarray(coords[-1][:2], dtype=np.float64)
    vec = p1 - p0
    norm = float(np.hypot(vec[0], vec[1]))
    if norm == 0.0:
        raise ValueError("known_caveline terminal segment has zero length")
    return vec / norm


def _vector_azimuth(vec: np.ndarray) -> float:
    return float((math.degrees(math.atan2(vec[0], vec[1])) + 360.0) % 360.0)


def _azimuth_unit(azimuth_deg: float) -> np.ndarray:
    rad = math.radians(azimuth_deg)
    return np.array([math.sin(rad), math.cos(rad)], dtype=np.float64)


def _axial_distance(a: float, b: float) -> float:
    diff = abs(a - b) % 180.0
    return min(diff, 180.0 - diff)


def _alignment_component(
    rosette_results: list[RosetteResult],
    *,
    reference_axial: float,
    tolerance_deg: float,
) -> float | None:
    best: AlignmentMode | None = None
    for rosette in rosette_results:
        for mode in rosette.modes:
            if _axial_distance(mode.azimuth_deg, reference_axial) > tolerance_deg:
                continue
            if best is None or mode.confidence > best.confidence:
                best = mode
    return None if best is None else float(best.azimuth_deg)


def _mode_by_index(
    rosette_results: list[RosetteResult], axial_deg: float | None
) -> AlignmentMode | None:
    if axial_deg is None:
        return None
    for rosette in rosette_results:
        for mode in rosette.modes:
            if abs(mode.azimuth_deg - axial_deg) < 1e-9:
                return mode
    return None


def _target_component(
    projected_targets: list[np.ndarray],
    original_targets: list[shapely.geometry.Point],
    *,
    terminus: np.ndarray,
    reference_axial: float,
    tolerance_deg: float,
) -> tuple[float | None, shapely.geometry.Point | None]:
    candidates: list[tuple[float, float, shapely.geometry.Point]] = []
    for projected, original in zip(projected_targets, original_targets, strict=True):
        vec = projected - terminus
        distance = float(np.hypot(vec[0], vec[1]))
        if distance == 0.0:
            continue
        axial = fold_bearing(_vector_azimuth(vec))
        if _axial_distance(axial, reference_axial) > tolerance_deg:
            continue
        candidates.append((distance, axial, original))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: item[0])
    _, axial, original = candidates[0]
    return axial, original


def _weighted_axial_mean(components: list[tuple[float, float]]) -> float:
    x = 0.0
    y = 0.0
    for axial, weight in components:
        rad = math.radians(2.0 * axial)
        x += weight * math.cos(rad)
        y += weight * math.sin(rad)
    angle = math.degrees(math.atan2(y, x)) / 2.0
    return float(angle % 180.0)


def _orient_axial(axial_deg: float, terminal_forward: np.ndarray) -> np.ndarray:
    option_a = _azimuth_unit(axial_deg)
    option_b = _azimuth_unit(axial_deg + 180.0)
    if float(np.dot(option_a, terminal_forward)) >= float(np.dot(option_b, terminal_forward)):
        return option_a
    return option_b


def _build_field(
    *,
    terminus: np.ndarray,
    forward: np.ndarray,
    perp: np.ndarray,
    params: ConduitProjectionParams,
) -> tuple[np.ndarray, Affine, int, int]:
    length = params.max_projection_distance_m
    half_width = 4.0 * params.sigma_m
    corners = np.array(
        [
            terminus + along * length * forward + side * half_width * perp
            for along in (0.0, 1.0)
            for side in (-1.0, 1.0)
        ],
        dtype=np.float64,
    )
    min_x = float(corners[:, 0].min())
    max_x = float(corners[:, 0].max())
    min_y = float(corners[:, 1].min())
    max_y = float(corners[:, 1].max())

    res = params.raster_resolution_m
    width = max(1, int(math.ceil((max_x - min_x) / res)))
    height = max(1, int(math.ceil((max_y - min_y) / res)))
    transform = from_origin(min_x, max_y, res, res)

    cols = np.arange(width, dtype=np.float64)
    rows = np.arange(height, dtype=np.float64)
    xs = min_x + (cols + 0.5) * res
    ys = max_y - (rows + 0.5) * res
    grid_x, grid_y = np.meshgrid(xs, ys)

    rel_x = grid_x - terminus[0]
    rel_y = grid_y - terminus[1]
    d_along = rel_x * forward[0] + rel_y * forward[1]
    d_perp = rel_x * perp[0] + rel_y * perp[1]

    field = corridor_field_value(d_along, d_perp, params)
    return field, transform, width, height


def _project_targets(
    target_points: list[shapely.geometry.Point] | None, *, crs: CRS | str
) -> list[np.ndarray]:
    if not target_points:
        return []
    projected = []
    for point in target_points:
        metric = project_geometry(point, crs=crs)
        projected.append(np.asarray(metric.coords[0][:2], dtype=np.float64))
    return projected


def _project_barriers(
    barriers: list[shapely.geometry.base.BaseGeometry | LineBarrier], *, crs: CRS | str
) -> list[tuple[str, Any]]:
    projected: list[tuple[str, Any]] = []
    for barrier in barriers:
        if isinstance(barrier, LineBarrier):
            line = project_geometry(barrier.line, crs=crs)
            ref = project_geometry(barrier.blocked_side_point, crs=crs)
            projected.append(("line", (line, ref)))
        elif barrier.geom_type in {"Polygon", "MultiPolygon"}:
            projected.append(("polygon", project_geometry(barrier, crs=crs)))
        else:
            raise ValueError(
                "line barriers must be passed as LineBarrier; "
                f"unsupported barrier geometry: {barrier.geom_type}"
            )
    return projected


def _apply_barriers(
    field: np.ndarray,
    *,
    transform: Affine,
    width: int,
    height: int,
    barriers: list[tuple[str, Any]],
    buffer_m: float,
) -> np.ndarray:
    if not barriers:
        return field

    masked = field.copy()
    cols = np.arange(width, dtype=np.float64)
    rows = np.arange(height, dtype=np.float64)
    res_x = transform.a
    res_y = -transform.e
    xs = transform.c + (cols + 0.5) * res_x
    ys = transform.f - (rows + 0.5) * res_y
    grid_x, grid_y = np.meshgrid(xs, ys)

    for kind, payload in barriers:
        if kind == "polygon":
            mask = rasterize(
                [(payload, 1)],
                out_shape=(height, width),
                transform=transform,
                fill=0,
                dtype="uint8",
            ).astype(bool)
            masked[mask] = 0.0
        else:
            line, ref = payload
            blocked = _halfplane_mask(grid_x, grid_y, line=line, ref_point=ref)
            masked[blocked] = 0.0
            if buffer_m > 0.0:
                near = _line_distance(grid_x, grid_y, line=line) <= buffer_m
                masked[near] = 0.0
    return masked


def _halfplane_mask(
    grid_x: np.ndarray,
    grid_y: np.ndarray,
    *,
    line: shapely.geometry.LineString,
    ref_point: shapely.geometry.Point,
) -> np.ndarray:
    p0 = np.asarray(line.coords[0][:2], dtype=np.float64)
    p1 = np.asarray(line.coords[-1][:2], dtype=np.float64)
    direction = p1 - p0
    cross = direction[0] * (grid_y - p0[1]) - direction[1] * (grid_x - p0[0])
    ref_cross = direction[0] * (ref_point.y - p0[1]) - direction[1] * (ref_point.x - p0[0])
    ref_sign = np.sign(ref_cross)
    if ref_sign == 0:
        return np.zeros(grid_x.shape, dtype=bool)
    return cast(NDArray[np.bool_], np.sign(cross) == ref_sign)


def _line_distance(
    grid_x: np.ndarray, grid_y: np.ndarray, *, line: shapely.geometry.LineString
) -> np.ndarray:
    coords = np.asarray(line.coords, dtype=np.float64)[:, :2]
    distance = np.full(grid_x.shape, np.inf, dtype=np.float64)
    for start, end in zip(coords[:-1], coords[1:], strict=True):
        distance = np.minimum(
            distance, _point_segment_distance(grid_x, grid_y, start, end)
        )
    return cast(NDArray[np.float64], distance)


def _point_segment_distance(
    grid_x: np.ndarray, grid_y: np.ndarray, start: np.ndarray, end: np.ndarray
) -> np.ndarray:
    seg = end - start
    seg_len_sq = float(seg[0] ** 2 + seg[1] ** 2)
    rel_x = grid_x - start[0]
    rel_y = grid_y - start[1]
    if seg_len_sq == 0.0:
        return cast(NDArray[np.float64], np.hypot(rel_x, rel_y))
    t = np.clip((rel_x * seg[0] + rel_y * seg[1]) / seg_len_sq, 0.0, 1.0)
    proj_x = start[0] + t * seg[0]
    proj_y = start[1] + t * seg[1]
    return cast(NDArray[np.float64], np.hypot(grid_x - proj_x, grid_y - proj_y))


def _point_blocked(
    point: np.ndarray, barriers: list[tuple[str, Any]], *, buffer_m: float
) -> bool:
    shapely_point = shapely.geometry.Point(float(point[0]), float(point[1]))
    for kind, payload in barriers:
        if kind == "polygon":
            if payload.contains(shapely_point):
                return True
        else:
            line, ref = payload
            p0 = np.asarray(line.coords[0][:2], dtype=np.float64)
            p1 = np.asarray(line.coords[-1][:2], dtype=np.float64)
            direction = p1 - p0
            cross = direction[0] * (point[1] - p0[1]) - direction[1] * (point[0] - p0[0])
            ref_cross = (
                direction[0] * (ref.y - p0[1]) - direction[1] * (ref.x - p0[0])
            )
            if np.sign(cross) != 0 and np.sign(cross) == np.sign(ref_cross):
                return True
            if buffer_m > 0.0 and line.distance(shapely_point) <= buffer_m:
                return True
    return False


def _score_candidates(
    depressions: list[DepressionResult],
    *,
    crs: CRS | str,
    terminus: np.ndarray,
    forward: np.ndarray,
    perp: np.ndarray,
    barriers: list[tuple[str, Any]],
    buffer_m: float,
    params: ConduitProjectionParams,
) -> list[CandidateEntrance]:
    scored: list[tuple[DepressionResult, float]] = []
    for depression in depressions:
        point = project_geometry(
            shapely.geometry.Point(depression.centroid.lon, depression.centroid.lat),
            crs=crs,
        )
        coords = np.asarray(point.coords[0][:2], dtype=np.float64)
        rel = coords - terminus
        d_along = float(rel[0] * forward[0] + rel[1] * forward[1])
        d_perp = float(rel[0] * perp[0] + rel[1] * perp[1])
        if _point_blocked(coords, barriers, buffer_m=buffer_m):
            score = 0.0
        else:
            score = float(corridor_field_value(d_along, d_perp, params))
        scored.append((depression, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    return [
        CandidateEntrance(depression=depression, corridor_score=score, rank=index + 1)
        for index, (depression, score) in enumerate(scored)
    ]


def _write_contours(
    field: np.ndarray,
    *,
    transform: Affine,
    crs: CRS | str,
    isoline_values: tuple[float, ...],
    output_path: Path,
) -> Path:
    res_x = transform.a
    res_y = -transform.e
    origin_x = transform.c
    origin_y = transform.f

    features: list[dict[str, Any]] = []
    for value in isoline_values:
        for contour in find_contours(field, level=value):  # type: ignore[no-untyped-call]
            if len(contour) < 2:
                continue
            xs = origin_x + (contour[:, 1] + 0.5) * res_x
            ys = origin_y - (contour[:, 0] + 0.5) * res_y
            metric_line = shapely.geometry.LineString(np.column_stack([xs, ys]))
            wgs84_line = unproject_geometry(metric_line, crs=crs)
            features.append(
                {
                    "type": "Feature",
                    "geometry": shapely.geometry.mapping(wgs84_line),
                    "properties": {"relative_likelihood": float(value)},
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )
    return output_path


__all__ = [
    "CandidateEntrance",
    "ConduitProjectionParams",
    "ConduitProjectionResult",
    "CorridorContext",
    "HeadingProvenance",
    "LineBarrier",
    "corridor_axis",
    "corridor_field_value",
    "project_conduit",
    "run_conduit_analysis",
]
