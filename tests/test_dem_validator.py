from __future__ import annotations

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin

from karstlab.business.dem_validator import DEMValidator
from karstlab.data.raster_io import save_geotiff
from tests.fixtures.synthetic_dem import (
    SYNTHETIC_DEM_CRS,
    SYNTHETIC_DEM_NODATA,
    SYNTHETIC_DEM_TRANSFORM,
    synthetic_dem_array,
    write_synthetic_dem,
)


def test_validator_accepts_synthetic_dem_with_only_expected_warnings(tmp_path) -> None:  # type: ignore[no-untyped-def]
    dem_path = write_synthetic_dem(tmp_path / "dem.tif")

    result = DEMValidator().validate(dem_path)

    assert result.is_valid
    assert not result.errors
    assert {issue.check_id for issue in result.warnings} == {
        "vertical_datum",
        "edge_artifacts",
    }


def test_validator_reports_missing_file_as_format_error(tmp_path) -> None:  # type: ignore[no-untyped-def]
    result = DEMValidator().validate(tmp_path / "missing.tif")

    assert not result.is_valid
    assert [issue.check_id for issue in result.errors] == ["format"]


def test_validator_rejects_missing_crs(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = save_geotiff(
        tmp_path / "missing_crs.tif",
        synthetic_dem_array(),
        crs=None,
        transform=SYNTHETIC_DEM_TRANSFORM,
        nodata=SYNTHETIC_DEM_NODATA,
    )

    result = DEMValidator().validate(path)

    assert _error_ids(result) == {"crs"}


def test_validator_rejects_geographic_crs(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = save_geotiff(
        tmp_path / "geographic.tif",
        synthetic_dem_array(),
        crs=CRS.from_epsg(4326),
        transform=from_origin(5.0, 43.0, 0.00001, 0.00001),
        nodata=SYNTHETIC_DEM_NODATA,
    )

    result = DEMValidator().validate(path)

    assert _error_ids(result) == {"crs"}


def test_validator_rejects_missing_nodata(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = save_geotiff(
        tmp_path / "missing_nodata.tif",
        synthetic_dem_array(),
        crs=SYNTHETIC_DEM_CRS,
        transform=SYNTHETIC_DEM_TRANSFORM,
        nodata=None,
    )

    result = DEMValidator().validate(path)

    assert "nodata" in _error_ids(result)


def test_validator_warns_on_low_precision_dtype(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = save_geotiff(
        tmp_path / "uint8_dem.tif",
        np.ones((10, 10), dtype=np.uint8),
        crs=SYNTHETIC_DEM_CRS,
        transform=from_origin(0.0, 10.0, 1.0, 1.0),
        nodata=0,
    )

    result = DEMValidator().validate(path)

    assert "data_type" in _warning_ids(result)


def test_validator_warns_on_resolution_outside_expected_lidar_range(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = save_geotiff(
        tmp_path / "coarse.tif",
        synthetic_dem_array(),
        crs=SYNTHETIC_DEM_CRS,
        transform=from_origin(0.0, 10_000.0, 100.0, 100.0),
        nodata=SYNTHETIC_DEM_NODATA,
    )

    result = DEMValidator().validate(path)

    assert "resolution" in _warning_ids(result)


def test_validator_warns_on_dsm_filename(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = write_synthetic_dem(tmp_path / "sample_dsm_surface.tif")

    result = DEMValidator().validate(path)

    assert "dsm_detection" in _warning_ids(result)


def test_validator_warns_on_hydrologically_preconditioned_filename(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = write_synthetic_dem(tmp_path / "dem_filled_hydro.tif")

    result = DEMValidator().validate(path)

    assert "hydro_preconditioning" in _warning_ids(result)


def test_validator_warns_on_large_nodata_coverage(tmp_path) -> None:  # type: ignore[no-untyped-def]
    array = synthetic_dem_array()
    array[:50, :] = SYNTHETIC_DEM_NODATA
    path = save_geotiff(
        tmp_path / "gappy.tif",
        array,
        crs=SYNTHETIC_DEM_CRS,
        transform=SYNTHETIC_DEM_TRANSFORM,
        nodata=SYNTHETIC_DEM_NODATA,
    )

    result = DEMValidator().validate(path)

    assert "nodata_coverage" in _warning_ids(result)
    assert "edge_artifacts" in _warning_ids(result)


def test_validator_handles_nan_nodata_masks(tmp_path) -> None:  # type: ignore[no-untyped-def]
    array = np.ones((10, 10), dtype=np.float32)
    array[0, :] = np.nan
    array[:, 0] = np.nan
    path = save_geotiff(
        tmp_path / "nan_nodata.tif",
        array,
        crs=SYNTHETIC_DEM_CRS,
        transform=from_origin(0.0, 10.0, 1.0, 1.0),
        nodata=np.nan,
    )

    result = DEMValidator(max_nodata_fraction=0.1).validate(path)

    assert "nodata_coverage" in _warning_ids(result)
    assert "edge_artifacts" in _warning_ids(result)


def test_validator_warns_on_multiband_dem(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "multiband.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=2,
        dtype="float32",
        crs=SYNTHETIC_DEM_CRS,
        transform=from_origin(0.0, 10.0, 1.0, 1.0),
        nodata=SYNTHETIC_DEM_NODATA,
    ) as dataset:
        dataset.write(np.ones((2, 10, 10), dtype=np.float32))

    result = DEMValidator().validate(path)

    assert "band_count" in _warning_ids(result)


def test_validator_rejects_insufficient_disk_space(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    path = write_synthetic_dem(tmp_path / "dem.tif")

    class Usage:
        free = 1

    monkeypatch.setattr("karstlab.business.dem_validator.shutil.disk_usage", lambda _: Usage)

    result = DEMValidator().validate(path)

    assert "disk_space" in _error_ids(result)


def test_validator_rejects_invalid_raster_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "not_a_raster.tif"
    path.write_text("not a raster", encoding="utf-8")

    result = DEMValidator().validate(path)

    assert "format" in _error_ids(result)


def _error_ids(result) -> set[str]:  # type: ignore[no-untyped-def]
    return {issue.check_id for issue in result.errors}


def _warning_ids(result) -> set[str]:  # type: ignore[no-untyped-def]
    return {issue.check_id for issue in result.warnings}
