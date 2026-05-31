from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon

from karstlab.business.alignment import AlignmentMode, RosetteResult
from karstlab.business.conduit import (
    ConduitProjectionParams,
    LineBarrier,
    corridor_field_value,
    project_conduit,
    run_conduit_analysis,
)
from karstlab.data.project_io import canonical_output_paths, create_project
from karstlab.data.raster_io import read_dem
from karstlab.data.schemas import (
    AnalysisParams,
    Coordinate,
    DepressionResult,
    PipelineResult,
    PipelineStatus,
    ProjectFile,
)

ANALYSIS_CRS = "EPSG:2154"
_TO_WGS84 = Transformer.from_crs(ANALYSIS_CRS, "EPSG:4326", always_xy=True)
ORIGIN = (700000.0, 6600000.0)


def _wgs84_point(x: float, y: float) -> Point:
    lon, lat = _TO_WGS84.transform(x, y)
    return Point(float(lon), float(lat))


def _wgs84_line(points_metric: list[tuple[float, float]]) -> LineString:
    return LineString([_wgs84_point(x, y).coords[0] for x, y in points_metric])


def _straight_caveline(
    azimuth_deg: float, *, length: float = 1000.0, steps: int = 11
) -> LineString:
    rad = math.radians(azimuth_deg)
    ux, uy = math.sin(rad), math.cos(rad)
    points = [
        (ORIGIN[0] + ux * length * t / (steps - 1), ORIGIN[1] + uy * length * t / (steps - 1))
        for t in range(steps)
    ]
    return _wgs84_line(points)


def _depression(identifier: str, x: float, y: float) -> DepressionResult:
    point = _wgs84_point(x, y)
    return DepressionResult(
        id=identifier,
        max_depth_m=3.0,
        area_m2=120.0,
        centroid=Coordinate(lat=float(point.y), lon=float(point.x)),
        geometry={"type": "Point", "coordinates": [float(point.x), float(point.y)]},
    )


def _small_params(**overrides: object) -> ConduitProjectionParams:
    base = {
        "sigma_m": 300.0,
        "decay_lambda": 0.001,
        "max_projection_distance_m": 2000.0,
        "raster_resolution_m": 20.0,
    }
    base.update(overrides)
    return ConduitProjectionParams(**base)  # type: ignore[arg-type]


# --- (a)-(d): continuous field formula -------------------------------------


def test_field_peaks_at_one_at_terminus() -> None:
    params = _small_params()
    assert float(corridor_field_value(0.0, 0.0, params)) == pytest.approx(1.0)


def test_field_transverse_cross_section_matches_gaussian() -> None:
    params = _small_params()
    d_perp = np.linspace(-600.0, 600.0, 25)
    value = corridor_field_value(np.full_like(d_perp, 100.0), d_perp, params)
    expected = np.exp(-0.5 * (d_perp / params.sigma_m) ** 2) * math.exp(
        -params.decay_lambda * 100.0
    )
    np.testing.assert_allclose(value, expected, atol=1e-6)


def test_field_along_axis_halving_distance() -> None:
    params = _small_params()
    halving = math.log(2.0) / params.decay_lambda
    assert float(corridor_field_value(halving, 0.0, params)) == pytest.approx(0.5, rel=0.01)


def test_field_isoline_invariant_to_max_projection_distance() -> None:
    short = _small_params(max_projection_distance_m=2000.0)
    long = _small_params(max_projection_distance_m=5000.0)
    for d_along in (100.0, 500.0, 1000.0):
        assert float(corridor_field_value(d_along, 50.0, short)) == pytest.approx(
            float(corridor_field_value(d_along, 50.0, long))
        )


# --- (e): analytical candidate scoring -------------------------------------


def test_candidate_score_independent_of_raster_resolution(tmp_path: Path) -> None:
    caveline = _straight_caveline(45.0)
    depressions = [_depression("d1", ORIGIN[0] + 500.0, ORIGIN[1] + 500.0)]

    def score(res: float) -> float:
        result = project_conduit(
            caveline,
            depressions,
            [],
            crs=ANALYSIS_CRS,
            output_dir=tmp_path / f"res{int(res)}",
            slug="res",
            params=_small_params(raster_resolution_m=res),
        )
        return result.candidates[0].corridor_score

    assert score(20.0) == pytest.approx(score(5.0), abs=1e-9)


