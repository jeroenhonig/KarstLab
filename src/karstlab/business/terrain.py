"""Terrain attribute helpers for DEM arrays."""

from __future__ import annotations

from typing import Any, cast

import numpy as np
from affine import Affine
from numpy.typing import NDArray

type CellSize = float | tuple[float, float] | Affine


def hillshade(
    dem: NDArray[Any],
    *,
    cell_size: CellSize = 1.0,
    azimuth: float = 315.0,
    altitude: float = 45.0,
) -> NDArray[np.float64]:
    """Return shaded relief values in the 0-255 range."""
    elevation = _as_elevation(dem)
    x_size, y_size = _cell_size(cell_size)
    dz_dy, dz_dx = np.gradient(elevation, y_size, x_size)

    slope_rad = np.arctan(np.hypot(dz_dx, dz_dy))
    aspect_rad = np.arctan2(dz_dy, -dz_dx)
    aspect_rad = np.where(aspect_rad < 0, 2.0 * np.pi + aspect_rad, aspect_rad)

    azimuth_rad = np.deg2rad((360.0 - azimuth + 90.0) % 360.0)
    altitude_rad = np.deg2rad(altitude)
    shaded = (
        np.sin(altitude_rad) * np.cos(slope_rad)
        + np.cos(altitude_rad) * np.sin(slope_rad) * np.cos(azimuth_rad - aspect_rad)
    )
    return cast(NDArray[np.float64], np.clip(255.0 * shaded, 0.0, 255.0))


def slope(dem: NDArray[Any], *, cell_size: CellSize = 1.0) -> NDArray[np.float64]:
    """Return slope angle in degrees."""
    elevation = _as_elevation(dem)
    x_size, y_size = _cell_size(cell_size)
    dz_dy, dz_dx = np.gradient(elevation, y_size, x_size)
    return cast(NDArray[np.float64], np.rad2deg(np.arctan(np.hypot(dz_dx, dz_dy))))


def curvature(dem: NDArray[Any], *, cell_size: CellSize = 1.0) -> NDArray[np.float64]:
    """Return profile-independent curvature as a Laplacian approximation.

    Positive values represent concave-up terrain such as bowl-shaped depressions.
    Negative values represent convex terrain such as domes or ridges.
    """
    elevation = _as_elevation(dem)
    x_size, y_size = _cell_size(cell_size)
    dz_dy, dz_dx = np.gradient(elevation, y_size, x_size)
    d2z_dy2 = np.gradient(dz_dy, y_size, axis=0)
    d2z_dx2 = np.gradient(dz_dx, x_size, axis=1)
    return cast(NDArray[np.float64], d2z_dx2 + d2z_dy2)


def _as_elevation(dem: NDArray[Any]) -> NDArray[np.float64]:
    elevation = np.asarray(dem, dtype=np.float64)
    if elevation.ndim != 2:
        raise ValueError("terrain helpers expect a 2D DEM array")
    if elevation.shape[0] < 2 or elevation.shape[1] < 2:
        raise ValueError("terrain helpers expect at least a 2x2 DEM array")
    return elevation


def _cell_size(cell_size: CellSize) -> tuple[float, float]:
    if isinstance(cell_size, Affine):
        x_size = abs(float(cell_size.a))
        y_size = abs(float(cell_size.e))
    elif isinstance(cell_size, tuple):
        x_size = float(cell_size[0])
        y_size = float(cell_size[1])
    else:
        x_size = float(cell_size)
        y_size = float(cell_size)

    if x_size <= 0 or y_size <= 0:
        raise ValueError("cell size must be positive")
    return x_size, y_size
