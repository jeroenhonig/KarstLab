"""Synthetic DEM fixtures for deterministic terrain-analysis tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from affine import Affine
from rasterio.crs import CRS
from rasterio.transform import from_origin

from karstlab.data.raster_io import save_geotiff

SYNTHETIC_DEM_SIZE = 100
SYNTHETIC_DEM_CRS = CRS.from_epsg(2154)
SYNTHETIC_DEM_NODATA = -9999.0
SYNTHETIC_DEM_TRANSFORM = from_origin(700000.0, 6600000.0, 1.0, 1.0)


def synthetic_dem_array() -> np.ndarray:
    y, x = np.indices((SYNTHETIC_DEM_SIZE, SYNTHETIC_DEM_SIZE), dtype=np.float32)
    dem = 250.0 + (x * 0.03) + (y * 0.02)

    # Three known depressions with deterministic depth/area for later doline tests.
    dem[20:28, 20:28] -= 4.0
    dem[50:62, 44:58] -= 7.5
    dem[72:80, 70:86] -= 2.0

    dem[0, 0] = SYNTHETIC_DEM_NODATA
    return dem.astype("float32")


def write_synthetic_dem(path: Path, *, transform: Affine = SYNTHETIC_DEM_TRANSFORM) -> Path:
    return save_geotiff(
        path,
        synthetic_dem_array(),
        crs=SYNTHETIC_DEM_CRS,
        transform=transform,
        nodata=SYNTHETIC_DEM_NODATA,
    )

