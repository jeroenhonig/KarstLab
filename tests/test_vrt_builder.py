from __future__ import annotations

import numpy as np
import pytest
from rasterio.crs import CRS
from rasterio.transform import from_origin

from karstlab.data.raster_io import read_dem, save_geotiff
from karstlab.data.vrt_builder import assemble_geotiff, assemble_vrt
from tests.fixtures.synthetic_dem import SYNTHETIC_DEM_CRS, SYNTHETIC_DEM_NODATA


def test_assemble_vrt_builds_two_tile_mosaic(tmp_path) -> None:  # type: ignore[no-untyped-def]
    left = np.full((10, 10), 1.0, dtype=np.float32)
    right = np.full((10, 10), 2.0, dtype=np.float32)
    left_path = save_geotiff(
        tmp_path / "left.tif",
        left,
        crs=SYNTHETIC_DEM_CRS,
        transform=from_origin(0.0, 10.0, 1.0, 1.0),
        nodata=SYNTHETIC_DEM_NODATA,
    )
    right_path = save_geotiff(
        tmp_path / "right.tif",
        right,
        crs=SYNTHETIC_DEM_CRS,
        transform=from_origin(10.0, 10.0, 1.0, 1.0),
        nodata=SYNTHETIC_DEM_NODATA,
    )

    mosaic = assemble_vrt([left_path, right_path], tmp_path / "mosaic.vrt")
    loaded = read_dem(mosaic.path)

    assert mosaic.width == 20
    assert mosaic.height == 10
    assert len(mosaic.tiles) == 2
    assert loaded.array.shape == (10, 20)
    assert np.all(loaded.array[:, :10] == 1.0)
    assert np.all(loaded.array[:, 10:] == 2.0)
    assert loaded.metadata.crs == SYNTHETIC_DEM_CRS


def test_assemble_vrt_supports_tiles_outside_vrt_directory(tmp_path) -> None:  # type: ignore[no-untyped-def]
    tile = np.full((5, 5), 4.0, dtype=np.float32)
    tile_path = save_geotiff(
        tmp_path / "tiles" / "tile.tif",
        tile,
        crs=SYNTHETIC_DEM_CRS,
        transform=from_origin(0.0, 5.0, 1.0, 1.0),
        nodata=SYNTHETIC_DEM_NODATA,
    )

    mosaic = assemble_vrt([tile_path], tmp_path / "vrt" / "mosaic.vrt")
    loaded = read_dem(mosaic.path)

    np.testing.assert_allclose(loaded.array, tile)


def test_assemble_geotiff_exports_vrt_to_tif(tmp_path) -> None:  # type: ignore[no-untyped-def]
    tile = np.full((5, 5), 3.0, dtype=np.float32)
    tile_path = save_geotiff(
        tmp_path / "tile.tif",
        tile,
        crs=SYNTHETIC_DEM_CRS,
        transform=from_origin(0.0, 5.0, 1.0, 1.0),
        nodata=SYNTHETIC_DEM_NODATA,
    )
    vrt = assemble_vrt([tile_path], tmp_path / "single.vrt")

    output = assemble_geotiff(vrt.path, tmp_path / "assembled.tif")
    loaded = read_dem(output)

    np.testing.assert_allclose(loaded.array, tile)
    assert loaded.metadata.crs == SYNTHETIC_DEM_CRS


def test_assemble_vrt_rejects_empty_tile_list(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="at least one"):
        assemble_vrt([], tmp_path / "empty.vrt")


def test_assemble_vrt_rejects_mismatched_crs(tmp_path) -> None:  # type: ignore[no-untyped-def]
    first = save_geotiff(
        tmp_path / "first.tif",
        np.ones((5, 5), dtype=np.float32),
        crs=SYNTHETIC_DEM_CRS,
        transform=from_origin(0.0, 5.0, 1.0, 1.0),
        nodata=SYNTHETIC_DEM_NODATA,
    )
    second = save_geotiff(
        tmp_path / "second.tif",
        np.ones((5, 5), dtype=np.float32),
        crs=CRS.from_epsg(4326),
        transform=from_origin(5.0, 5.0, 1.0, 1.0),
        nodata=SYNTHETIC_DEM_NODATA,
    )

    with pytest.raises(ValueError, match="same CRS"):
        assemble_vrt([first, second], tmp_path / "bad.vrt")


def test_assemble_vrt_rejects_misaligned_tiles(tmp_path) -> None:  # type: ignore[no-untyped-def]
    first = save_geotiff(
        tmp_path / "first.tif",
        np.ones((5, 5), dtype=np.float32),
        crs=SYNTHETIC_DEM_CRS,
        transform=from_origin(0.0, 5.0, 1.0, 1.0),
        nodata=SYNTHETIC_DEM_NODATA,
    )
    second = save_geotiff(
        tmp_path / "second.tif",
        np.ones((5, 5), dtype=np.float32),
        crs=SYNTHETIC_DEM_CRS,
        transform=from_origin(5.25, 5.0, 1.0, 1.0),
        nodata=SYNTHETIC_DEM_NODATA,
    )

    with pytest.raises(ValueError, match="grid-aligned"):
        assemble_vrt([first, second], tmp_path / "bad.vrt")
