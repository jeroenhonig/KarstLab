from __future__ import annotations

import numpy as np
import pytest
from affine import Affine

from karstlab.business.contours import extract_contours


def test_extract_contours_from_plane_returns_lines_with_elevation() -> None:
    x = np.arange(5, dtype=np.float64)
    dem = np.tile(x, (5, 1))
    transform = Affine.translation(100.0, 200.0) * Affine.scale(2.0, -2.0)

    contours = extract_contours(dem, transform=transform, interval_m=1.0, crs="EPSG:2154")

    assert list(contours.columns) == ["elevation_m", "geometry"]
    assert contours.crs == "EPSG:2154"
    assert set(contours["elevation_m"]) == {1.0, 2.0, 3.0}
    assert len(contours) == 3
    assert all(geometry.geom_type == "LineString" for geometry in contours.geometry)
    first_line = contours.sort_values("elevation_m").iloc[0].geometry
    assert first_line.coords[0][0] == pytest.approx(103.0)


def test_extract_contours_returns_empty_frame_when_no_internal_levels() -> None:
    dem = np.full((3, 3), 5.0, dtype=np.float64)

    contours = extract_contours(dem, transform=Affine.identity(), interval_m=1.0)

    assert contours.empty
    assert list(contours.columns) == ["elevation_m", "geometry"]


def test_extract_contours_rejects_non_positive_interval() -> None:
    dem = np.zeros((3, 3), dtype=np.float64)

    with pytest.raises(ValueError, match="interval"):
        extract_contours(dem, transform=Affine.identity(), interval_m=0.0)


def test_extract_contours_rejects_non_2d_arrays() -> None:
    with pytest.raises(ValueError, match="2D DEM"):
        extract_contours(
            np.zeros((2, 3, 4), dtype=np.float64),
            transform=Affine.identity(),
            interval_m=1.0,
        )
