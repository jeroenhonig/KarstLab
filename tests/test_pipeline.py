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
    assert messages == ["breach", "pointer", "accumulation", "streams", "fill"]


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
