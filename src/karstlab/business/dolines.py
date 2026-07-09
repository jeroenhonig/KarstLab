"""Doline detection using a fill-subtract depression depth raster."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import numpy as np
import shapely.geometry as sgeom
from affine import Affine
from numpy.typing import NDArray
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.features import shapes as _raster_shapes
from scipy import ndimage
from shapely.geometry.base import BaseGeometry

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
        depth: np.ndarray | None = None,
    ) -> list[DepressionResult]:
        if crs is None:
            raise ValueError("crs is required for WGS84 depression centroid and geometry output")

        original = _as_2d_float(original_dem, name="original_dem")
        filled = _as_2d_float(filled_dem, name="filled_dem")
        if original.shape != filled.shape:
            raise ValueError("original_dem and filled_dem must have the same shape")

        nodata_mask = _nodata_mask(original, nodata) | _nodata_mask(filled, nodata)
        # Reuse a depth raster the caller already computed (e.g. the pipeline
        # saves it as an export) instead of recomputing the full-array
        # fill-minus-original subtraction a second time here.
        if depth is None:
            depth = depression_depth_raster(original, filled, nodata=nodata)
        else:
            depth = _as_2d_float(depth, name="depth")
            if depth.shape != original.shape:
                raise ValueError("depth raster must match the DEM shape")
        candidate_mask = depth >= self.params.min_depth_m

        labels, count = ndimage.label(candidate_mask)
        if count == 0:
            return []
        # ``find_objects`` returns the tight bounding-box slice for every label so
        # each component is processed on its small sub-array instead of scanning
        # the full raster once per label (the old O(labels x pixels) loop).
        slices = ndimage.find_objects(labels)
        pixel_area = abs((transform.a * transform.e) - (transform.b * transform.d))
        transformer = _wgs84_transformer(crs)
        has_nodata = bool(np.any(nodata_mask))
        full_shape = labels.shape
        depressions: list[DepressionResult] = []
        for label_id, bounds in enumerate(slices, start=1):
            if bounds is None:
                continue
            row_offset = bounds[0].start
            col_offset = bounds[1].start
            sub_component = labels[bounds] == label_id
            sub_depth = depth[bounds]
            max_depth = float(np.max(sub_depth[sub_component]))
            area = float(np.count_nonzero(sub_component) * pixel_area)
            if not self._passes_filters(max_depth=max_depth, area=area):
                continue

            rows_local, cols_local = np.where(sub_component)
            rows = rows_local + row_offset
            cols = cols_local + col_offset
            centroid = _centroid(rows, cols, transform, transformer=transformer)
            depressions.append(
                DepressionResult(
                    id=f"doline-{len(depressions) + 1:04d}",
                    max_depth_m=max_depth,
                    area_m2=area,
                    centroid=centroid,
                    geometry=_component_polygon(
                        sub_component,
                        transform,
                        transformer=transformer,
                        row_offset=row_offset,
                        col_offset=col_offset,
                    ),
                    quality_flags=DepressionQualityFlags(
                        edge_proximity=_touches_edge_bounds(
                            rows, cols, full_shape, self.params.edge_buffer_cells
                        ),
                        nodata_adjacent=_adjacent_to_nodata(
                            sub_component, row_offset, col_offset, nodata_mask, has_nodata
                        ),
                        depth_confidence=_depth_confidence(max_depth),
                        shape_regularity=_shape_regularity(sub_component),
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
    depth: np.ndarray | None = None,
) -> list[DepressionResult]:
    return DolineDetector(params=params or DolineDetectionParams()).detect(
        original_dem,
        filled_dem,
        transform=transform,
        crs=crs,
        nodata=nodata,
        depth=depth,
    )


def _as_2d_float(array: np.ndarray, *, name: str) -> np.ndarray:
    # Keep a float32 DEM at float32; only promote non-float inputs (int tiles)
    # to float64 so NaN-based nodata masking stays valid. Halves the working
    # footprint of the depth raster and detection masks on float32 DEMs.
    result = np.asarray(array)
    if not np.issubdtype(result.dtype, np.floating):
        result = result.astype(np.float64)
    if result.ndim != 2:
        raise ValueError(f"{name} must be a 2D array")
    return result


def depression_depth_raster(
    original: np.ndarray,
    filled: np.ndarray,
    *,
    nodata: float | int | None = None,
) -> NDArray[np.float64]:
    """Return the fill-minus-original depression depth, clipped to >= 0.

    Cells flagged as nodata in either the original or the filled DEM are set to
    0.0 using the same NaN-aware masking the detector applies, so an exported
    depth raster matches the depths used during doline detection.
    """
    original = _as_2d_float(original, name="original_dem")
    filled = _as_2d_float(filled, name="filled_dem")
    depth = np.maximum(filled - original, 0.0)
    depth[_nodata_mask(original, nodata) | _nodata_mask(filled, nodata)] = 0.0
    return cast(NDArray[np.float64], depth)


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
    transformer: Transformer | None,
) -> Coordinate:
    row = float(np.mean(rows))
    col = float(np.mean(cols))
    x, y = _to_wgs84(transform * (col + 0.5, row + 0.5), transformer=transformer)
    return Coordinate(lat=float(y), lon=float(x))


def _component_polygon(
    component: np.ndarray,
    transform: Affine,
    *,
    transformer: Transformer | None,
    row_offset: int = 0,
    col_offset: int = 0,
) -> dict[str, object]:
    """Vectorise the true outline of a depression component (not its bbox).

    Uses ``rasterio.features.shapes`` on the component mask (cropped to its
    bounding box for speed), keeps the largest ring set, lightly simplifies the
    pixel staircase, and reprojects vertices to WGS84. ``row_offset``/``col_offset``
    map the local ``(0, 0)`` of ``component`` back to its global pixel position
    when the mask is a bounding-box sub-array of the full raster.
    """
    rows, cols = np.where(component)
    min_row, max_row = int(np.min(rows)), int(np.max(rows)) + 1
    min_col, max_col = int(np.min(cols)), int(np.max(cols)) + 1
    sub = np.ascontiguousarray(component[min_row:max_row, min_col:max_col].astype(np.uint8))
    sub_transform = transform * Affine.translation(col_offset + min_col, row_offset + min_row)

    polygons = [
        sgeom.shape(geom)
        for geom, value in _raster_shapes(sub, mask=sub.astype(bool), transform=sub_transform)
        if value == 1
    ]
    if not polygons:
        return _bbox_polygon(
            row_offset + min_row,
            row_offset + max_row,
            col_offset + min_col,
            col_offset + max_col,
            transform,
            transformer,
        )

    polygon: BaseGeometry = max(polygons, key=lambda geometry: geometry.area)
    tolerance = abs(float(transform.a))  # ~one pixel: smooth the staircase, keep shape
    simplified = polygon.simplify(tolerance, preserve_topology=True)
    if not simplified.is_empty and simplified.geom_type in {"Polygon", "MultiPolygon"}:
        polygon = simplified
    if polygon.geom_type == "MultiPolygon":
        polygon = max(polygon.geoms, key=lambda geometry: geometry.area)

    return _reproject_polygon(sgeom.mapping(polygon), transformer=transformer)


def _reproject_polygon(
    geometry: dict[str, object],
    *,
    transformer: Transformer | None,
) -> dict[str, object]:
    rings = cast("list[list[tuple[float, float]]]", geometry["coordinates"])
    reprojected = [
        [list(_to_wgs84((x, y), transformer=transformer)) for x, y in ring] for ring in rings
    ]
    return {"type": "Polygon", "coordinates": reprojected}


def _bbox_polygon(
    min_row: int,
    max_row: int,
    min_col: int,
    max_col: int,
    transform: Affine,
    transformer: Transformer | None,
) -> dict[str, object]:
    top_left = _to_wgs84(transform * (min_col, min_row), transformer=transformer)
    top_right = _to_wgs84(transform * (max_col, min_row), transformer=transformer)
    bottom_right = _to_wgs84(transform * (max_col, max_row), transformer=transformer)
    bottom_left = _to_wgs84(transform * (min_col, max_row), transformer=transformer)
    return {
        "type": "Polygon",
        "coordinates": [[top_left, top_right, bottom_right, bottom_left, top_left]],
    }


def _touches_edge_bounds(
    rows: np.ndarray,
    cols: np.ndarray,
    full_shape: tuple[int, int],
    edge_buffer_cells: int,
) -> bool:
    """Edge proximity from a component's global row/col indices and raster shape."""
    max_row = full_shape[0] - 1
    max_col = full_shape[1] - 1
    return bool(
        np.min(rows) <= edge_buffer_cells
        or np.min(cols) <= edge_buffer_cells
        or np.max(rows) >= max_row - edge_buffer_cells
        or np.max(cols) >= max_col - edge_buffer_cells
    )


