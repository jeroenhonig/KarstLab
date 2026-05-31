"""GDAL VRT mosaic helpers for DEM tile assembly."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

import rasterio
from affine import Affine


@dataclass(frozen=True)
class VrtTile:
    path: Path
    width: int
    height: int
    col_off: int
    row_off: int


@dataclass(frozen=True)
class VrtMosaic:
    path: Path
    width: int
    height: int
    transform: Affine
    crs_wkt: str
    dtype: str
    nodata: float | int | None
    tiles: tuple[VrtTile, ...]


GDAL_DTYPE_BY_RASTERIO = {
    "uint8": "Byte",
    "uint16": "UInt16",
    "int16": "Int16",
    "uint32": "UInt32",
    "int32": "Int32",
    "float32": "Float32",
    "float64": "Float64",
}
GRID_ALIGNMENT_TOLERANCE = 1e-6


def assemble_vrt(tile_paths: list[Path], vrt_path: Path) -> VrtMosaic:
    if not tile_paths:
        raise ValueError("assemble_vrt requires at least one tile")

    datasets: list[rasterio.io.DatasetReader] = []
    try:
        for path in tile_paths:
            datasets.append(rasterio.open(path))

        reference = datasets[0]
        _validate_datasets(datasets)

        xres, yres = reference.res
        min_x = min(dataset.bounds.left for dataset in datasets)
        min_y = min(dataset.bounds.bottom for dataset in datasets)
        max_x = max(dataset.bounds.right for dataset in datasets)
        max_y = max(dataset.bounds.top for dataset in datasets)
        width = round((max_x - min_x) / xres)
        height = round((max_y - min_y) / yres)
        transform = Affine.translation(min_x, max_y) * Affine.scale(xres, -yres)

        gdal_dtype = _gdal_dtype(reference.dtypes[0])
        tiles = tuple(
            VrtTile(
                path=Path(dataset.name),
                width=dataset.width,
                height=dataset.height,
                col_off=_grid_offset(
                    (dataset.bounds.left - min_x) / xres,
                    dataset_name=dataset.name,
                    axis="column",
                ),
                row_off=_grid_offset(
                    (max_y - dataset.bounds.top) / yres,
                    dataset_name=dataset.name,
                    axis="row",
                ),
            )
            for dataset in datasets
        )
        mosaic = VrtMosaic(
            path=vrt_path,
            width=width,
            height=height,
            transform=transform,
            crs_wkt=reference.crs.to_wkt(),
            dtype=reference.dtypes[0],
            nodata=reference.nodata,
            tiles=tiles,
        )
        _write_vrt(mosaic, gdal_dtype=gdal_dtype)
        return mosaic
    finally:
        for dataset in datasets:
            dataset.close()


def assemble_geotiff(vrt_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(vrt_path) as source:
        profile = source.profile.copy()
        profile.update(driver="GTiff")
        profile.pop("blockxsize", None)
        profile.pop("blockysize", None)
        profile.pop("tiled", None)
        with rasterio.open(output_path, "w", **profile) as destination:
            for band in range(1, source.count + 1):
                destination.write(source.read(band), band)
    return output_path


def _validate_datasets(datasets: list[rasterio.io.DatasetReader]) -> None:
    reference = datasets[0]
    if reference.count != 1:
        raise ValueError("VRT assembly currently supports single-band DEM tiles only")
    if reference.crs is None:
        raise ValueError(f"Tile has no CRS: {reference.name}")
    if reference.transform.b != 0 or reference.transform.d != 0:
        raise ValueError("VRT assembly requires north-up rasters without rotation")

    for dataset in datasets[1:]:
        if dataset.count != reference.count:
            raise ValueError("All tiles must have the same band count")
        if dataset.crs != reference.crs:
            raise ValueError("All tiles must have the same CRS")
        if dataset.res != reference.res:
            raise ValueError("All tiles must have the same resolution")
        if dataset.dtypes != reference.dtypes:
            raise ValueError("All tiles must have the same dtype")
        if dataset.nodata != reference.nodata:
            raise ValueError("All tiles must have the same NoData value")
        if dataset.transform.b != 0 or dataset.transform.d != 0:
            raise ValueError("VRT assembly requires north-up rasters without rotation")


def _write_vrt(mosaic: VrtMosaic, *, gdal_dtype: str) -> None:
    mosaic.path.parent.mkdir(parents=True, exist_ok=True)

    nodata_xml = (
        f"    <NoDataValue>{mosaic.nodata}</NoDataValue>\n" if mosaic.nodata is not None else ""
    )
    sources = "\n".join(
        _source_xml(mosaic.path, tile, gdal_dtype=gdal_dtype) for tile in mosaic.tiles
    )
    xml = f"""<VRTDataset rasterXSize="{mosaic.width}" rasterYSize="{mosaic.height}">
  <SRS>{escape(mosaic.crs_wkt)}</SRS>
  <GeoTransform>{_geo_transform(mosaic.transform)}</GeoTransform>
  <VRTRasterBand dataType="{gdal_dtype}" band="1">
{nodata_xml}{sources}
  </VRTRasterBand>
</VRTDataset>
"""
    mosaic.path.write_text(xml, encoding="utf-8")


def _source_xml(vrt_path: Path, tile: VrtTile, *, gdal_dtype: str) -> str:
    source_path = escape(os.path.relpath(tile.path, vrt_path.parent))
    source_properties = (
        f'<SourceProperties RasterXSize="{tile.width}" RasterYSize="{tile.height}" '
        f'DataType="{gdal_dtype}" BlockXSize="{tile.width}" BlockYSize="1" />'
    )
    dst_rect = (
        f'<DstRect xOff="{tile.col_off}" yOff="{tile.row_off}" '
        f'xSize="{tile.width}" ySize="{tile.height}" />'
    )
    return f"""    <SimpleSource>
      <SourceFilename relativeToVRT="1">{source_path}</SourceFilename>
      <SourceBand>1</SourceBand>
      {source_properties}
      <SrcRect xOff="0" yOff="0" xSize="{tile.width}" ySize="{tile.height}" />
      {dst_rect}
    </SimpleSource>"""


def _geo_transform(transform: Affine) -> str:
    values = (transform.c, transform.a, transform.b, transform.f, transform.d, transform.e)
    return ", ".join(f"{value:.16g}" for value in values)


def _gdal_dtype(rasterio_dtype: str) -> str:
    gdal_dtype = GDAL_DTYPE_BY_RASTERIO.get(rasterio_dtype)
    if gdal_dtype is None:
        raise ValueError(f"Unsupported VRT dtype: {rasterio_dtype}")
    return gdal_dtype


def _grid_offset(raw_offset: float, *, dataset_name: str, axis: str) -> int:
    rounded = round(raw_offset)
    if abs(raw_offset - rounded) > GRID_ALIGNMENT_TOLERANCE:
        raise ValueError(
            f"Tile {dataset_name} is not grid-aligned ({axis} offset {raw_offset})"
        )
    return rounded
