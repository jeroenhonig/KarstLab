from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from affine import Affine
from pyproj import Transformer

from karstlab.business.terrain import (
    curvature,
    extract_elevation_profile,
    hillshade,
    multidirectional_hillshade,
    slope,
)
from tests.fixtures.synthetic_dem import (
    SYNTHETIC_DEM_CRS,
    synthetic_dem_array,
    write_synthetic_dem,
)

_TO_WGS84 = Transformer.from_crs(SYNTHETIC_DEM_CRS, "EPSG:4326", always_xy=True)


def _wgs84_latlon(x: float, y: float) -> tuple[float, float]:
    lon, lat = _TO_WGS84.transform(x, y)
    return (float(lat), float(lon))


def test_hillshade_of_flat_surface_is_uniform() -> None:
    dem = np.full((5, 5), 100.0, dtype=np.float64)

    shaded = hillshade(dem, cell_size=1.0, azimuth=315.0, altitude=45.0)

    assert shaded.shape == dem.shape
    assert np.allclose(shaded, shaded[0, 0])
    assert shaded[0, 0] == pytest.approx(180.312, abs=0.001)


def test_multidirectional_hillshade_of_flat_surface_is_uniform() -> None:
    dem = np.full((5, 5), 100.0, dtype=np.float64)

    shaded = multidirectional_hillshade(dem, cell_size=Affine.scale(1.0, -1.0))

    assert shaded.shape == dem.shape
    assert shaded.dtype == np.float64
    assert np.allclose(shaded, shaded[0, 0])


def test_multidirectional_hillshade_matches_mean_of_eight_hillshades() -> None:
    axis = np.arange(6, dtype=np.float64)
    dem = np.add.outer(axis, axis * 2.0)
    transform = Affine.scale(1.0, -1.0)

    shaded = multidirectional_hillshade(dem, cell_size=transform)
    expected = np.mean(
        [
            hillshade(dem, cell_size=transform, azimuth=azimuth, altitude=45.0)
            for azimuth in (0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0)
        ],
        axis=0,
    )

    np.testing.assert_allclose(shaded, expected, atol=1e-5)


def test_multidirectional_hillshade_respects_custom_azimuths() -> None:
    axis = np.arange(6, dtype=np.float64)
    dem = np.add.outer(axis, axis * 2.0)
    transform = Affine.scale(1.0, -1.0)

    shaded = multidirectional_hillshade(dem, cell_size=transform, azimuths_deg=(90.0, 180.0))
    expected = np.mean(
        [
            hillshade(dem, cell_size=transform, azimuth=90.0, altitude=45.0),
            hillshade(dem, cell_size=transform, azimuth=180.0, altitude=45.0),
        ],
        axis=0,
    )

    np.testing.assert_allclose(shaded, expected, atol=1e-5)


def test_slope_of_tilted_plane_matches_expected_angle() -> None:
    x = np.arange(6, dtype=np.float64)
    dem = np.tile(2.0 * x, (6, 1))

    angles = slope(dem, cell_size=1.0)

    np.testing.assert_allclose(angles, np.rad2deg(np.arctan(2.0)), atol=0.1)


def test_slope_accepts_affine_transform_cell_size() -> None:
    transform = Affine.translation(0.0, 0.0) * Affine.scale(2.0, -2.0)
    x = np.arange(6, dtype=np.float64)
    dem = np.tile(2.0 * x, (6, 1))

    angles = slope(dem, cell_size=transform)

    np.testing.assert_allclose(angles, 45.0, atol=0.1)


def test_slope_accepts_rectangular_tuple_cell_size() -> None:
    x = np.arange(6, dtype=np.float64) * 2.0
    y = np.arange(6, dtype=np.float64)[:, None] * 3.0
    dem = x + y

    angles = slope(dem, cell_size=(2.0, 3.0))

    np.testing.assert_allclose(angles, np.rad2deg(np.arctan(np.sqrt(2.0))), atol=0.1)


