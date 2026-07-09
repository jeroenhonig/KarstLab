from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from rasterio.crs import CRS
from rasterio.transform import from_origin

from karstlab.business.pipeline import run_headless_analysis
from karstlab.data.project_io import canonical_output_paths, create_project
from karstlab.data.raster_io import read_dem, save_geotiff
from karstlab.data.schemas import AnalysisParams, PipelineStatus, ProjectFile, UserSettings
from tests.fixtures.synthetic_dem import (
    SYNTHETIC_DEM_CRS,
    SYNTHETIC_DEM_NODATA,
    synthetic_dem_array,
    write_synthetic_dem,
)


class FakeHydrologyBackend:
    def breach_depressions_least_cost(
        self,
        dem_path: Path,
        output_path: Path,
        *,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        if callback is not None:
            callback("breach")
        return self._copy(dem_path, output_path, callback=None, message="breach")

    def fill_depressions(
        self,
        dem_path: Path,
        output_path: Path,
        *,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        if callback is not None:
            callback("fill")
        dem = read_dem(dem_path)
        filled = dem.array.copy()
        filled[20:28, 20:28] += 4.0
        filled[50:62, 44:58] += 7.5
        filled[72:80, 70:86] += 2.0
        return save_geotiff(
            output_path,
            filled,
            crs=dem.metadata.crs,
            transform=dem.metadata.transform,
            nodata=dem.metadata.nodata,
        )

    def d8_pointer(
        self,
        dem_path: Path,
        output_path: Path,
        *,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        return self._copy(dem_path, output_path, callback=callback, message="pointer")

    def flow_accumulation(
        self,
        pointer_path: Path,
        output_path: Path,
        *,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        return self._copy(pointer_path, output_path, callback=callback, message="accumulation")

    def extract_streams(
        self,
        flow_accumulation_path: Path,
        output_path: Path,
        *,
        threshold: float,
        zero_background: bool,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        assert threshold == 1000.0
        assert zero_background is True
        return self._copy(flow_accumulation_path, output_path, callback=callback, message="streams")

    def _copy(
        self,
        source_path: Path,
        output_path: Path,
        *,
        callback: Callable[[str], None] | None,
        message: str,
    ) -> Path:
        if callback is not None:
            callback(message)
        dem = read_dem(source_path)
        return save_geotiff(
            output_path,
            dem.array,
            crs=dem.metadata.crs,
            transform=dem.metadata.transform,
            nodata=dem.metadata.nodata,
        )


class FailingFillHydrologyBackend(FakeHydrologyBackend):
    def fill_depressions(
        self,
        dem_path: Path,
        output_path: Path,
        *,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        raise RuntimeError("whitebox panic")


@pytest.fixture(autouse=True)
def _stub_pipeline_map_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "karstlab.business.pipeline.render_top_depressions_map_html",
        lambda *_args, **_kwargs: "<html><body>pipeline map</body></html>",
    )


def _project_with_dems(
    tmp_path: Path,
    *,
    name: str,
    slug: str,
    dem_paths: list[Path],
) -> ProjectFile:
    return create_project(
        base_dir=tmp_path,
        name=name,
        land_profile="generic",
        crs_analysis="EPSG:2154",
        analysis_params=AnalysisParams(),
        slug=slug,
    ).model_copy(update={"dem_paths": dem_paths})


def test_run_headless_analysis_writes_pipeline_result(tmp_path: Path) -> None:
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    project = _project_with_dems(
        tmp_path,
        name="Synthetic",
        slug="synthetic",
        dem_paths=[dem_path],
    )
    messages: list[str] = []

    result = run_headless_analysis(
        project,
        hydrology_backend=FakeHydrologyBackend(),
        callback=messages.append,
    )

    paths = canonical_output_paths(project)
    assert result.status == PipelineStatus.SUCCESS
    assert len(result.depressions) == 3
    assert [depression.rank for depression in result.top_depressions] == [1, 2, 3]
    assert paths["pipeline_result"].exists()
    assert {step.step_id for step in result.steps} == {
        "read_dem",
        "hydrology",
        "terrain",
        "depression_fill",
        "doline_detection",
        "contours",
        "exports",
        "interactive_map",
        "report",
    }
    assert paths["statistics"].exists()
    assert paths["dolines_geojson"].exists()
    assert paths["dolines_kml"].exists()
    assert paths["top_depressions_gpx"].exists()
    assert paths["contours_geojson"].exists()
    assert paths["contours_kml"].exists()
    assert paths["interactive_map"].exists()
    assert paths["report"].exists()
    assert "<iframe" in paths["report"].read_text(encoding="utf-8")
    # WhiteboxTools backend messages must still arrive, in order, interleaved with
    # the pipeline phase-progress messages.
    backend = {"breach", "pointer", "accumulation", "streams", "fill"}
    backend_messages = [m for m in messages if m in backend]
    assert backend_messages == ["breach", "pointer", "accumulation", "streams", "fill"]
    # Phase-progress messages drive the determinate progress bar.
    assert "Detecting dolines" in messages
    assert "Rendering interactive map" in messages


def test_run_headless_analysis_falls_back_when_fill_depressions_fails(
    tmp_path: Path,
) -> None:
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    project = _project_with_dems(
        tmp_path,
        name="Fill Fallback",
        slug="fill-fallback",
        dem_paths=[dem_path],
    )
    messages: list[str] = []

    result = run_headless_analysis(
        project,
        hydrology_backend=FailingFillHydrologyBackend(),
        callback=messages.append,
    )

    paths = canonical_output_paths(project)
    assert result.status == PipelineStatus.SUCCESS
    assert paths["pipeline_result"].exists()
    assert (project.output_dir / "rasters" / "depression_fill").exists()
    assert any("Python fallback" in message for message in messages)


def test_run_headless_analysis_writes_terrain_derivative_rasters(tmp_path: Path) -> None:
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    project = _project_with_dems(
        tmp_path,
        name="Terrain",
        slug="terrain",
        dem_paths=[dem_path],
    )

    result = run_headless_analysis(project, hydrology_backend=FakeHydrologyBackend())

    paths = canonical_output_paths(project)
    source_metadata = read_dem(dem_path).metadata
    terrain_step = next(step for step in result.steps if step.step_id == "terrain")
    assert terrain_step.output_paths == [
        paths["hillshade"],
        paths["hillshade_multi"],
        paths["slope"],
        paths["curvature"],
    ]
    for path in terrain_step.output_paths:
        assert path.exists()
        terrain = read_dem(path)
        assert terrain.array.shape == (100, 100)
        assert terrain.metadata.crs == SYNTHETIC_DEM_CRS
        assert terrain.metadata.transform == source_metadata.transform


def test_run_headless_analysis_writes_depression_depth_raster(tmp_path: Path) -> None:
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    project = _project_with_dems(
        tmp_path,
        name="Depression Depth",
        slug="depression-depth",
        dem_paths=[dem_path],
    )

    result = run_headless_analysis(project, hydrology_backend=FakeHydrologyBackend())

    paths = canonical_output_paths(project)
    detection_step = next(step for step in result.steps if step.step_id == "doline_detection")
    depth = read_dem(paths["depression_depth"])
    assert paths["depression_depth"].exists()
    assert paths["depression_depth"] in detection_step.output_paths
    assert depth.array.shape == (100, 100)
    assert float(np.nanmin(depth.array)) >= 0.0
    assert float(np.nanmax(depth.array)) == pytest.approx(7.5)
    assert depth.metadata.crs == SYNTHETIC_DEM_CRS


def test_run_headless_analysis_passes_imported_markers_to_map(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    marker_path = tmp_path / "markers.gpx"
    marker_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="KarstLab test">
  <wpt lat="44.1" lon="1.2"><name>Sinkhole A</name></wpt>
</gpx>
""",
        encoding="utf-8",
    )
    project = _project_with_dems(
        tmp_path,
        name="Markers",
        slug="markers",
        dem_paths=[dem_path],
    ).model_copy(update={"marker_paths": [marker_path]})
    captured_layers: list[Any] = []

    def render_map(_depressions: object, **kwargs: object) -> str:
        captured_layers.extend(kwargs["imported_marker_layers"])  # type: ignore[arg-type]
        return "<html><body>pipeline map</body></html>"

    monkeypatch.setattr(
        "karstlab.business.pipeline.render_top_depressions_map_html",
        render_map,
    )

    run_headless_analysis(project, hydrology_backend=FakeHydrologyBackend())

    assert [layer.name for layer in captured_layers] == ["markers"]


def test_run_headless_analysis_passes_profile_tile_attribution_to_map(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    project = create_project(
        base_dir=tmp_path,
        name="Profile Tiles",
        land_profile="fr",
        crs_analysis="EPSG:2154",
        slug="profile-tiles",
    ).model_copy(update={"dem_paths": [dem_path]})
    captured_kwargs: dict[str, Any] = {}

    def render_map(_depressions: object, **kwargs: object) -> str:
        captured_kwargs.update(kwargs)
        return "<html><body>pipeline map</body></html>"

    monkeypatch.setattr(
        "karstlab.business.pipeline.render_top_depressions_map_html",
        render_map,
    )

    run_headless_analysis(project, hydrology_backend=FakeHydrologyBackend())

    assert captured_kwargs["tiles"] == "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
    assert captured_kwargs["tile_attribution"] == "© OpenStreetMap contributors"


def test_run_headless_analysis_assembles_multiple_dem_tiles_before_analysis(
    tmp_path: Path,
) -> None:
    left = write_synthetic_dem(tmp_path / "left.tif")
    right = write_synthetic_dem(
        tmp_path / "right.tif",
        transform=from_origin(700100.0, 6600000.0, 1.0, 1.0),
    )
    project = _project_with_dems(
        tmp_path,
        name="Mosaic",
        slug="mosaic",
        dem_paths=[left, right],
    )

    result = run_headless_analysis(project, hydrology_backend=FakeHydrologyBackend())

    paths = canonical_output_paths(project)
    assembled = read_dem(paths["assembled_dem"])
    assert paths["assembled_dem"].exists()
    assert assembled.array.shape == (100, 200)
    assert result.input_dem_paths == [paths["assembled_dem"]]
    read_step = next(step for step in result.steps if step.step_id == "read_dem")
    assert read_step.metadata["path"] == str(paths["assembled_dem"])
    assert len(result.depressions) == 3


def test_run_headless_analysis_uses_vrt_for_large_multi_tile_dem(
    tmp_path: Path,
) -> None:
    """Verifies VRT-mode selection; true full-array OOM prevention remains out of scope."""
    array = np.full((512, 512), 250.0, dtype=np.float32)
    array[20:28, 20:28] -= 4.0
    array[50:62, 44:58] -= 7.5
    array[72:80, 70:86] -= 2.0
    left = save_geotiff(
        tmp_path / "left.tif",
        array,
        crs=SYNTHETIC_DEM_CRS,
        transform=from_origin(700000.0, 6600000.0, 1.0, 1.0),
        nodata=SYNTHETIC_DEM_NODATA,
    )
    right = save_geotiff(
        tmp_path / "right.tif",
        array,
        crs=SYNTHETIC_DEM_CRS,
        transform=from_origin(700512.0, 6600000.0, 1.0, 1.0),
        nodata=SYNTHETIC_DEM_NODATA,
    )
    project = _project_with_dems(
        tmp_path,
        name="Large Mosaic",
        slug="large-mosaic",
        dem_paths=[left, right],
    )

    result = run_headless_analysis(
        project,
        hydrology_backend=FakeHydrologyBackend(),
        user_settings=UserSettings(large_dem_threshold_mb=1),
    )

    paths = canonical_output_paths(project)
    vrt_step = next(step for step in result.steps if step.step_id == "vrt_assembly")
    read_step = next(step for step in result.steps if step.step_id == "read_dem")
    assert result.status == PipelineStatus.SUCCESS
    assert result.input_dem_paths == [project.cache_dir / "assembled_dem.vrt"]
    assert not paths["assembled_dem"].exists()
    assert vrt_step.output_paths == [project.cache_dir / "assembled_dem.vrt"]
    assert vrt_step.metadata["analysis_dem_mode"] == "vrt"
    assert read_step.metadata["path"] == str(project.cache_dir / "assembled_dem.vrt")
    assert len(result.depressions) > 0


def test_run_headless_analysis_uses_vrt_for_large_single_tile_dem(
    tmp_path: Path,
) -> None:
    """Single CRS-bearing tile over the threshold must still route through VRT mode."""
    array = np.full((600, 600), 250.0, dtype=np.float32)
    array[20:28, 20:28] -= 4.0
    array[50:62, 44:58] -= 7.5
    array[72:80, 70:86] -= 2.0
    tile = save_geotiff(
        tmp_path / "single_large.tif",
        array,
        crs=SYNTHETIC_DEM_CRS,
        transform=from_origin(700000.0, 6600000.0, 1.0, 1.0),
        nodata=SYNTHETIC_DEM_NODATA,
    )
    project = _project_with_dems(
        tmp_path,
        name="Large Single",
        slug="large-single",
        dem_paths=[tile],
    )

    result = run_headless_analysis(
        project,
        hydrology_backend=FakeHydrologyBackend(),
        user_settings=UserSettings(large_dem_threshold_mb=1),
    )

    paths = canonical_output_paths(project)
    vrt_step = next(step for step in result.steps if step.step_id == "vrt_assembly")
    assert result.status == PipelineStatus.SUCCESS
    assert result.input_dem_paths == [project.cache_dir / "assembled_dem.vrt"]
    assert not paths["assembled_dem"].exists()
    assert vrt_step.metadata["analysis_dem_mode"] == "vrt"
    assert len(result.depressions) > 0


def test_run_headless_analysis_uses_direct_path_for_small_single_tile_dem(
    tmp_path: Path,
) -> None:
    """Small single tile keeps the direct path (no VRT, no size-guard activation)."""
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    project = _project_with_dems(
        tmp_path,
        name="Small Single",
        slug="small-single",
        dem_paths=[dem_path],
    )

    result = run_headless_analysis(
        project,
        hydrology_backend=FakeHydrologyBackend(),
        user_settings=UserSettings(large_dem_threshold_mb=500),
    )

    assert result.status == PipelineStatus.SUCCESS
    assert result.input_dem_paths == [dem_path]
    assert not any(step.step_id == "vrt_assembly" for step in result.steps)


def test_run_headless_analysis_rejects_multitile_crs_mismatch_with_clear_error(
    tmp_path: Path,
) -> None:
    first = write_synthetic_dem(tmp_path / "first.tif")
    second = save_geotiff(
        tmp_path / "second.tif",
        synthetic_dem_array(),
        crs=CRS.from_epsg(4326),
        transform=from_origin(1.0, 45.0, 0.00001, 0.00001),
        nodata=SYNTHETIC_DEM_NODATA,
    )
    project = _project_with_dems(
        tmp_path,
        name="Crs Mismatch",
        slug="crs-mismatch",
        dem_paths=[first, second],
    )

    with pytest.raises(ValueError, match="same CRS|CRS"):
        run_headless_analysis(project, hydrology_backend=FakeHydrologyBackend())


def test_run_headless_analysis_requires_dem_path(tmp_path: Path) -> None:
    project = create_project(
        base_dir=tmp_path,
        name="Empty",
        land_profile="generic",
        crs_analysis="EPSG:2154",
        slug="empty",
    )

    try:
        run_headless_analysis(project, hydrology_backend=FakeHydrologyBackend())
    except ValueError as exc:
        assert "dem_paths" in str(exc)
    else:
        raise AssertionError("expected missing dem_paths to fail")


def test_overview_array_decimates_only_when_oversized() -> None:
    from karstlab.business.pipeline import _overview_array

    small = np.zeros((50, 80), dtype=np.float32)
    assert _overview_array(small, max_px=2048) is small  # untouched below budget

    big = np.zeros((5000, 3000), dtype=np.float32)
    reduced = _overview_array(big, max_px=2048)
    assert max(reduced.shape) <= 5000  # decimated
    assert reduced.shape == (1667, 1000)  # stride ceil(5000/2048)=3


def test_run_headless_analysis_emits_per_phase_timing(tmp_path: Path) -> None:
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    project = _project_with_dems(
        tmp_path, name="Timing", slug="timing", dem_paths=[dem_path]
    )
    messages: list[str] = []

    run_headless_analysis(
        project,
        hydrology_backend=FakeHydrologyBackend(),
        callback=messages.append,
    )

    # Live per-phase completion lines with a duration.
    assert any(m.startswith("✓ ") and m.endswith("s)") for m in messages)
    # End-of-run breakdown header plus at least one labelled phase row.
    assert any(m.startswith("Timing breakdown (wall-clock ") for m in messages)
    assert any("Terrain derivatives:" in m for m in messages)


def test_max_pool_or_keeps_thin_features() -> None:
    import numpy as np

    from karstlab.business.pipeline import _max_pool_or

    mask = np.zeros((8, 8), dtype=bool)
    mask[3, :] = True  # one-pixel-wide horizontal line
    pooled = _max_pool_or(mask, 2)
    assert pooled.shape == (4, 4)
    assert pooled.any()  # line survives decimation (stride alone would drop it)


def test_streams_overlay_bounds_and_empty(tmp_path: Path) -> None:
    import numpy as np
    from rasterio.transform import from_origin

    from karstlab.business.pipeline import _streams_overlay

    bounds = [[47.0, 6.0], [47.1, 6.1]]
    transform = from_origin(700000.0, 6600000.0, 0.5, 0.5)

    streams = np.zeros((50, 60), dtype=np.float32)
    streams[10, :] = 1.0
    path = save_geotiff(
        tmp_path / "streams.tif", streams, crs=SYNTHETIC_DEM_CRS,
        transform=transform, nodata=0.0, dtype="float32",
    )
    overlay = _streams_overlay(path, bounds=bounds)
    assert overlay is not None
    assert isinstance(overlay.image, np.ndarray)
    assert overlay.image.shape[2] == 4  # RGBA
    assert overlay.bounds == bounds

    empty = save_geotiff(
        tmp_path / "empty.tif", np.zeros((20, 20), dtype=np.float32),
        crs=SYNTHETIC_DEM_CRS, transform=transform, nodata=0.0, dtype="float32",
    )
    assert _streams_overlay(empty, bounds=bounds) is None


def _write_survey_gpx(path: Path, points_l93: list[tuple[float, float]]) -> Path:
    """Write a GPX track of Lambert-93 points (reprojected to WGS84) for a caveline."""
    from pyproj import Transformer

    to_wgs84 = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)
    trkpts = "".join(
        f'<trkpt lat="{lat}" lon="{lon}"></trkpt>'
        for x, y in points_l93
        for lon, lat in [to_wgs84.transform(x, y)]
    )
    path.write_text(
        '<?xml version="1.0"?>'
        '<gpx version="1.1" creator="test"><trk><trkseg>'
        f"{trkpts}"
        "</trkseg></trk></gpx>",
        encoding="utf-8",
    )
    return path


def test_run_headless_analysis_projects_conduit_when_caveline_present(tmp_path: Path) -> None:
    """A project carrying a survey line runs the conduit stage and writes its outputs."""
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    # A short survey line inside the synthetic DEM footprint (origin 700000/6600000).
    caveline = _write_survey_gpx(
        tmp_path / "survey.gpx", [(700010.0, 6599990.0), (700030.0, 6599970.0)]
    )
    project = _project_with_dems(
        tmp_path, name="Conduit", slug="conduit", dem_paths=[dem_path]
    ).model_copy(update={"caveline_path": caveline})
    messages: list[str] = []

    result = run_headless_analysis(
        project, hydrology_backend=FakeHydrologyBackend(), callback=messages.append
    )

    paths = canonical_output_paths(project)
    assert result.status == PipelineStatus.SUCCESS
    assert "conduit" in result.provenance
    assert paths["conduit_probability"].exists()
    assert paths["conduit_contours"].exists()
    summary = result.provenance["conduit"]
    assert "heading_deg" in summary
    assert isinstance(summary["candidates"], list)
    assert "Projecting conduit corridor" in messages


def test_load_caveline_direction_reverses_terminus(tmp_path: Path) -> None:
    """`downstream_end` flips which survey endpoint becomes the projection terminus."""
    from karstlab.business.pipeline import _load_caveline

    caveline = _write_survey_gpx(
        tmp_path / "survey.gpx", [(700010.0, 6599990.0), (700030.0, 6599970.0)]
    )
    first = _load_caveline(caveline, downstream_end="first")
    last = _load_caveline(caveline, downstream_end="last")
    # Same geometry, opposite orientation: the last coord of one is the first of the other.
    assert first.coords[0] == last.coords[-1]
    assert first.coords[-1] == last.coords[0]


def test_load_caveline_handles_disconnected_survey_network(tmp_path: Path) -> None:
    """A branching survey (disjoint legs) yields the longest connected passage."""
    from karstlab.business.pipeline import _load_caveline

    # Two disjoint legs; survey_line_geometry would reject these as unconnected.
    kml = tmp_path / "network.kml"
    from pyproj import Transformer

    to_wgs84 = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)

    def leg(pts: list[tuple[float, float]]) -> str:
        coords = " ".join(
            f"{lon},{lat},0" for x, y in pts for lon, lat in [to_wgs84.transform(x, y)]
        )
        return (
            f"<Placemark><LineString><coordinates>{coords}"
            "</coordinates></LineString></Placemark>"
        )

    short_leg = leg([(700000.0, 6600000.0), (700010.0, 6600000.0)])
    long_leg = leg([(700100.0, 6600100.0), (700100.0, 6600300.0), (700100.0, 6600500.0)])
    kml.write_text(
        '<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"{short_leg}{long_leg}</Document></kml>",
        encoding="utf-8",
    )
    line = _load_caveline(kml, downstream_end="first")
    assert line.geom_type == "LineString"
    assert len(line.coords) >= 2  # longest passage selected, not an error


def test_load_caveline_derives_axis_from_polygon_survey(tmp_path: Path) -> None:
    """A footprint-polygon survey (no centreline) yields a principal-axis caveline."""
    from pyproj import Transformer

    from karstlab.business.pipeline import _load_caveline

    to_wgs84 = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)
    # Two small square footprints strung out along a N-S trend (y grows north).
    def square(cx: float, cy: float) -> str:
        ring = [
            (cx - 5, cy - 5), (cx + 5, cy - 5), (cx + 5, cy + 5),
            (cx - 5, cy + 5), (cx - 5, cy - 5),
        ]
        coords = " ".join(
            f"{lon},{lat},0" for x, y in ring for lon, lat in [to_wgs84.transform(x, y)]
        )
        return (
            "<Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>"
            f"{coords}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
        )

    kml = tmp_path / "footprints.kml"
    kml.write_text(
        '<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"{square(700000.0, 6600000.0)}{square(700000.0, 6600400.0)}</Document></kml>",
        encoding="utf-8",
    )
    line = _load_caveline(kml, downstream_end="first")
    assert line.geom_type == "LineString"
    assert len(line.coords) == 2  # principal-axis segment
    # Trend is N-S, so the two ends differ mostly in latitude.
    (lon0, lat0), (lon1, lat1) = line.coords[0], line.coords[-1]
    assert abs(lat1 - lat0) > abs(lon1 - lon0)


def test_run_headless_analysis_skips_conduit_without_caveline(tmp_path: Path) -> None:
    """No survey line → no conduit stage, no conduit provenance, core run unaffected."""
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    project = _project_with_dems(
        tmp_path, name="NoConduit", slug="noconduit", dem_paths=[dem_path]
    )
    messages: list[str] = []

    result = run_headless_analysis(
        project, hydrology_backend=FakeHydrologyBackend(), callback=messages.append
    )

    assert result.status == PipelineStatus.SUCCESS
    assert "conduit" not in result.provenance
    assert "Projecting conduit corridor" not in messages
    assert not canonical_output_paths(project)["conduit_contours"].exists()


def test_simplify_for_map_reprojects_to_wgs84() -> None:
    """Map contours must be WGS84 so Leaflet plots them in the visible extent.

    Regression: the interactive-map contour layer was embedded in the DEM's
    native (projected, metric) CRS, so Leaflet rendered the lines far outside
    valid lat/lon and they never appeared. Simplification stays in metric units;
    the result is reprojected to EPSG:4326.
    """
    import geopandas as gpd
    from shapely.geometry import LineString

    from karstlab.business.pipeline import _simplify_for_map

    # A short contour segment in Lambert-93 (EPSG:2154), eastings/northings in m.
    metric = gpd.GeoDataFrame(
        {"elevation_m": [260.0], "name": ["260 m"]},
        geometry=[LineString([(948100.0, 6697100.0), (948200.0, 6697150.0)])],
        crs="EPSG:2154",
    )

    out = _simplify_for_map(metric)

    assert out.crs is not None
    assert CRS.from_user_input(out.crs).to_epsg() == 4326
    lon, lat = out.geometry.iloc[0].coords[0]
    assert 5.0 < lon < 8.0  # eastern France longitude
    assert 46.0 < lat < 48.0  # eastern France latitude


def test_hillshade_overlay_rgba_makes_nodata_transparent() -> None:
    import numpy as np

    from karstlab.business.pipeline import _hillshade_overlay_rgba

    hill = np.full((20, 16), 180.0, dtype=np.float32)
    hill[:5, :] = np.nan  # nodata border
    rgba = _hillshade_overlay_rgba(hill)
    assert rgba.shape == (20, 16, 4)
    assert int(rgba[0, 0, 3]) == 0  # nodata fully transparent (no black border)
    assert int(rgba[10, 8, 3]) == 255  # valid data opaque
    assert int(rgba[10, 8, 0]) == 180  # grayscale carries the relief value


def test_dem_cache_reuses_intermediates_on_second_run(tmp_path: Path) -> None:
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    project = _project_with_dems(
        tmp_path, name="Cache", slug="cache", dem_paths=[dem_path]
    )

    first: list[str] = []
    run_headless_analysis(
        project, hydrology_backend=FakeHydrologyBackend(), callback=first.append
    )
    assert not any("Reusing cached" in m for m in first)  # cold cache: computed

    second: list[str] = []
    run_headless_analysis(
        project, hydrology_backend=FakeHydrologyBackend(), callback=second.append
    )
    # Warm cache: DEM-only stages are reused instead of recomputed.
    assert any("Reusing cached terrain derivatives" in m for m in second)
    assert any("Reusing cached detection fill" in m for m in second)

    forced: list[str] = []
    run_headless_analysis(
        project,
        hydrology_backend=FakeHydrologyBackend(),
        callback=forced.append,
        force_recompute=True,
    )
    assert not any("Reusing cached" in m for m in forced)  # force bypasses cache


def test_dem_cache_invalidated_when_dem_changes(tmp_path: Path) -> None:
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    project = _project_with_dems(
        tmp_path, name="Inval", slug="inval", dem_paths=[dem_path]
    )
    run_headless_analysis(project, hydrology_backend=FakeHydrologyBackend())

    # Rewrite the DEM (new mtime/size fingerprint) → cache must invalidate.
    write_synthetic_dem(dem_path)
    msgs: list[str] = []
    run_headless_analysis(
        project, hydrology_backend=FakeHydrologyBackend(), callback=msgs.append
    )
    assert not any("Reusing cached" in m for m in msgs)


def test_fr_profile_loads_with_vector_overlays() -> None:
    from karstlab.data.land_profiles import load_land_profile

    profile = load_land_profile("fr")
    names = [v.name for v in profile.map_layers.vector_overlays]
    assert "BRGM Dolines (BDCharm50)" in names
    doline = next(v for v in profile.map_layers.vector_overlays if v.bake)
    assert doline.typename == "BRGM:c50_l_divers"
    assert doline.cql_filter == "code=8"
    assert doline.srs == "EPSG:2154"


def test_profile_vector_overlays_bakes_when_data_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from karstlab.business import pipeline
    from karstlab.data import geodata_service
    from karstlab.data.land_profiles import load_land_profile

    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"code": 8},
             "geometry": {"type": "Point", "coordinates": [6.0, 47.3]}}
        ],
    }
    monkeypatch.setattr(geodata_service, "fetch_wfs_geojson", lambda **_k: fc)
    specs = pipeline._profile_vector_overlays(
        load_land_profile("fr"),
        dem_bounds=(920000.0, 6650000.0, 1010000.0, 6740000.0),
        dem_crs="EPSG:2154",
        cache_dir=tmp_path,
    )
    assert [s.name for s in specs] == ["BRGM Dolines (BDCharm50)"]


def test_profile_vector_overlays_skips_when_source_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from karstlab.business import pipeline
    from karstlab.data import geodata_service
    from karstlab.data.land_profiles import load_land_profile

    monkeypatch.setattr(geodata_service, "fetch_wfs_geojson", lambda **_k: None)
    specs = pipeline._profile_vector_overlays(
        load_land_profile("fr"),
        dem_bounds=(920000.0, 6650000.0, 1010000.0, 6740000.0),
        dem_crs="EPSG:2154",
        cache_dir=tmp_path,
    )
    assert specs == []  # unavailable source never blocks the analysis


def test_fr_profile_has_on_demand_bss_eau_overlay() -> None:
    from karstlab.data.land_profiles import load_land_profile

    profile = load_land_profile("fr")
    bss = next(
        (v for v in profile.map_layers.vector_overlays if "BSS Eau" in v.name), None
    )
    assert bss is not None
    assert bss.bake is False  # on-demand, not baked into the analysis map
    assert bss.typename == "BSS_EAU_POINT"
    assert bss.output_format == "GML2"  # MapServer endpoint is GML-only


def test_fetch_vector_overlay_passes_bbox_and_returns_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from karstlab.business import pipeline
    from karstlab.data import geodata_service
    from karstlab.data.schemas import VectorLayerConfig

    captured: dict[str, object] = {}

    def fake_fetch(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"type": "FeatureCollection", "features": [{"id": 1}]}

    monkeypatch.setattr(geodata_service, "fetch_wfs_geojson", fake_fetch)
    vec = VectorLayerConfig.model_validate(
        {"name": "X", "url": "https://x/ows", "typename": "T", "srs": "EPSG:2154"}
    )
    out = pipeline.fetch_vector_overlay(
        vec,
        dem_bounds=(948000.0, 6697000.0, 951000.0, 6702000.0),
        dem_crs="EPSG:2154",
        cache_dir=tmp_path,
    )
    assert out is not None and out["features"]
    # Same-CRS bbox is passed through unchanged.
    assert captured["bbox"] == (948000.0, 6697000.0, 951000.0, 6702000.0)


def test_annotate_fault_distances_without_path_is_noop(tmp_path: Path) -> None:
    from karstlab.business import pipeline
    from karstlab.data.schemas import DepressionResult

    project = _project_with_dems(tmp_path, name="NoFault", slug="nofault", dem_paths=[])
    ring = [[6.0, 47.3], [6.001, 47.3], [6.001, 47.301], [6.0, 47.3]]
    dep = DepressionResult.model_validate({
        "id": "d1", "max_depth_m": 2.0, "area_m2": 50.0,
        "centroid": {"lat": 47.3, "lon": 6.0},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    })
    assert project.fault_lines_path is None
    out, faults = pipeline._annotate_fault_distances([dep], project)
    assert out[0].distance_to_fault_m is None
    assert faults is None


def test_annotate_fault_distances_with_shapefile(tmp_path: Path) -> None:
    import geopandas as gpd
    import shapely.geometry as sgeom
    from pyproj import Transformer

    from karstlab.business import pipeline
    from karstlab.data.schemas import DepressionResult

    shp = tmp_path / "faults.shp"
    gpd.GeoDataFrame(
        {"DESCR": ["Faille observée"]},
        geometry=[sgeom.LineString([(948000.0, 6699000.0), (948000.0, 6701000.0)])],
        crs="EPSG:2154",
    ).to_file(shp)
    lon, lat = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True).transform(
        948000.0, 6700000.0
    )
    project = _project_with_dems(
        tmp_path, name="Fault", slug="fault", dem_paths=[]
    ).model_copy(update={"fault_lines_path": shp})
    ring = [[lon, lat], [lon + 1e-4, lat], [lon + 1e-4, lat + 1e-4], [lon, lat]]
    dep = DepressionResult.model_validate({
        "id": "d1", "max_depth_m": 2.0, "area_m2": 50.0,
        "centroid": {"lat": lat, "lon": lon},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    })
    out, faults = pipeline._annotate_fault_distances([dep], project)
    assert out[0].distance_to_fault_m is not None and out[0].distance_to_fault_m < 5.0
    assert out[0].nearest_fault_type == "Faille observée"
    assert faults is not None and len(faults) == 1