def _adjacent_to_nodata(
    sub_component: np.ndarray,
    row_offset: int,
    col_offset: int,
    nodata_mask: np.ndarray,
    has_nodata: bool,
) -> bool:
    """Test nodata adjacency by dilating the component within a 1-cell padded window.

    Operates on a small region around the component's bounding box rather than
    dilating the full raster, while still reaching the one-cell border that may
    fall outside the tight bounding box.
    """
    if not has_nodata:
        return False
    height, width = sub_component.shape
    full_rows, full_cols = nodata_mask.shape
    row_start = max(row_offset - 1, 0)
    col_start = max(col_offset - 1, 0)
    row_stop = min(row_offset + height + 1, full_rows)
    col_stop = min(col_offset + width + 1, full_cols)

    region = np.zeros((row_stop - row_start, col_stop - col_start), dtype=bool)
    region[
        row_offset - row_start : row_offset - row_start + height,
        col_offset - col_start : col_offset - col_start + width,
    ] = sub_component
    expanded = ndimage.binary_dilation(region, structure=np.ones((3, 3), dtype=bool))
    border = expanded & ~region
    return bool(np.any(border & nodata_mask[row_start:row_stop, col_start:col_stop]))


def _depth_confidence(max_depth: float) -> DepthConfidence:
    """Map depth to confidence: LOW <0.5m, MEDIUM 0.5-2m, HIGH >=2m."""
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


def _wgs84_transformer(crs: CRS | str) -> Transformer | None:
    source_crs = CRS.from_user_input(crs)
    if source_crs == CRS.from_epsg(4326):
        return None
    return Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)


def _to_wgs84(
    coordinate: tuple[float, float],
    *,
    transformer: Transformer | None,
) -> tuple[float, float]:
    if transformer is None:
        return float(coordinate[0]), float(coordinate[1])
    x, y = transformer.transform(coordinate[0], coordinate[1])
    return float(x), float(y)
