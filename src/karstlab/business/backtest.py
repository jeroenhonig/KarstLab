"""Backtest validation for the conduit prediction corridor.

Validates :func:`karstlab.business.conduit.project_conduit` against a known
survey by withholding its upstream end: for each split the downstream part is
treated as known, the upstream part as ground truth, and the predicted corridor
is scored against the hidden upstream geometry using the *continuous analytical
field* (never a raster lookup), so metrics are independent of
``raster_resolution_m``.

Reuses the shared corridor context from ``conduit.py`` and the reprojection
helpers in ``data/crs.py``; it implements no field formula or transform of its
own. Skipped splits are always reported, never silently omitted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import shapely.geometry
from rasterio.crs import CRS
from shapely.ops import substring

from karstlab.business.alignment import RosetteResult
from karstlab.business.conduit import ConduitProjectionParams, corridor_axis
from karstlab.data.crs import fold_bearing, project_geometry, unproject_geometry
from karstlab.data.schemas import DepressionResult

SCHEMA_VERSION = "1.0.0"
_SAMPLES_PER_HIDDEN_LINE = 64


@dataclass(frozen=True)
class BacktestParams:
    split_fractions: tuple[float, ...] = (0.3, 0.4, 0.5, 0.6, 0.7)
    min_known_length_m: float = 300.0
    min_hidden_length_m: float = 100.0
    min_valid_splits: int = 2


@dataclass(frozen=True)
class SplitMetrics:
    split_fraction: float
    chainage_m: float
    known_length_m: float
    hidden_length_m: float
    fraction_within_isoline_050: float
    fraction_within_isoline_020: float
    fraction_within_isoline_005: float
    mean_perp_distance_m: float
    heading_within_tolerance: bool


@dataclass(frozen=True)
class SkippedSplit:
    split_fraction: float
    chainage_m: float
    reason: Literal["known_too_short", "hidden_too_short"]


@dataclass(frozen=True)
class BacktestResult:
    valid_splits: list[SplitMetrics]
    skipped_splits: list[SkippedSplit]
    total_survey_length_m: float
    is_sufficient: bool
    insufficiency_reason: str | None
    report_path: Path
    figure_path: Path | None
    orientation_warning: str | None = None


def run_backtest(
    known_caveline: shapely.geometry.LineString,
    depressions: list[DepressionResult],
    rosette_results: list[RosetteResult],
    *,
    crs: CRS | str,
    output_dir: Path,
    slug: str,
    target_points: list[shapely.geometry.Point] | None = None,
    barrier_geometries: list[Any] | None = None,
    conduit_params: ConduitProjectionParams | None = None,
    backtest_params: BacktestParams | None = None,
    write_figure: bool = True,
) -> BacktestResult:
    """Validate ``project_conduit`` by withholding the survey's upstream end."""
    conduit_resolved = conduit_params or ConduitProjectionParams()
    backtest_resolved = backtest_params or BacktestParams()

    proj_line = project_geometry(known_caveline, crs=crs)
    total_length = float(proj_line.length)

    orientation_warning = _orientation_warning(
        known_caveline, target_points=target_points, crs=crs
    )

    valid_splits: list[SplitMetrics] = []
    skipped_splits: list[SkippedSplit] = []

    for fraction in backtest_resolved.split_fractions:
        chainage = fraction * total_length
        known_length = chainage
        hidden_length = total_length - chainage

        if known_length < backtest_resolved.min_known_length_m:
            skipped_splits.append(
                SkippedSplit(
                    split_fraction=fraction,
                    chainage_m=chainage,
                    reason="known_too_short",
                )
            )
            continue
        if hidden_length < backtest_resolved.min_hidden_length_m:
            skipped_splits.append(
                SkippedSplit(
                    split_fraction=fraction,
                    chainage_m=chainage,
                    reason="hidden_too_short",
                )
            )
            continue

        metrics = _evaluate_split(
            proj_line,
            crs=crs,
            chainage=chainage,
            total_length=total_length,
            rosette_results=rosette_results,
            target_points=target_points,
            barrier_geometries=barrier_geometries,
            conduit_params=conduit_resolved,
            fraction=fraction,
        )
        valid_splits.append(metrics)

    is_sufficient = len(valid_splits) >= backtest_resolved.min_valid_splits
    insufficiency_reason = (
        None
        if is_sufficient
        else (
            "survey too short for reliable backtest distribution: "
            f"{len(valid_splits)} valid split(s) < required "
            f"{backtest_resolved.min_valid_splits}"
        )
    )

    report_path = output_dir / "export" / f"backtest_report_{slug}.json"
    _write_report(
        report_path,
        slug=slug,
        total_length=total_length,
        is_sufficient=is_sufficient,
        insufficiency_reason=insufficiency_reason,
        valid_splits=valid_splits,
        skipped_splits=skipped_splits,
        orientation_warning=orientation_warning,
    )

    figure_path: Path | None = None
    if write_figure:
        figure_path = output_dir / "export" / f"backtest_figure_{slug}.png"
        _write_figure(figure_path, valid_splits)

    return BacktestResult(
        valid_splits=valid_splits,
        skipped_splits=skipped_splits,
        total_survey_length_m=total_length,
        is_sufficient=is_sufficient,
        insufficiency_reason=insufficiency_reason,
        report_path=report_path,
        figure_path=figure_path,
        orientation_warning=orientation_warning,
    )


