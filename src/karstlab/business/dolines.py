"""Doline detection using a fill-subtract depression depth raster."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import numpy as np
from affine import Affine
from numpy.typing import NDArray
from pyproj import Transformer
from rasterio.crs import CRS
from scipy import ndimage

from karstlab.data.schemas import (
    Coordinate,
    DepressionQualityFlags,
    DepressionResult,
    DepthConfidence,
)


@dataclass(frozen=True)
class DolineDetectionParams:
    min_depth_m: float = 0.25
    max_depth_m: float = 40.0
    min_area_m2: float = 1.0
    max_area_m2: float = 60_000.0
    edge_buffer_cells: int = 1


@dataclass(frozen=True)
class DolineDetector:
    params: DolineDetectionParams = DolineDetectionParams()

    def detect(
        self,
        original_dem: np.ndarray,
        filled_dem: np.ndarray,
        *,
        transform: Affine,
        crs: CRS | str | None = None,
        nodata: float | int | None = None,
    ) -> list[DepressionResult]:
        original = _as_2d_float(original_dem, name="original_dem")
        filled = _as_2d_float(filled_dem, name="filled_dem")
        if original.shape != filled.shape:
            raise ValueError("original_dem and filled_dem must have the same shape")

        nodata_mask = _nodata_mask(original, nodata) | _nodata_mask(filled, nodata)
        depth = np.maximum(filled - original, 0.0)
        depth[nodata_mask] = 0.0
        candidate_mask = depth >= self.params.min_depth_m

        labels, count = ndimage.label(candidate_mask)
        pixel_area = abs(transform.a * transform.e)
        depressions: list[DepressionResult] = []
        for label_id in range(1, count + 1):
            component = labels == label_id
            max_depth = float(np.max(depth[component]))
            area = float(np.count_nonzero(component) * pixel_area)
            if not self._passes_filters(max_depth=max_depth, area=area):
                continue

            rows, cols = np.where(component)
            centroid = _centroid(rows, cols, transform, crs=crs)
            depressions.append(
                DepressionResult(
                    id=f"doline-{len(depressions) + 1:04d}",
                    max_depth_m=max_depth,
                    area_m2=area,
                    centroid=centroid,
                    geometry=_component_polygon(rows, cols, transform),
                    quality_flags=DepressionQualityFlags(
                        edge_proximity=_touches_edge(component, self.params.edge_buffer_cells),
                        nodata_adjacent=_adjacent_to_nodata(component, nodata_mask),
                        depth_confidence=_depth_confidence(max_depth),
                        shape_regularity=_shape_regularity(component),
                        nested=False,
                    ),
                )
            )
        return depressions

    def _passes_filters(self, *, max_depth: float, area: float) -> bool:
        return (
            self.params.min_depth_m <= max_depth <= self.params.max_depth_m
            and self.params.min_area_m2 <= area <= self.params.max_area_m2
        )


def detect_dolines(
    original_dem: np.ndarray,
    filled_dem: np.ndarray,
    *,
    transform: Affine,
    crs: CRS | str | None = None,
    nodata: float | int | None = None,
    params: DolineDetectionParams | None = None,
) -> list[DepressionResult]:
    return DolineDetector(params=params or DolineDetectionParams()).detect(
        original_dem,
        filled_dem,
        transform=transform,
        crs=crs,
        nodata=nodata,
    )


def _as_2d_float(array: np.ndarray, *, name: str) -> np.ndarray:
    result = np.asarray(array, dtype=np.float64)
    if result.ndim != 2:
        raise ValueError(f"{name} must be a 2D array")
    return result


def _nodata_mask(array: np.ndarray, nodata: float | int | None) -> np.ndarray:
    if nodata is None:
        return np.zeros(array.shape, dtype=bool)
    if np.isnan(nodata):
        return cast(NDArray[np.bool_], np.isnan(array))
    return cast(NDArray[np.bool_], array == nodata)


def _centroid(
    rows: np.ndarray,
    cols: np.ndarray,
    transform: Affine,
    *,
    crs: CRS | str | None,
) -> Coordinate:
    row = float(np.mean(rows))
    col = float(np.mean(cols))
    x, y = transform * (col + 0.5, row + 0.5)
    if crs is not None and CRS.from_user_input(crs) != CRS.from_epsg(4326):
        x, y = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(x, y)
    return Coordinate(lat=float(y), lon=float(x))


def _component_polygon(rows: np.ndarray, cols: np.ndarray, transform: Affine) -> dict[str, object]:
    min_row = int(np.min(rows))
    max_row = int(np.max(rows)) + 1
    min_col = int(np.min(cols))
    max_col = int(np.max(cols)) + 1
    top_left = transform * (min_col, min_row)
    top_right = transform * (max_col, min_row)
    bottom_right = transform * (max_col, max_row)
    bottom_left = transform * (min_col, max_row)
    return {
        "type": "Polygon",
        "coordinates": [[top_left, top_right, bottom_right, bottom_left, top_left]],
    }


def _touches_edge(mask: np.ndarray, edge_buffer_cells: int) -> bool:
    rows, cols = np.where(mask)
    max_row = mask.shape[0] - 1
    max_col = mask.shape[1] - 1
    return bool(
        np.min(rows) <= edge_buffer_cells
        or np.min(cols) <= edge_buffer_cells
        or np.max(rows) >= max_row - edge_buffer_cells
        or np.max(cols) >= max_col - edge_buffer_cells
    )


def _adjacent_to_nodata(component: np.ndarray, nodata_mask: np.ndarray) -> bool:
    if not np.any(nodata_mask):
        return False
    expanded = ndimage.binary_dilation(component, structure=np.ones((3, 3), dtype=bool))
    border = expanded & ~component
    return bool(np.any(border & nodata_mask))


def _depth_confidence(max_depth: float) -> DepthConfidence:
    if max_depth >= 2.0:
        return DepthConfidence.HIGH
    if max_depth >= 0.5:
        return DepthConfidence.MEDIUM
    return DepthConfidence.LOW


def _shape_regularity(component: np.ndarray) -> float:
    area = float(np.count_nonzero(component))
    eroded = ndimage.binary_erosion(component, structure=np.ones((3, 3), dtype=bool))
    perimeter = float(np.count_nonzero(component & ~eroded))
    if perimeter == 0:
        return 1.0
    compactness = (4.0 * np.pi * area) / (perimeter * perimeter)
    return float(np.clip(compactness, 0.0, 1.0))
