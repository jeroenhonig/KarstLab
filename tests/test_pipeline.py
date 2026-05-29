from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from karstlab.business.pipeline import run_headless_analysis
from karstlab.data.project_io import canonical_output_paths, create_project
from karstlab.data.raster_io import read_dem, save_geotiff
from karstlab.data.schemas import AnalysisParams, PipelineStatus
from tests.fixtures.synthetic_dem import write_synthetic_dem


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


def test_run_headless_analysis_writes_pipeline_result(tmp_path: Path) -> None:
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")
    project = create_project(
        base_dir=tmp_path,
        name="Synthetic",
        land_profile="generic",
        crs_analysis="EPSG:2154",
        analysis_params=AnalysisParams(),
        slug="synthetic",
    ).model_copy(update={"dem_paths": [dem_path]})
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
