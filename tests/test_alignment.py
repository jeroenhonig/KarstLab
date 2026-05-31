from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pyproj import Transformer
from shapely.geometry import Point

from karstlab.business.alignment import (
    AlignmentParams,
    _fold_bearing,
    _pairwise_bearings,
    detect_doline_alignment,
    plot_rosette,
)
from karstlab.data.crs import project_centroids, project_geometry
from karstlab.data.schemas import (
    Coordinate,
    DepressionQualityFlags,
    DepressionResult,
)


def _depression(identifier: str, x: float, y: float, *, crs: str = "EPSG:2154") -> DepressionResult:
    lon, lat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(x, y)
    return DepressionResult(
        id=identifier,
        max_depth_m=2.0,
        area_m2=100.0,
        centroid=Coordinate(lat=float(lat), lon=float(lon)),
        geometry={"type": "Point", "coordinates": [float(lon), float(lat)]},
        quality_flags=DepressionQualityFlags(),
    )


def _line_depressions(
    azimuth_deg: float,
    *,
    count: int = 10,
    spacing: float = 100.0,
    origin: tuple[float, float] = (700000.0, 6600000.0),
    crs: str = "EPSG:2154",
    prefix: str = "d",
) -> list[DepressionResult]:
    angle = np.deg2rad(azimuth_deg)
    dx = np.sin(angle) * spacing
    dy = np.cos(angle) * spacing
    return [
        _depression(prefix + str(index), origin[0] + index * dx, origin[1] + index * dy, crs=crs)
        for index in range(count)
    ]


def test_linear_arrangement_has_single_45_degree_mode() -> None:
    depressions = _line_depressions(45.0, count=10)

    result = detect_doline_alignment(depressions, crs="EPSG:2154")[0]

    assert len(result.modes) == 1
    assert result.modes[0].azimuth_deg == pytest.approx(45.0, abs=5.0)
    assert result.modes[0].confidence > 1.5


def test_crossed_sets_produce_two_modes_not_one_average() -> None:
    depressions = [
        *_line_depressions(45.0, count=8, prefix="a"),
        *_line_depressions(135.0, count=8, origin=(700800.0, 6600000.0), prefix="b"),
    ]

    result = detect_doline_alignment(
        depressions,
        crs="EPSG:2154",
        params=AlignmentParams(k_neighbors=3, max_neighbor_distance_m=500.0),
    )[0]
    azimuths = sorted(mode.azimuth_deg for mode in result.modes)

    assert azimuths == pytest.approx([45.0, 135.0], abs=5.0)


def test_uniform_grid_returns_no_modes() -> None:
    rng = np.random.default_rng(42)
    depressions = [
        _depression(f"d-{index}", 700000.0 + float(x), 6600000.0 + float(y))
        for index, (x, y) in enumerate(rng.uniform(0.0, 1000.0, size=(24, 2)))
    ]

    result = detect_doline_alignment(
        depressions,
        crs="EPSG:2154",
        params=AlignmentParams(k_neighbors=4, max_neighbor_distance_m=400.0, min_peak_ratio=3.0),
    )[0]

    assert result.modes == []


def test_bearing_folding_keeps_opposite_directions_in_same_bin() -> None:
    coords = np.array([[0.0, 0.0], [-17.365, 98.481]], dtype=np.float64)

    bearings = _pairwise_bearings(coords, k=1, max_distance_m=200.0)
    counts, edges = np.histogram(bearings, bins=18, range=(0.0, 180.0))
    folded_bin = int(np.searchsorted(edges, _fold_bearing(float(bearings[0])), side="right") - 1)

    assert counts[folded_bin] == 2


def test_global_rosette_writes_png(tmp_path: Path) -> None:
    result = detect_doline_alignment(
        _line_depressions(45.0, count=10),
        crs="EPSG:2154",
        rosette_dir=tmp_path,
    )[0]

    assert result.cluster_id is None
    assert (tmp_path / "rosette_global.png").exists()


