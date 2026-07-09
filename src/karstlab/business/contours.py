"""Contour extraction helpers for DEM arrays."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, cast

import geopandas as gpd
import numpy as np
from affine import Affine
from numpy.typing import NDArray
from pyproj import CRS
from shapely.geometry import LineString
from skimage import measure

# Longest-side pixel budget for contour tracing. ``find_contours`` walks the
# whole grid once per level, so a multi-tile 1 m mosaic (tens of millions of
# cells x hundreds of levels) costs minutes and emits unusably dense lines.
# Decimating to this budget keeps contours visually identical for display while
# cutting the work by the square of the decimation factor.
_CONTOUR_MAX_GRID_PX = 2000

# Safety ceiling on the number of contour levels traced. ``find_contours`` runs
# once per level; nodata is now masked out of the range (so the sentinel can no
# longer explode the count), which means the requested interval is honoured for
# any realistic elevation range — a 250 m range at 1 m keeps 1 m. This ceiling
# only guards against pathological ranges (e.g. a 4000 m alpine span at 1 m),
# coarsening the interval just enough to stay below it.
_CONTOUR_MAX_LEVELS = 2000


def extract_contours(
    array: NDArray[Any],
    *,
    transform: Affine,
    interval_m: float,
    crs: CRS | str | None = None,
    nodata: float | int | None = None,
    max_grid_px: int = _CONTOUR_MAX_GRID_PX,
    max_levels: int = _CONTOUR_MAX_LEVELS,
    callback: Callable[[str], None] | None = None,
) -> gpd.GeoDataFrame:
    """Extract elevation contours from a DEM array as LineString features.

    Nodata cells (non-finite, or equal to ``nodata``) are excluded from the
    elevation range and flattened to the minimum valid elevation so they never
    spawn spurious contours — critical for multi-tile mosaics whose nodata
    sentinel (e.g. -99999) would otherwise inflate the level count by orders of
    magnitude. Large DEMs are decimated to ``max_grid_px`` on the longest side,
    and the effective interval is coarsened so at most ``max_levels`` levels are
    traced. Small in-range DEMs are unchanged.
    """
    raw = _validate_2d(array)
    if interval_m <= 0:
        raise ValueError("contour interval must be positive")

    factor = _decimation_factor(raw.shape, max_grid_px)
    sample = np.asarray(raw[::factor, ::factor], dtype=np.float64)
    sample_transform = transform * Affine.scale(float(factor)) if factor > 1 else transform

    valid = np.isfinite(sample)
    if nodata is not None and np.isfinite(nodata):
        valid &= sample != nodata
    if not valid.any():
        return _contour_frame([], crs=crs)

    vmin = float(sample[valid].min())
    vmax = float(sample[valid].max())
    if vmin == vmax:
        return _contour_frame([], crs=crs)

    # Flatten invalid cells to the valid floor so the constant fill region sits
    # below every (strictly interior) contour level and produces no geometry.
    elevation = np.where(valid, sample, vmin)

    effective_interval = _effective_interval(vmin, vmax, interval_m, max_levels)
    if callback is not None and effective_interval > interval_m:
        callback(
            f"Contour interval raised to {effective_interval:g} m "
            f"(requested {interval_m:g} m exceeds {max_levels} levels)"
        )

    records: list[dict[str, Any]] = []
    for level in _contour_levels(vmin, vmax, effective_interval):
        contours = measure.find_contours(elevation, level=level)  # type: ignore[no-untyped-call]
        for contour in contours:
            if len(contour) < 2:
                continue
            records.append(
                {
                    "elevation_m": level,
                    "geometry": LineString(
                        _contour_to_spatial(contour, transform=sample_transform)
                    ),
                }
            )

    return _contour_frame(records, crs=crs)


def _effective_interval(
    minimum: float, maximum: float, interval_m: float, max_levels: int
) -> float:
    """Coarsen ``interval_m`` so ``(maximum - minimum) / interval`` <= ``max_levels``."""
    span = maximum - minimum
    if max_levels <= 0 or span <= 0:
        return interval_m
    level_count = span / interval_m
    if level_count <= max_levels:
        return interval_m
    return interval_m * math.ceil(level_count / max_levels)


def _decimation_factor(shape: tuple[int, ...], max_grid_px: int) -> int:
    longest = max(shape[0], shape[1])
    if max_grid_px <= 0 or longest <= max_grid_px:
        return 1
    return int(np.ceil(longest / max_grid_px))


def _validate_2d(array: NDArray[Any]) -> NDArray[Any]:
    raw = np.asarray(array)
    if raw.ndim != 2:
        raise ValueError("contour extraction expects a 2D DEM array")
    if raw.shape[0] < 2 or raw.shape[1] < 2:
        raise ValueError("contour extraction expects at least a 2x2 DEM array")
    return raw


def _contour_to_spatial(contour: NDArray[Any], *, transform: Affine) -> NDArray[np.float64]:
    """Map an ``(N, 2)`` array of ``(row, col)`` pixel coords to ``(N, 2)`` spatial XY.

    Applies the affine transform to every vertex at once instead of one Python
    call per point, which dominates contour extraction on dense DEMs.
    """
    rows = contour[:, 0] + 0.5
    cols = contour[:, 1] + 0.5
    xs, ys = transform * (cols, rows)
    return np.column_stack([xs, ys])


def _contour_levels(minimum: float, maximum: float, interval_m: float) -> tuple[float, ...]:
    first = np.ceil(minimum / interval_m) * interval_m
    last = np.floor(maximum / interval_m) * interval_m
    levels: list[float] = []
    current = first
    tolerance = interval_m * 1e-9
    while current <= last + tolerance:
        level = float(current)
        if minimum < level < maximum:
            levels.append(level)
        current += interval_m
    return tuple(levels)


def _contour_frame(records: list[dict[str, Any]], *, crs: CRS | str | None) -> gpd.GeoDataFrame:
    if not records:
        return cast(
            gpd.GeoDataFrame,
            gpd.GeoDataFrame({"elevation_m": [], "geometry": []}, geometry="geometry", crs=crs),
        )
    return cast(gpd.GeoDataFrame, gpd.GeoDataFrame(records, geometry="geometry", crs=crs))
