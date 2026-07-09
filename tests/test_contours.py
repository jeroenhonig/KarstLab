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


def test_extract_contours_returns_empty_frame_for_all_nan_dem() -> None:
    dem = np.full((3, 3), np.nan, dtype=np.float64)

    contours = extract_contours(dem, transform=Affine.identity(), interval_m=1.0)

    assert contours.empty
    assert list(contours.columns) == ["elevation_m", "geometry"]


def test_extract_contours_rejects_non_positive_interval() -> None:
    dem = np.zeros((3, 3), dtype=np.float64)

    with pytest.raises(ValueError, match="interval"):
        extract_contours(dem, transform=Affine.identity(), interval_m=0.0)


def test_extract_contours_rejects_negative_interval() -> None:
    dem = np.zeros((3, 3), dtype=np.float64)

    with pytest.raises(ValueError, match="interval"):
        extract_contours(dem, transform=Affine.identity(), interval_m=-1.0)


def test_extract_contours_accepts_2x2_dem() -> None:
    dem = np.array([[0.0, 1.0], [0.0, 1.0]], dtype=np.float64)

    contours = extract_contours(dem, transform=Affine.identity(), interval_m=0.5)

    assert len(contours) == 1
    assert contours.iloc[0].elevation_m == pytest.approx(0.5)


def test_extract_contours_rejects_non_2d_arrays() -> None:
    with pytest.raises(ValueError, match="2D DEM"):
        extract_contours(
            np.zeros((2, 3, 4), dtype=np.float64),
            transform=Affine.identity(),
            interval_m=1.0,
        )


def test_extract_contours_excludes_nodata_from_range() -> None:
    # A small ramp 0..4 with a -99999 nodata sentinel. Without masking the
    # sentinel would inflate the level count to ~100k and hang; masked, only the
    # valid 0..4 range is contoured.
    ramp = np.tile(np.arange(5, dtype=np.float64), (5, 1))
    ramp[0, 0] = -99999.0

    contours = extract_contours(
        ramp, transform=Affine.identity(), interval_m=1.0, nodata=-99999.0
    )

    assert set(contours["elevation_m"]) == {1.0, 2.0, 3.0}


def test_extract_contours_caps_level_count_and_reports() -> None:
    # 0..600 range at 1 m would be 599 levels; capped to <= max_levels by
    # coarsening the interval, and the adjustment is reported via callback.
    ramp = np.tile(np.linspace(0.0, 600.0, 400, dtype=np.float64), (4, 1))
    messages: list[str] = []

    contours = extract_contours(
        ramp,
        transform=Affine.identity(),
        interval_m=1.0,
        max_levels=60,
        callback=messages.append,
    )

    distinct_levels = set(contours["elevation_m"])
    assert len(distinct_levels) <= 60
    assert any("Contour interval raised" in m for m in messages)


def test_effective_interval_coarsens_only_when_needed() -> None:
    from karstlab.business.contours import _effective_interval

    assert _effective_interval(0.0, 50.0, 1.0, 60) == 1.0  # 50 levels, fine
    assert _effective_interval(0.0, 258.0, 1.0, 60) == 5.0  # ceil(258/60)=5
    assert _effective_interval(0.0, 0.0, 1.0, 60) == 1.0  # flat: unchanged


def test_decimation_factor_thresholds() -> None:
    from karstlab.business.contours import _decimation_factor

    assert _decimation_factor((100, 100), 2000) == 1  # within budget
    assert _decimation_factor((2000, 1500), 2000) == 1  # exactly at budget
    assert _decimation_factor((4100, 800), 2000) == 3  # ceil(4100 / 2000)
    assert _decimation_factor((9000, 9000), 0) == 1  # disabled budget


def test_extract_contours_decimates_large_grid_but_keeps_coordinates() -> None:
    # A west-east elevation ramp: every column is one metre higher than the last.
    width = 600
    ramp = np.tile(np.arange(width, dtype=np.float64), (10, 1))
    transform = Affine.translation(1000.0, 5000.0) * Affine.scale(1.0, -1.0)

    full = extract_contours(ramp, transform=transform, interval_m=1.0, max_grid_px=10_000)
    decimated = extract_contours(ramp, transform=transform, interval_m=1.0, max_grid_px=100)

    # Decimation traces a coarser grid, so it emits fewer/shorter lines.
    assert not decimated.empty
    assert len(decimated) <= len(full)
    # Coordinates remain in the DEM's spatial range (transform scaled correctly).
    xs = [x for geom in decimated.geometry for x, _ in geom.coords]
    assert min(xs) >= 1000.0
    assert max(xs) <= 1000.0 + width
