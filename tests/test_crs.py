from __future__ import annotations

import pytest
import rasterio
from affine import Affine
from rasterio.crs import CRS

from karstlab.data.crs import detect_crs, is_metric_crs, to_metric, to_wgs84
from karstlab.data.raster_io import read_dem, save_geotiff
from tests.fixtures.synthetic_dem import (
    SYNTHETIC_DEM_NODATA,
    synthetic_dem_array,
    write_synthetic_dem,
)


def test_detect_crs_reads_raster_crs(tmp_path) -> None:  # type: ignore[no-untyped-def]
    dem_path = write_synthetic_dem(tmp_path / "synthetic_dem.tif")

    assert detect_crs(dem_path) == CRS.from_epsg(2154)


def test_detect_crs_rejects_missing_crs(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "missing_crs.tif"
    save_geotiff(
        path,
        synthetic_dem_array(),
        crs=None,
        transform=Affine.identity(),
        nodata=SYNTHETIC_DEM_NODATA,
    )

    with pytest.raises(ValueError, match="no CRS"):
        detect_crs(path)


def test_is_metric_crs_distinguishes_projected_and_geographic_crs() -> None:
    assert is_metric_crs("EPSG:2154") is True
    assert is_metric_crs("EPSG:28992") is True
    assert is_metric_crs("EPSG:4326") is False


def test_to_wgs84_reprojects_synthetic_dem(tmp_path) -> None:  # type: ignore[no-untyped-def]
    dem_path = write_synthetic_dem(tmp_path / "synthetic_dem.tif")
    output = to_wgs84(dem_path, tmp_path / "synthetic_wgs84.tif")

    reprojected = read_dem(output)

    assert reprojected.metadata.crs == CRS.from_epsg(4326)
    assert reprojected.array.size > 0
    assert reprojected.metadata.nodata == SYNTHETIC_DEM_NODATA


def test_to_metric_reprojects_geographic_dem(tmp_path) -> None:  # type: ignore[no-untyped-def]
    geographic_path = tmp_path / "geographic.tif"
    save_geotiff(
        geographic_path,
        synthetic_dem_array(),
        crs=CRS.from_epsg(4326),
        transform=rasterio.transform.from_origin(1.0, 44.0, 0.00001, 0.00001),
        nodata=SYNTHETIC_DEM_NODATA,
    )

    output = to_metric(geographic_path, tmp_path / "metric.tif", target_crs="EPSG:2154")
    reprojected = read_dem(output)

    assert reprojected.metadata.crs == CRS.from_epsg(2154)
    assert is_metric_crs(reprojected.metadata.crs)
    assert reprojected.array.size > 0