# --- (f)-(i): barriers ------------------------------------------------------


def test_polygon_barrier_zeros_cells_inside(tmp_path: Path) -> None:
    caveline = _straight_caveline(0.0, length=200.0)
    # Polygon straddling the corridor axis ~500 m ahead (north) of terminus.
    metric_poly = [
        (ORIGIN[0] - 100.0, ORIGIN[1] + 400.0),
        (ORIGIN[0] + 100.0, ORIGIN[1] + 400.0),
        (ORIGIN[0] + 100.0, ORIGIN[1] + 600.0),
        (ORIGIN[0] - 100.0, ORIGIN[1] + 600.0),
    ]
    polygon = Polygon([_wgs84_point(x, y).coords[0] for x, y in metric_poly])

    no_barrier = project_conduit(
        caveline,
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path / "a",
        slug="a",
        params=_small_params(),
    )
    with_barrier = project_conduit(
        caveline,
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path / "b",
        slug="b",
        barrier_geometries=[polygon],
        params=_small_params(),
    )

    base = read_dem(no_barrier.raster_path).array
    masked = read_dem(with_barrier.raster_path).array
    # Some cells that were positive are now zero; positive count strictly drops.
    assert int(np.count_nonzero(masked > 0)) < int(np.count_nonzero(base > 0))


def test_line_barrier_halfplane_blocks_one_side(tmp_path: Path) -> None:
    caveline = _straight_caveline(0.0, length=200.0)
    # Horizontal barrier 800 m north; blocked side is the far (north) side.
    line = _wgs84_line(
        [(ORIGIN[0] - 500.0, ORIGIN[1] + 800.0), (ORIGIN[0] + 500.0, ORIGIN[1] + 800.0)]
    )
    blocked_point = _wgs84_point(ORIGIN[0], ORIGIN[1] + 1500.0)
    barrier = LineBarrier(line=line, blocked_side_point=blocked_point)

    result = project_conduit(
        caveline,
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="line",
        barrier_geometries=[barrier],
        params=_small_params(),
    )
    dem = read_dem(result.raster_path)
    array = dem.array
    transform = dem.metadata.transform
    rows, cols = np.indices(array.shape)
    ys = transform.f + (rows + 0.5) * transform.e
    # Every cell north of the barrier line must be masked.
    north_of_barrier = ys > (ORIGIN[1] + 800.0)
    assert float(array[north_of_barrier].max(initial=0.0)) == 0.0
    # Cells just south of the barrier on-axis remain positive.
    assert float(array.max()) > 0.0


def test_line_barrier_buffer_masks_allowed_side(tmp_path: Path) -> None:
    caveline = _straight_caveline(0.0, length=200.0)
    line = _wgs84_line(
        [(ORIGIN[0] - 500.0, ORIGIN[1] + 800.0), (ORIGIN[0] + 500.0, ORIGIN[1] + 800.0)]
    )
    blocked_point = _wgs84_point(ORIGIN[0], ORIGIN[1] + 1500.0)
    barrier = LineBarrier(line=line, blocked_side_point=blocked_point)

    no_buffer = project_conduit(
        caveline,
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path / "nb",
        slug="nb",
        barrier_geometries=[barrier],
        params=_small_params(barrier_line_buffer_m=0.0),
    )
    buffered = project_conduit(
        caveline,
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path / "bf",
        slug="bf",
        barrier_geometries=[barrier],
        params=_small_params(barrier_line_buffer_m=100.0),
    )
    assert int(np.count_nonzero(read_dem(buffered.raster_path).array > 0)) < int(
        np.count_nonzero(read_dem(no_buffer.raster_path).array > 0)
    )


# --- (j)-(l): heading derivation -------------------------------------------