def _evaluate_split(
    proj_line: shapely.geometry.LineString,
    *,
    crs: CRS | str,
    chainage: float,
    total_length: float,
    rosette_results: list[RosetteResult],
    target_points: list[shapely.geometry.Point] | None,
    barrier_geometries: list[Any] | None,
    conduit_params: ConduitProjectionParams,
    fraction: float,
) -> SplitMetrics:
    known_metric = substring(proj_line, 0.0, chainage)
    hidden_metric = substring(proj_line, chainage, total_length)

    # corridor_axis expects WGS84 input; reproject the known downstream part back.
    known_wgs84 = unproject_geometry(known_metric, crs=crs)
    context = corridor_axis(
        known_wgs84,
        rosette_results,
        crs=crs,
        target_points=target_points,
        barrier_geometries=barrier_geometries,
        params=conduit_params,
    )

    sample_coords = _sample_line(hidden_metric, _SAMPLES_PER_HIDDEN_LINE)
    field_values = context.field_at_metric(sample_coords)
    _, d_perp = context.along_perp(sample_coords)

    hidden_axial = _line_axial_heading(hidden_metric)
    heading_within = (
        _axial_distance(hidden_axial, context.heading_provenance.combined_deg)
        <= conduit_params.heading_angle_tolerance_deg
    )

    return SplitMetrics(
        split_fraction=fraction,
        chainage_m=chainage,
        known_length_m=chainage,
        hidden_length_m=total_length - chainage,
        fraction_within_isoline_050=_fraction_within(field_values, 0.5),
        fraction_within_isoline_020=_fraction_within(field_values, 0.2),
        fraction_within_isoline_005=_fraction_within(field_values, 0.05),
        mean_perp_distance_m=float(np.mean(np.abs(d_perp))) if d_perp.size else 0.0,
        heading_within_tolerance=heading_within,
    )


def _sample_line(line: shapely.geometry.LineString, samples: int) -> np.ndarray:
    length = float(line.length)
    distances = np.linspace(0.0, length, samples)
    points = [line.interpolate(float(distance)) for distance in distances]
    return np.asarray([(point.x, point.y) for point in points], dtype=np.float64)


def _fraction_within(field_values: np.ndarray, level: float) -> float:
    if field_values.size == 0:
        return 0.0
    return float(np.count_nonzero(field_values >= level) / field_values.size)


