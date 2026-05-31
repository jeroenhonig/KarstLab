"""Contour extraction helpers for DEM arrays."""

from __future__ import annotations

from typing import Any, cast

import geopandas as gpd
import numpy as np
from affine import Affine
from numpy.typing import NDArray
from pyproj import CRS
from shapely.geometry import LineString
from skimage import measure


def extract_contours(
    array: NDArray[Any],
    *,
    transform: Affine,
    interval_m: float,
    crs: CRS | str | None = None,
) -> gpd.GeoDataFrame:
    """Extract elevation contours from a DEM array as LineString features."""
    elevation = _as_elevation(array)
    if interval_m <= 0:
        raise ValueError("contour interval must be positive")

    finite = elevation[np.isfinite(elevation)]
    if finite.size == 0:
        return _contour_frame([], crs=crs)

    records: list[dict[str, Any]] = []
    for level in _contour_levels(float(finite.min()), float(finite.max()), interval_m):
        contours = measure.find_contours(elevation, level=level)  # type: ignore[no-untyped-call]
        for contour in contours:
            if len(contour) < 2:
                continue
            records.append(
                {
                    "elevation_m": level,
                    "geometry": LineString(
                        _pixel_center_to_spatial(row=row, col=col, transform=transform)
                        for row, col in contour
                    ),
                }
            )

    return _contour_frame(records, crs=crs)


def _as_elevation(array: NDArray[Any]) -> NDArray[np.float64]:
    elevation = np.asarray(array, dtype=np.float64)
    if elevation.ndim != 2:
        raise ValueError("contour extraction expects a 2D DEM array")
    if elevation.shape[0] < 2 or elevation.shape[1] < 2:
        raise ValueError("contour extraction expects at least a 2x2 DEM array")
    return elevation


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


def _pixel_center_to_spatial(
    *,
    row: float,
    col: float,
    transform: Affine,
) -> tuple[float, float]:
    x_coord, y_coord = transform * (col + 0.5, row + 0.5)
    return float(x_coord), float(y_coord)


def _contour_frame(records: list[dict[str, Any]], *, crs: CRS | str | None) -> gpd.GeoDataFrame:
    if not records:
        return cast(
            gpd.GeoDataFrame,
            gpd.GeoDataFrame({"elevation_m": [], "geometry": []}, geometry="geometry", crs=crs),
        )
    return cast(gpd.GeoDataFrame, gpd.GeoDataFrame(records, geometry="geometry", crs=crs))
