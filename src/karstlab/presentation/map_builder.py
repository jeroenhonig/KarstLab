"""Folium map rendering helpers for ranked depression results."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Protocol, TypeGuard, cast

import folium
from folium.raster_layers import ImageOverlay, WmsTileLayer

from karstlab.data.schemas import DepressionResult


class GeoInterface(Protocol):
    """Object exposing a GeoJSON-compatible feature collection."""

    @property
    def __geo_interface__(self) -> Mapping[str, Any]: ...


GeoJsonLike = Mapping[str, Any] | GeoInterface
StyleFunction = Callable[[Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class MapLayerSpec:
    """Optional vector layer definition for Folium overlays."""

    name: str
    data: GeoJsonLike
    show: bool = False
    style: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ImageLayerSpec:
    """Optional raster image overlay definition for Folium overlays."""

    name: str
    image: str | Path | Any
    bounds: Sequence[Sequence[float]]
    show: bool = False
    opacity: float = 0.65


@dataclass(frozen=True, slots=True)
class TileLayerSpec:
    """Extra XYZ/WMTS basemap shown as a radio option in the layer control."""

    name: str
    url: str  # XYZ template: {z}/{x}/{y}
    attribution: str
    show: bool = False


@dataclass(frozen=True, slots=True)
class WmsLayerSpec:
    """WMS overlay shown as a checkbox in the layer control."""

    name: str
    url: str
    layers: str  # WMS layer name(s)
    attribution: str
    fmt: str = "image/png"
    transparent: bool = True
    version: str = "1.3.0"
    show: bool = False


MapLayerInput = MapLayerSpec | Sequence[MapLayerSpec] | GeoJsonLike | None
ImageLayerInput = ImageLayerSpec | Sequence[ImageLayerSpec] | None


def build_top_depressions_map(
    depressions: Sequence[DepressionResult],
    *,
    hillshade_layers: ImageLayerInput = (),
    hillshade_layer: ImageLayerSpec | None = None,
    contour_layers: Sequence[MapLayerSpec] = (),
    stream_layers: Sequence[MapLayerSpec] = (),
    vector_layers: Sequence[MapLayerSpec] = (),
    imported_marker_layers: MapLayerInput = (),
    imported_markers: GeoJsonLike | None = None,
    extra_tile_layers: Sequence[TileLayerSpec] = (),
    wms_layers: Sequence[WmsLayerSpec] = (),
    max_results: int = 25,
    tiles: str = "OpenStreetMap",
    tile_attribution: str | None = None,
    zoom_start: int = 13,
) -> folium.Map:
    """Build an interactive Folium map for the top ranked depression results."""

    if max_results < 1:
        raise ValueError("max_results must be positive")

    selected = list(depressions[:max_results])
    location = _initial_location(selected)
    if tiles.startswith("http"):
        folium_map = folium.Map(location=location, zoom_start=zoom_start, tiles=None)
        folium.TileLayer(
            tiles=tiles,
            attr=tile_attribution or "",
            name="Base map",
        ).add_to(folium_map)
    else:
        folium_map = folium.Map(location=location, zoom_start=zoom_start, tiles=tiles)

    _add_basemaps(folium_map, extra_tile_layers)
    _add_wms_overlays(folium_map, wms_layers)
    _add_depression_geometries(folium_map, selected)
    _add_numbered_markers(folium_map, selected)
    _add_image_layers(folium_map, "Hillshade", _image_layers(hillshade_layers, hillshade_layer))
    _add_overlay_layers(folium_map, "Contours", contour_layers)
    _add_overlay_layers(folium_map, "Streams", stream_layers)
    _add_overlay_layers(folium_map, "Vectors", vector_layers)
    _add_overlay_layers(
        folium_map,
        "Imported markers",
        _map_layers(imported_marker_layers, "Imported markers", imported_markers),
    )

    folium.LayerControl(collapsed=False).add_to(folium_map)
    return folium_map


def render_top_depressions_map_html(
    depressions: Sequence[DepressionResult],
    *,
    hillshade_layers: ImageLayerInput = (),
    hillshade_layer: ImageLayerSpec | None = None,
    contour_layers: Sequence[MapLayerSpec] = (),
    stream_layers: Sequence[MapLayerSpec] = (),
    vector_layers: Sequence[MapLayerSpec] = (),
    imported_marker_layers: MapLayerInput = (),
    imported_markers: GeoJsonLike | None = None,
    extra_tile_layers: Sequence[TileLayerSpec] = (),
    wms_layers: Sequence[WmsLayerSpec] = (),
    max_results: int = 25,
    tiles: str = "OpenStreetMap",
    tile_attribution: str | None = None,
    zoom_start: int = 13,
) -> str:
    """Render the top depression Folium map to a standalone HTML document."""

    return (
        build_top_depressions_map(
            depressions,
            hillshade_layers=hillshade_layers,
            hillshade_layer=hillshade_layer,
            contour_layers=contour_layers,
            stream_layers=stream_layers,
            vector_layers=vector_layers,
            imported_marker_layers=imported_marker_layers,
            imported_markers=imported_markers,
            extra_tile_layers=extra_tile_layers,
            wms_layers=wms_layers,
            max_results=max_results,
            tiles=tiles,
            tile_attribution=tile_attribution,
            zoom_start=zoom_start,
        )
        .get_root()
        .render()
    )


def _add_basemaps(folium_map: folium.Map, specs: Sequence[TileLayerSpec]) -> None:
    for spec in specs:
        folium.TileLayer(
            tiles=spec.url,
            attr=spec.attribution,
            name=spec.name,
            show=spec.show,
            overlay=False,
            control=True,
        ).add_to(folium_map)


def _add_wms_overlays(folium_map: folium.Map, specs: Sequence[WmsLayerSpec]) -> None:
    for spec in specs:
        WmsTileLayer(
            url=spec.url,
            layers=spec.layers,
            name=spec.name,
            fmt=spec.fmt,
            transparent=spec.transparent,
            version=spec.version,
            attr=spec.attribution,
            show=spec.show,
            overlay=True,
            control=True,
        ).add_to(folium_map)


def _initial_location(depressions: Sequence[DepressionResult]) -> tuple[float, float]:
    if not depressions:
        raise ValueError("depressions must contain at least one result")

    lat = sum(depression.centroid.lat for depression in depressions) / len(depressions)
    lon = sum(depression.centroid.lon for depression in depressions) / len(depressions)
    return (lat, lon)


def _add_depression_geometries(
    folium_map: folium.Map, depressions: Sequence[DepressionResult]
) -> None:
    if not depressions:
        return

    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": depression.geometry,
                "properties": _depression_properties(depression, index),
            }
            for index, depression in enumerate(depressions, start=1)
        ],
    }
    folium.GeoJson(
        feature_collection,
        name="Top 25 depression footprints",
        tooltip=folium.GeoJsonTooltip(
            fields=["rank", "id", "max_depth_m", "area_m2"],
            aliases=["Rank", "ID", "Depth (m)", "Area (m2)"],
        ),
        style_function=lambda _feature: {
            "color": "#0f766e",
            "fillColor": "#14b8a6",
            "fillOpacity": 0.25,
            "weight": 2,
        },
    ).add_to(folium_map)


def _add_numbered_markers(folium_map: folium.Map, depressions: Sequence[DepressionResult]) -> None:
    marker_group = folium.FeatureGroup(name="Top 25 depression markers", show=True)
    for index, depression in enumerate(depressions, start=1):
        number = depression.rank if depression.rank is not None else index
        safe_id = escape(depression.id, quote=True)
        folium.Marker(
            location=(depression.centroid.lat, depression.centroid.lon),
            tooltip=f"#{number} {safe_id}",
            popup=folium.Popup(_popup_html(depression, number), max_width=260),
            icon=folium.DivIcon(
                html=(
                    '<div class="karstlab-rank-marker" '
                    'style="background:#0f766e;color:white;border:2px solid white;'
                    "border-radius:50%;box-shadow:0 1px 4px rgba(0,0,0,.35);"
                    "font:700 12px/24px sans-serif;height:24px;text-align:center;"
                    f'width:24px;">{number}</div>'
                ),
                icon_size=(24, 24),
                icon_anchor=(12, 12),
            ),
        ).add_to(marker_group)
    marker_group.add_to(folium_map)


def _image_layers(
    layers: ImageLayerInput, additional_layer: ImageLayerSpec | None = None
) -> tuple[ImageLayerSpec, ...]:
    if layers is None:
        normalized: tuple[ImageLayerSpec, ...] = ()
    elif isinstance(layers, ImageLayerSpec):
        normalized = (layers,)
    else:
        normalized = tuple(layers)

    if additional_layer is None:
        return normalized
    return (*normalized, additional_layer)


def _add_image_layers(
    folium_map: folium.Map, group_name: str, layers: Sequence[ImageLayerSpec]
) -> None:
    for layer in layers:
        ImageOverlay(
            image=str(layer.image) if isinstance(layer.image, Path) else layer.image,
            bounds=layer.bounds,
            name=f"{group_name}: {layer.name}",
            opacity=layer.opacity,
            show=layer.show,
        ).add_to(folium_map)


def _map_layers(
    layers: MapLayerInput,
    default_name: str,
    additional_data: GeoJsonLike | None = None,
) -> tuple[MapLayerSpec, ...]:
    if layers is None:
        normalized: tuple[MapLayerSpec, ...] = ()
    elif isinstance(layers, MapLayerSpec):
        normalized = (layers,)
    elif _is_geojson_like(layers):
        normalized = (MapLayerSpec(name=default_name, data=layers, show=True),)
    else:
        normalized = tuple(cast(Sequence[MapLayerSpec], layers))

    if additional_data is None:
        return normalized
    return (*normalized, MapLayerSpec(name=default_name, data=additional_data, show=True))


def _add_overlay_layers(
    folium_map: folium.Map, group_name: str, layers: Sequence[MapLayerSpec]
) -> None:
    for layer in layers:
        folium.GeoJson(
            _geojson_data(layer.data),
            name=f"{group_name}: {layer.name}",
            show=layer.show,
            style_function=_style_function(layer.style),
        ).add_to(folium_map)


def _style_function(style: Mapping[str, Any] | None) -> StyleFunction | None:
    if style is None:
        return None
    return lambda _feature: dict(style)


def _geojson_data(data: GeoJsonLike) -> Mapping[str, Any]:
    if isinstance(data, Mapping):
        return data
    return data.__geo_interface__


def _is_geojson_like(data: object) -> TypeGuard[GeoJsonLike]:
    return isinstance(data, Mapping) or hasattr(data, "__geo_interface__")


def _depression_properties(depression: DepressionResult, index: int) -> dict[str, Any]:
    rank = depression.rank if depression.rank is not None else index
    return {
        "id": depression.id,
        "rank": rank,
        "max_depth_m": round(depression.max_depth_m, 2),
        "area_m2": round(depression.area_m2, 2),
    }


def _popup_html(depression: DepressionResult, number: int) -> str:
    safe_id = escape(depression.id, quote=True)
    return (
        f"<strong>#{number} {safe_id}</strong><br>"
        f"Depth: {depression.max_depth_m:.2f} m<br>"
        f"Area: {depression.area_m2:.1f} m2"
    )