def test_curvature_sign_matches_concave_and_convex_surfaces() -> None:
    axis = np.linspace(-2.0, 2.0, 7)
    x_grid, y_grid = np.meshgrid(axis, axis)
    concave = x_grid**2 + y_grid**2
    convex = -concave

    concave_curvature = curvature(concave, cell_size=axis[1] - axis[0])
    convex_curvature = curvature(convex, cell_size=axis[1] - axis[0])

    assert concave_curvature[3, 3] > 0.0
    assert convex_curvature[3, 3] < 0.0
    assert concave_curvature[3, 3] == pytest.approx(4.0, abs=0.01)
    assert convex_curvature[3, 3] == pytest.approx(-4.0, abs=0.01)


def test_terrain_helpers_reject_non_2d_arrays() -> None:
    with pytest.raises(ValueError, match="2D DEM"):
        slope(np.zeros((2, 3, 4), dtype=np.float64))


def test_terrain_helpers_reject_arrays_smaller_than_2x2() -> None:
    with pytest.raises(ValueError, match="2x2 DEM"):
        slope(np.zeros((1, 2), dtype=np.float64))
    with pytest.raises(ValueError, match="2x2 DEM"):
        slope(np.zeros((2, 1), dtype=np.float64))


def test_terrain_helpers_reject_non_positive_cell_size() -> None:
    with pytest.raises(ValueError, match="cell size"):
        curvature(np.zeros((3, 3), dtype=np.float64), cell_size=0.0)
    with pytest.raises(ValueError, match="cell size"):
        curvature(np.zeros((3, 3), dtype=np.float64), cell_size=(-5.0, 10.0))


def test_extract_elevation_profile_returns_n_samples(tmp_path: Path) -> None:
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    start = _wgs84_latlon(700010.5, 6599990.5)
    end = _wgs84_latlon(700080.5, 6599930.5)

    distances, elevations = extract_elevation_profile(
        dem_path, start, end, crs=SYNTHETIC_DEM_CRS, n_samples=64
    )

    assert len(distances) == 64
    assert len(elevations) == 64


def test_extract_elevation_profile_distance_axis(tmp_path: Path) -> None:
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    start = _wgs84_latlon(700010.5, 6599990.5)
    end = _wgs84_latlon(700080.5, 6599930.5)

    distances, _ = extract_elevation_profile(
        dem_path, start, end, crs=SYNTHETIC_DEM_CRS, n_samples=64
    )

    assert distances[0] == 0.0
    expected = float(np.hypot(700080.5 - 700010.5, 6599990.5 - 6599930.5))
    assert distances[-1] == pytest.approx(expected, rel=0.01)


def test_extract_elevation_profile_samples_known_value(tmp_path: Path) -> None:
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    # Pixel (row=10, col=10): elevation = 250 + col*0.03 + row*0.02 = 250.5.
    expected = float(synthetic_dem_array()[10, 10])
    start = _wgs84_latlon(700010.5, 6599990.5)
    end = _wgs84_latlon(700040.5, 6599960.5)

    _, elevations = extract_elevation_profile(
        dem_path, start, end, crs=SYNTHETIC_DEM_CRS, n_samples=32
    )

    assert elevations[0] == pytest.approx(expected, abs=1.0)


def test_extract_elevation_profile_marks_outside_samples_nan(tmp_path: Path) -> None:
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    start = _wgs84_latlon(700010.5, 6599990.5)  # inside
    end = _wgs84_latlon(900000.0, 6599990.5)  # far outside DEM bounds

    distances, elevations = extract_elevation_profile(
        dem_path, start, end, crs=SYNTHETIC_DEM_CRS, n_samples=16
    )

    assert len(distances) == 16
    assert np.isnan(elevations[-1])


def test_extract_elevation_profile_rejects_fully_outside_line(tmp_path: Path) -> None:
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    start = _wgs84_latlon(900000.0, 6599990.5)
    end = _wgs84_latlon(910000.0, 6599990.5)

    with pytest.raises(ValueError, match="outside the DEM bounds"):
        extract_elevation_profile(dem_path, start, end, crs=SYNTHETIC_DEM_CRS, n_samples=16)