def test_dbscan_separated_groups_write_cluster_pngs(tmp_path: Path) -> None:
    pytest.importorskip("sklearn")
    depressions = [
        *_line_depressions(45.0, count=5, prefix="a"),
        *_line_depressions(135.0, count=5, origin=(704000.0, 6600000.0), prefix="b"),
    ]

    results = detect_doline_alignment(
        depressions,
        crs="EPSG:2154",
        params=AlignmentParams(
            k_neighbors=2,
            use_dbscan=True,
            dbscan_eps_m=600.0,
            dbscan_min_samples=4,
        ),
        rosette_dir=tmp_path,
    )

    assert sorted(result.cluster_id for result in results) == [0, 1]
    assert (tmp_path / "rosette_cluster_0.png").exists()
    assert (tmp_path / "rosette_cluster_1.png").exists()


def test_dbscan_does_not_count_pairs_between_clusters() -> None:
    pytest.importorskip("sklearn")
    depressions = [
        *_line_depressions(45.0, count=4, prefix="a"),
        *_line_depressions(45.0, count=4, origin=(704000.0, 6600000.0), prefix="b"),
    ]

    clustered = detect_doline_alignment(
        depressions,
        crs="EPSG:2154",
        params=AlignmentParams(
            k_neighbors=3,
            max_neighbor_distance_m=5000.0,
            use_dbscan=True,
            dbscan_eps_m=500.0,
            dbscan_min_samples=4,
        ),
    )
    global_result = detect_doline_alignment(
        depressions,
        crs="EPSG:2154",
        params=AlignmentParams(k_neighbors=5, max_neighbor_distance_m=5000.0),
    )[0]

    assert sum(result.neighbor_count for result in clustered) < global_result.neighbor_count


def test_dbscan_small_cluster_is_ignored() -> None:
    pytest.importorskip("sklearn")
    depressions = _line_depressions(45.0, count=3)

    results = detect_doline_alignment(
        depressions,
        crs="EPSG:2154",
        params=AlignmentParams(use_dbscan=True, dbscan_eps_m=500.0, dbscan_min_samples=4),
    )

    assert results == []


def test_pair_distance_diagnostics_are_computed() -> None:
    result = detect_doline_alignment(
        _line_depressions(0.0, count=3, spacing=100.0),
        crs="EPSG:2154",
        params=AlignmentParams(k_neighbors=1, max_neighbor_distance_m=150.0),
    )[0]

    assert result.mean_pair_distance_m == pytest.approx(100.0, abs=0.1)
    assert result.std_pair_distance_m == pytest.approx(0.0, abs=0.1)


def test_non_metric_crs_raises_value_error() -> None:
    with pytest.raises(ValueError, match="metric"):
        detect_doline_alignment(_line_depressions(45.0), crs="EPSG:4326")


def test_alignment_params_override_defaults() -> None:
    result = detect_doline_alignment(
        _line_depressions(45.0, count=4),
        crs="EPSG:2154",
        params=AlignmentParams(k_neighbors=3, max_neighbor_distance_m=50.0),
    )[0]

    assert result.neighbor_count == 0


def test_different_metric_crs_preserves_alignment_mode() -> None:
    epsg2154 = detect_doline_alignment(_line_depressions(45.0), crs="EPSG:2154")[0]
    epsg32632 = detect_doline_alignment(
        _line_depressions(45.0, crs="EPSG:32632"),
        crs="EPSG:32632",
    )[0]

    assert epsg32632.modes[0].azimuth_deg == pytest.approx(epsg2154.modes[0].azimuth_deg, abs=5)


def test_project_centroids_and_geometry_reproject_to_metric_crs() -> None:
    depressions = _line_depressions(45.0, count=1)

    coords = project_centroids(depressions, crs="EPSG:2154")

    assert coords[0][0] == pytest.approx(700000.0, abs=0.1)
    assert coords[0][1] == pytest.approx(6600000.0, abs=0.1)
    assert project_geometry(Point(5.0, 43.0), crs="EPSG:2154")


def test_plot_rosette_writes_explicit_output_path(tmp_path: Path) -> None:
    result = detect_doline_alignment(_line_depressions(45.0), crs="EPSG:2154")[0]

    output = plot_rosette(result, tmp_path / "custom.png")

    assert output.exists()
