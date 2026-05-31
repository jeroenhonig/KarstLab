"""Terrain attribute helpers for DEM arrays."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import numpy as np
import rasterio
from affine import Affine
from numpy.typing import NDArray
from pyproj import Geod, Transformer
from rasterio.crs import CRS

type CellSize = float | tuple[float, float] | Affine

_WGS84_GEOD = Geod(ellps="WGS84")

_DEFAULT_AZIMUTHS_DEG: tuple[float, ...] = (
    0.0,
    45.0,
    90.0,
    135.0,
    180.0,
    225.0,
    270.0,
    315.0,
)


def _gradients(
    elevation: NDArray[np.float64], x_size: float, y_size: float
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return ``(dz_dx, dz_dy)`` first derivatives for a DEM.

    Shared by every terrain derivative so a DEM is differentiated once instead
    of once per attribute (hillshade, slope, curvature, and each multidirectional
    azimuth all reuse this single result).
    """
    dz_dy, dz_dx = np.gradient(elevation, y_size, x_size)
    return cast(NDArray[np.float64], dz_dx), cast(NDArray[np.float64], dz_dy)


def _slope_aspect(
    dz_dx: NDArray[np.float64], dz_dy: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    slope_rad = np.arctan(np.hypot(dz_dx, dz_dy))
    aspect_rad = np.arctan2(dz_dy, -dz_dx)
    aspect_rad = np.where(aspect_rad < 0, 2.0 * np.pi + aspect_rad, aspect_rad)
    return slope_rad, aspect_rad


def _shade_from_slope_aspect(
    slope_rad: NDArray[np.float64],
    aspect_rad: NDArray[np.float64],
    *,
    azimuth: float,
    altitude: float,
) -> NDArray[np.float64]:
    azimuth_rad = np.deg2rad((360.0 - azimuth + 90.0) % 360.0)
    altitude_rad = np.deg2rad(altitude)
    shaded = (
        np.sin(altitude_rad) * np.cos(slope_rad)
        + np.cos(altitude_rad) * np.sin(slope_rad) * np.cos(azimuth_rad - aspect_rad)
    )
    return cast(NDArray[np.float64], np.clip(255.0 * shaded, 0.0, 255.0))


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
    dz_dx, dz_dy = _gradients(elevation, x_size, y_size)
    slope_rad, aspect_rad = _slope_aspect(dz_dx, dz_dy)
    return _shade_from_slope_aspect(slope_rad, aspect_rad, azimuth=azimuth, altitude=altitude)


def multidirectional_hillshade(
    dem: NDArray[Any],
    *,
    cell_size: Affine,
    azimuths_deg: tuple[float, ...] = _DEFAULT_AZIMUTHS_DEG,
    altitude_deg: float = 45.0,
) -> NDArray[np.float64]:
    """Combine hillshades from multiple solar azimuths using their mean.

    Returns float64 to stay dtype-consistent with the other terrain
    derivatives (hillshade, slope, curvature). The DEM gradient and its
    slope/aspect are computed once and reused for every azimuth.
    """
    if not azimuths_deg:
        raise ValueError("azimuths_deg must contain at least one azimuth")
    elevation = _as_elevation(dem)
    x_size, y_size = _cell_size(cell_size)
    dz_dx, dz_dy = _gradients(elevation, x_size, y_size)
    slope_rad, aspect_rad = _slope_aspect(dz_dx, dz_dy)
    shaded = np.mean(
        [
            _shade_from_slope_aspect(
                slope_rad, aspect_rad, azimuth=azimuth, altitude=altitude_deg
            )
            for azimuth in azimuths_deg
        ],
        axis=0,
    )
    return cast(NDArray[np.float64], shaded)


def slope(dem: NDArray[Any], *, cell_size: CellSize = 1.0) -> NDArray[np.float64]:
    """Return slope angle in degrees."""
    elevation = _as_elevation(dem)
    x_size, y_size = _cell_size(cell_size)
    dz_dx, dz_dy = _gradients(elevation, x_size, y_size)
    return cast(NDArray[np.float64], np.rad2deg(np.arctan(np.hypot(dz_dx, dz_dy))))


def curvature(dem: NDArray[Any], *, cell_size: CellSize = 1.0) -> NDArray[np.float64]:
    """Return profile-independent curvature as a Laplacian approximation.

    Positive values represent concave-up terrain such as bowl-shaped depressions.
    Negative values represent convex terrain such as domes or ridges.
    """
    elevation = _as_elevation(dem)
    x_size, y_size = _cell_size(cell_size)
    dz_dx, dz_dy = _gradients(elevation, x_size, y_size)
    d2z_dy2 = np.gradient(dz_dy, y_size, axis=0)
    d2z_dx2 = np.gradient(dz_dx, x_size, axis=1)
    return cast(NDArray[np.float64], d2z_dx2 + d2z_dy2)


def compute_terrain_derivatives(
    dem: NDArray[Any],
    *,
    cell_size: CellSize = 1.0,
    azimuth: float = 315.0,
    altitude: float = 45.0,
    multi_azimuths_deg: tuple[float, ...] = _DEFAULT_AZIMUTHS_DEG,
) -> dict[str, NDArray[np.float64]]:
    """Compute hillshade, multidirectional hillshade, slope, and curvature together.

    Differentiates the DEM a single time and reuses the slope/aspect for the
    single- and multi-directional hillshades, instead of recomputing the
    gradient ~11 times across the four standalone helpers.
    """
    if not multi_azimuths_deg:
        raise ValueError("multi_azimuths_deg must contain at least one azimuth")
    elevation = _as_elevation(dem)
    x_size, y_size = _cell_size(cell_size)
    dz_dx, dz_dy = _gradients(elevation, x_size, y_size)
    slope_rad, aspect_rad = _slope_aspect(dz_dx, dz_dy)

    hillshade_single = _shade_from_slope_aspect(
        slope_rad, aspect_rad, azimuth=azimuth, altitude=altitude
    )
    hillshade_multi = cast(
        NDArray[np.float64],
        np.mean(
            [
                _shade_from_slope_aspect(
                    slope_rad, aspect_rad, azimuth=multi_azimuth, altitude=altitude
                )
                for multi_azimuth in multi_azimuths_deg
            ],
            axis=0,
        ),
    )
    slope_deg = cast(NDArray[np.float64], np.rad2deg(slope_rad))
    d2z_dy2 = np.gradient(dz_dy, y_size, axis=0)
    d2z_dx2 = np.gradient(dz_dx, x_size, axis=1)
    curvature_values = cast(NDArray[np.float64], d2z_dx2 + d2z_dy2)
    return {
        "hillshade": hillshade_single,
        "hillshade_multi": hillshade_multi,
        "slope": slope_deg,
        "curvature": curvature_values,
    }


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


def extract_elevation_profile(
    dem_path: Path,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    crs: CRS | str,
    n_samples: int = 256,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Sample a DEM along a geodetic great-circle line between two WGS84 points.

    ``start`` and ``end`` are ``(lat, lon)`` in WGS84. Returns
    ``(distances_m, elevations_m)`` where ``distances_m[0] == 0`` and the last
    distance equals the geodesic length. Nodata samples become ``nan``.
    Raises ``ValueError`` if both endpoints are outside the DEM bounds.
    """
    if n_samples < 2:
        raise ValueError("n_samples must be at least 2")

    lat1, lon1 = start
    lat2, lon2 = end
    _, _, total_distance = _WGS84_GEOD.inv(lon1, lat1, lon2, lat2)

    intermediate = (
        _WGS84_GEOD.npts(lon1, lat1, lon2, lat2, n_samples - 2) if n_samples > 2 else []
    )
    lons = [lon1, *[lon for lon, _ in intermediate], lon2]
    lats = [lat1, *[lat for _, lat in intermediate], lat2]
    distances = np.linspace(0.0, float(total_distance), n_samples)

    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xs, ys = transformer.transform(lons, lats)
    xs = np.asarray(xs, dtype=np.float64)
    ys = np.asarray(ys, dtype=np.float64)

    with rasterio.open(dem_path) as dataset:
        left, bottom, right, top = dataset.bounds

        def _inside(x: float, y: float) -> bool:
            return bool(left <= x <= right and bottom <= y <= top)

        if not _inside(xs[0], ys[0]) and not _inside(xs[-1], ys[-1]):
            raise ValueError("both profile endpoints are outside the DEM bounds")

        nodata = dataset.nodata
        samples = dataset.sample(np.column_stack([xs, ys]))
        elevations = np.array([float(value[0]) for value in samples], dtype=np.float64)
        # rasterio.sample() returns 0 (not nodata) for points outside the dataset
        # when no nodata is set, which would render as spurious sea-level. Mark
        # every out-of-bounds sample as nan explicitly.
        outside = (xs < left) | (xs > right) | (ys < bottom) | (ys > top)

    if nodata is not None:
        elevations[elevations == nodata] = np.nan
    elevations[outside] = np.nan
    return distances, elevations
