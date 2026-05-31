"""Raster read/write helpers for GeoTIFF DEM files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS
from rasterio.windows import Window
from rasterio.windows import transform as window_transform


@dataclass(frozen=True)
class DemMetadata:
    path: Path
    width: int
    height: int
    count: int
    dtype: str
    crs: CRS
    transform: Affine
    nodata: float | int | None
    bounds: tuple[float, float, float, float]
    resolution: tuple[float, float]


@dataclass(frozen=True)
class DemData:
    array: np.ndarray
    metadata: DemMetadata


def read_dem(
    path: Path,
    *,
    band: int = 1,
    window: Window | None = None,
) -> DemData:
    with rasterio.open(path) as dataset:
        array = dataset.read(band, window=window)
        transform = dataset.transform
        bounds = tuple(dataset.bounds)
        width = dataset.width
        height = dataset.height
        if window is not None:
            transform = window_transform(window, dataset.transform)
            bounds = tuple(dataset.window_bounds(window))
            width = int(window.width)
            height = int(window.height)
        metadata = DemMetadata(
            path=path,
            width=width,
            height=height,
            count=dataset.count,
            dtype=dataset.dtypes[band - 1],
            crs=dataset.crs,
            transform=transform,
            nodata=dataset.nodata,
            bounds=bounds,
            resolution=dataset.res,
        )
    return DemData(array=array, metadata=metadata)


def read_band(
    path: Path,
    *,
    band: int = 1,
    window: Window | None = None,
) -> np.ndarray:
    return read_dem(path, band=band, window=window).array


def save_geotiff(
    path: Path,
    array: np.ndarray,
    *,
    crs: CRS | str | None,
    transform: Affine,
    nodata: float | int | None,
    dtype: str | None = None,
    extra_profile: dict[str, Any] | None = None,
) -> Path:
    if array.ndim != 2:
        raise ValueError("save_geotiff expects a 2D single-band array")

    path.parent.mkdir(parents=True, exist_ok=True)
    target_dtype = dtype or str(array.dtype)
    profile: dict[str, Any] = {
        "driver": "GTiff",
        "height": array.shape[0],
        "width": array.shape[1],
        "count": 1,
        "dtype": target_dtype,
        "crs": crs,
        "transform": transform,
        "nodata": nodata,
    }
    if extra_profile:
        profile.update(extra_profile)

    with rasterio.open(path, "w", **profile) as dataset:
        dataset.write(array.astype(target_dtype, copy=False), 1)

    return path