def _line_axial_heading(line: shapely.geometry.LineString) -> float:
    coords = np.asarray(line.coords, dtype=np.float64)[:, :2]
    vec = coords[-1] - coords[0]
    azimuth = (np.degrees(np.arctan2(vec[0], vec[1])) + 360.0) % 360.0
    return fold_bearing(float(azimuth))


def _axial_distance(a: float, b: float) -> float:
    diff = abs(a - b) % 180.0
    return min(diff, 180.0 - diff)


def _orientation_warning(
    known_caveline: shapely.geometry.LineString,
    *,
    target_points: list[shapely.geometry.Point] | None,
    crs: CRS | str,
) -> str | None:
    if not target_points:
        return None
    proj_line = project_geometry(known_caveline, crs=crs)
    coords = np.asarray(proj_line.coords, dtype=np.float64)[:, :2]
    first = coords[0]
    last = coords[-1]
    projected_targets = [
        np.asarray(project_geometry(point, crs=crs).coords[0][:2], dtype=np.float64)
        for point in target_points
    ]
    first_dist = min(float(np.hypot(*(target - first))) for target in projected_targets)
    last_dist = min(float(np.hypot(*(target - last))) for target in projected_targets)
    if last_dist < first_dist:
        return (
            "vertex-0 is farther from the nearest resurgence/target than vertex-last "
            f"({first_dist:.1f} m vs {last_dist:.1f} m); orientation may be reversed. "
            "Not auto-flipped — verify downstream_end convention."
        )
    return None


def _write_report(
    report_path: Path,
    *,
    slug: str,
    total_length: float,
    is_sufficient: bool,
    insufficiency_reason: str | None,
    valid_splits: list[SplitMetrics],
    skipped_splits: list[SkippedSplit],
    orientation_warning: str | None,
) -> Path:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "slug": slug,
        "total_survey_length_m": total_length,
        "is_sufficient": is_sufficient,
        "insufficiency_reason": insufficiency_reason,
        "orientation_warning": orientation_warning,
        "valid_splits": [
            {
                "split_fraction": split.split_fraction,
                "chainage_m": split.chainage_m,
                "known_length_m": split.known_length_m,
                "hidden_length_m": split.hidden_length_m,
                "fraction_within_isoline_050": split.fraction_within_isoline_050,
                "fraction_within_isoline_020": split.fraction_within_isoline_020,
                "fraction_within_isoline_005": split.fraction_within_isoline_005,
                "mean_perp_distance_m": split.mean_perp_distance_m,
                "heading_within_tolerance": split.heading_within_tolerance,
            }
            for split in valid_splits
        ],
        "skipped_splits": [
            {
                "split_fraction": skipped.split_fraction,
                "chainage_m": skipped.chainage_m,
                "reason": skipped.reason,
            }
            for skipped in skipped_splits
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return report_path


def _write_figure(figure_path: Path, valid_splits: list[SplitMetrics]) -> Path:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(6, 4))
    FigureCanvasAgg(figure)
    axis = figure.add_subplot(111)
    if valid_splits:
        chainages = [split.chainage_m for split in valid_splits]
        axis.plot(
            chainages,
            [split.fraction_within_isoline_050 for split in valid_splits],
            marker="o",
            label="p >= 0.5",
        )
        axis.plot(
            chainages,
            [split.fraction_within_isoline_020 for split in valid_splits],
            marker="s",
            label="p >= 0.2",
        )
        axis.plot(
            chainages,
            [split.fraction_within_isoline_005 for split in valid_splits],
            marker="^",
            label="p >= 0.05",
        )
        axis.set_xlabel("Known chainage (m)")
        axis.set_ylabel("Fraction of hidden line within isoline")
        axis.set_ylim(0.0, 1.0)
        axis.legend(loc="best")
    else:
        axis.text(0.5, 0.5, "No valid splits", ha="center", va="center")
    figure.tight_layout()
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(figure_path)
    return figure_path


__all__ = [
    "BacktestParams",
    "BacktestResult",
    "SkippedSplit",
    "SplitMetrics",
    "run_backtest",
]
