"""CRS detection and raster reprojection helpers."""

from __future__ import annotations

from pathlib import Path

import rasterio
from rasterio.crs import CRS
from rasterio.warp import Resampling, calculate_default_transform, reproject


def detect_crs(path: Path) -> CRS:
    with rasterio.open(path) as dataset:
        if dataset.crs is None:
            raise ValueError(f"Raster has no CRS: {path}")
        return dataset.crs


def is_metric_crs(crs: CRS | str) -> bool:
    resolved = CRS.from_user_input(crs)
    return bool(resolved.is_projected and resolved.linear_units_factor[0] == "metre")


def to_metric(
    source_path: Path,
    target_path: Path,
    *,
    target_crs: CRS | str,
    resampling: Resampling = Resampling.bilinear,
) -> Path:
    if not is_metric_crs(target_crs):
        raise ValueError(f"target_crs is not metric: {target_crs}")

    return reproject_raster(
        source_path,
        target_path,
        target_crs=target_crs,
        resampling=resampling,
    )


def to_wgs84(
    source_path: Path,
    target_path: Path,
    *,
    resampling: Resampling = Resampling.nearest,
) -> Path:
    return reproject_raster(
        source_path,
        target_path,
        target_crs="EPSG:4326",
        resampling=resampling,
    )


def reproject_raster(
    source_path: Path,
    target_path: Path,
    *,
    target_crs: CRS | str,
    resampling: Resampling = Resampling.bilinear,
) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    destination_crs = CRS.from_user_input(target_crs)

    with rasterio.open(source_path) as source:
        if source.crs is None:
            raise ValueError(f"Raster has no CRS: {source_path}")

        transform, width, height = calculate_default_transform(
            source.crs,
            destination_crs,
            source.width,
            source.height,
            *source.bounds,
        )
        profile = source.profile.copy()
        profile.update(
            {
                "crs": destination_crs,
                "transform": transform,
                "width": width,
                "height": height,
            }
        )

        with rasterio.open(target_path, "w", **profile) as destination:
            for band in range(1, source.count + 1):
                reproject(
                    source=rasterio.band(source, band),
                    destination=rasterio.band(destination, band),
                    src_transform=source.transform,
                    src_crs=source.crs,
                    src_nodata=source.nodata,
                    dst_transform=transform,
                    dst_crs=destination_crs,
                    dst_nodata=source.nodata,
                    resampling=resampling,
                )

    return target_path