def test_heading_follows_straight_approach_not_terminal_curl(tmp_path: Path) -> None:
    # Long straight approach heading az=45, then a short dense curl at the tip.
    rad = math.radians(45.0)
    ux, uy = math.sin(rad), math.cos(rad)
    straight = [(ORIGIN[0] + ux * d, ORIGIN[1] + uy * d) for d in range(0, 1001, 100)]
    tip = straight[-1]
    # Dense curl: many points jagging east over the final ~10 m.
    curl = [(tip[0] + 1.0 * k, tip[1] + 0.2 * k) for k in range(1, 21)]
    caveline = _wgs84_line(straight + curl)

    result = project_conduit(
        caveline,
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="curl",
        params=_small_params(terminal_length_m=200.0),
    )
    assert result.heading_provenance.conduit_component_deg == pytest.approx(45.0, abs=5.0)


def test_override_heading_bypasses_derivation(tmp_path: Path) -> None:
    caveline = _straight_caveline(45.0)
    result = project_conduit(
        caveline,
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="ovr",
        params=_small_params(override_heading_deg=110.0),
    )
    assert result.heading_provenance.conduit_was_overridden is True
    assert result.heading_provenance.conduit_component_deg == pytest.approx(110.0, abs=1e-6)


def test_wgs84_line_heading_matches_metric_azimuth(tmp_path: Path) -> None:
    result = project_conduit(
        _straight_caveline(70.0),
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="az",
        params=_small_params(),
    )
    assert result.heading_provenance.combined_deg == pytest.approx(70.0, abs=2.0)


# --- (m)-(p): component selection ------------------------------------------


def _rosette(modes: list[AlignmentMode]) -> RosetteResult:
    return RosetteResult(
        modes=modes,
        bin_edges_deg=tuple(float(v) for v in range(0, 181, 10)),
        bin_counts=tuple(0 for _ in range(18)),
        neighbor_count=0,
        cluster_id=None,
        mean_pair_distance_m=0.0,
        std_pair_distance_m=0.0,
    )


def test_no_rosette_mode_within_tolerance_drops_alignment(tmp_path: Path) -> None:
    caveline = _straight_caveline(45.0)
    far_mode = _rosette(
        [AlignmentMode(azimuth_deg=170.0, confidence=3.0, bin_index=17, pair_count=8)]
    )
    result = project_conduit(
        caveline,
        [],
        [far_mode],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="m",
        params=_small_params(heading_angle_tolerance_deg=40.0),
    )
    assert result.heading_provenance.alignment_component_deg is None
    assert sum(result.heading_provenance.weights) == pytest.approx(1.0)


def test_two_modes_within_tolerance_uses_highest_confidence(tmp_path: Path) -> None:
    caveline = _straight_caveline(45.0)
    rosette = _rosette(
        [
            AlignmentMode(azimuth_deg=40.0, confidence=1.6, bin_index=4, pair_count=4),
            AlignmentMode(azimuth_deg=55.0, confidence=4.2, bin_index=5, pair_count=9),
        ]
    )
    result = project_conduit(
        caveline,
        [],
        [rosette],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="n",
        params=_small_params(heading_angle_tolerance_deg=40.0),
    )
    assert result.heading_provenance.alignment_component_deg == pytest.approx(55.0)


def test_target_outside_tolerance_is_dropped(tmp_path: Path) -> None:
    caveline = _straight_caveline(0.0)  # heading due north
    # Target due east of terminus → bearing 90°, axial distance 90° > tolerance.
    target = _wgs84_point(ORIGIN[0] + 1000.0, ORIGIN[1])
    result = project_conduit(
        caveline,
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="o",
        target_points=[target],
        params=_small_params(heading_angle_tolerance_deg=40.0),
    )
    assert result.heading_provenance.target_component_deg is None
    assert result.heading_provenance.weights[2] == pytest.approx(0.0)
    assert sum(result.heading_provenance.weights) == pytest.approx(1.0)


