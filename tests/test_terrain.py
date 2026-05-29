from __future__ import annotations

import numpy as np
import pytest
from affine import Affine

from karstlab.business.terrain import curvature, hillshade, slope


def test_hillshade_of_flat_surface_is_uniform() -> None:
    dem = np.full((5, 5), 100.0, dtype=np.float64)

    shaded = hillshade(dem, cell_size=1.0, azimuth=315.0, altitude=45.0)

    assert shaded.shape == dem.shape
    assert np.allclose(shaded, shaded[0, 0])
    assert shaded[0, 0] == pytest.approx(180.312, abs=0.001)


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


def test_terrain_helpers_reject_non_positive_cell_size() -> None:
    with pytest.raises(ValueError, match="cell size"):
        curvature(np.zeros((3, 3), dtype=np.float64), cell_size=0.0)
