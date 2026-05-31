from __future__ import annotations

import numpy as np
import pytest
from rasterio.crs import CRS

from karstlab.data.raster_io import read_band, read_dem, save_geotiff
from tests.fixtures.synthetic_dem import (
    SYNTHETIC_DEM_CRS,
    SYNTHETIC_DEM_NODATA,
    SYNTHETIC_DEM_TRANSFORM,
    synthetic_dem_array,
    write_synthetic_dem,
)


def test_read_dem_returns_array_and_metadata(tmp_path) -> None:  # type: ignore[no-untyped-def]
    dem_path = write_synthetic_dem(tmp_path / "synthetic_dem.tif")

    dem = read_dem(dem_path)

    assert dem.array.shape == (100, 100)
    assert dem.array.dtype == np.float32
    assert dem.metadata.path == dem_path
    assert dem.metadata.width == 100
    assert dem.metadata.height == 100
    assert dem.metadata.count == 1
    assert dem.metadata.dtype == "float32"
    assert dem.metadata.crs == SYNTHETIC_DEM_CRS
    assert dem.metadata.transform == SYNTHETIC_DEM_TRANSFORM
    assert dem.metadata.nodata == SYNTHETIC_DEM_NODATA
    assert dem.metadata.resolution == (1.0, 1.0)


def test_read_band_returns_single_raster_band(tmp_path) -> None:  # type: ignore[no-untyped-def]
    dem_path = write_synthetic_dem(tmp_path / "synthetic_dem.tif")

    band = read_band(dem_path, band=1)

    assert band.shape == (100, 100)
    assert np.isclose(band[0, 0], SYNTHETIC_DEM_NODATA)
    assert band[55, 50] < band[10, 10]


def test_save_geotiff_round_trip_preserves_metadata(tmp_path) -> None:  # type: ignore[no-untyped-def]
    array = synthetic_dem_array()
    output = save_geotiff(
        tmp_path / "roundtrip.tif",
        array,
        crs=CRS.from_epsg(2154),
        transform=SYNTHETIC_DEM_TRANSFORM,
        nodata=SYNTHETIC_DEM_NODATA,
    )

    loaded = read_dem(output)

    np.testing.assert_allclose(loaded.array, array)
    assert loaded.metadata.crs == CRS.from_epsg(2154)
    assert loaded.metadata.nodata == SYNTHETIC_DEM_NODATA


def test_save_geotiff_rejects_multiband_arrays(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="2D single-band"):
        save_geotiff(
            tmp_path / "invalid.tif",
            np.zeros((2, 10, 10), dtype=np.float32),
            crs=CRS.from_epsg(2154),
            transform=SYNTHETIC_DEM_TRANSFORM,
            nodata=SYNTHETIC_DEM_NODATA,
        )