def test_multiple_targets_uses_nearest_within_tolerance(tmp_path: Path) -> None:
    caveline = _straight_caveline(0.0, length=200.0)  # heading due north
    near = _wgs84_point(ORIGIN[0], ORIGIN[1] + 500.0)
    far = _wgs84_point(ORIGIN[0] + 50.0, ORIGIN[1] + 1500.0)
    result = project_conduit(
        caveline,
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="p",
        target_points=[far, near],
        params=_small_params(heading_angle_tolerance_deg=40.0),
    )
    used = result.heading_provenance.target_point_used
    assert used is not None
    assert used.equals(near)


# --- (q)-(r): run_conduit_analysis orchestration ---------------------------


def _project(tmp_path: Path) -> ProjectFile:
    return create_project(
        base_dir=tmp_path,
        name="Conduit",
        slug="conduit",
        land_profile="generic",
        crs_analysis=ANALYSIS_CRS,
    )


def _pipeline_result(project: ProjectFile, depressions: list[DepressionResult]) -> PipelineResult:
    return PipelineResult(
        project_id=project.id,
        status=PipelineStatus.SUCCESS,
        land_profile="generic",
        analysis_params=AnalysisParams(),
        input_dem_paths=[Path("dem.tif")],
        output_dir=project.output_dir,
        depressions=depressions,
        top_depressions=depressions[:25],
    )


def test_run_conduit_analysis_rejects_empty_depressions(tmp_path: Path) -> None:
    project = _project(tmp_path)
    result = _pipeline_result(project, [])
    with pytest.raises(ValueError, match="non-empty"):
        run_conduit_analysis(project, _straight_caveline(45.0), [], result)


def test_run_conduit_analysis_reuses_prior_depressions(tmp_path: Path) -> None:
    project = _project(tmp_path)
    depressions = [
        _depression("a", ORIGIN[0] + 400.0, ORIGIN[1] + 400.0),
        _depression("b", ORIGIN[0] + 800.0, ORIGIN[1] + 800.0),
    ]
    prior = _pipeline_result(project, depressions)

    result = run_conduit_analysis(project, _straight_caveline(45.0), [], prior)

    assert {c.depression.id for c in result.candidates} == {"a", "b"}
    assert result.raster_path == canonical_output_paths(project)["conduit_probability"]
    assert result.contours_path == canonical_output_paths(project)["conduit_contours"]


# --- (s)-(u): outputs and static weights -----------------------------------


def test_outputs_use_correct_crs(tmp_path: Path) -> None:
    result = project_conduit(
        _straight_caveline(45.0),
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="crs",
        params=_small_params(),
    )
    raster = read_dem(result.raster_path)
    assert raster.metadata.crs == raster.metadata.crs.from_string(ANALYSIS_CRS)
    assert raster.metadata.crs.to_epsg() == 2154

    geojson = json.loads(result.contours_path.read_text(encoding="utf-8"))
    assert geojson["type"] == "FeatureCollection"
    for feature in geojson["features"]:
        for lon, lat in feature["geometry"]["coordinates"]:
            assert -180.0 <= lon <= 180.0
            assert -90.0 <= lat <= 90.0


def test_static_weights_not_auto_adjusted(tmp_path: Path) -> None:
    caveline = _straight_caveline(45.0)
    rosette = _rosette([AlignmentMode(azimuth_deg=50.0, confidence=2.0, bin_index=5, pair_count=6)])
    target = _wgs84_point(ORIGIN[0] + 700.0, ORIGIN[1] + 700.0)
    result = project_conduit(
        caveline,
        [],
        [rosette],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="t",
        target_points=[target],
        params=_small_params(),
    )
    wc, wa, wt = result.heading_provenance.weights
    total = 0.6 + 0.25 + 0.15
    assert wc == pytest.approx(0.6 / total)
    assert wa == pytest.approx(0.25 / total)
    assert wt == pytest.approx(0.15 / total)


def test_no_barriers_reports_zero(tmp_path: Path) -> None:
    result = project_conduit(
        _straight_caveline(45.0),
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="u",
        params=_small_params(),
    )
    assert result.barriers_applied == 0
    assert result.barrier_paths == ()
