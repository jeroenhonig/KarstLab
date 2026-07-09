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
from karstlab.presentation import map_palette


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
    # Match the OpenStreetMap base layer's zoom range. Leaflet derives the
    # map's overall max zoom from the *lowest* base-layer maxZoom, so a basemap
    # with a smaller value (Esri defaults to 18) would clamp the whole map and
    # make switching to it jump the view outward.
    max_zoom: int = 19
    max_native_zoom: int = 19
    min_zoom: int = 0


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
    opacity: float = 0.6  # semi-transparent so it never fully hides the basemap/results


MapLayerInput = MapLayerSpec | Sequence[MapLayerSpec] | GeoJsonLike | None
ImageLayerInput = ImageLayerSpec | Sequence[ImageLayerSpec] | None


# Regional zoom floor: below this Leaflet starts repeating the whole world.
_MAP_MIN_ZOOM = 5


def build_top_depressions_map(
    depressions: Sequence[DepressionResult],
    *,
    hillshade_layers: ImageLayerInput = (),
    hillshade_layer: ImageLayerSpec | None = None,
    contour_layers: Sequence[MapLayerSpec] = (),
    stream_layers: Sequence[MapLayerSpec] = (),
    stream_image_layers: Sequence[ImageLayerSpec] = (),
    vector_layers: Sequence[MapLayerSpec] = (),
    all_depressions: Sequence[DepressionResult] = (),
    fault_geojson: GeoJsonLike | None = None,
    conduit_geojson: GeoJsonLike | None = None,
    conduit_candidates: Sequence[DepressionResult] = (),
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
    # Floor the zoom so the map can never fall back to the repeated whole-world
    # view (e.g. when switching to a base layer with a different native range);
    # the analysis area is always regional, so a regional floor is safe.
    if tiles.startswith("http"):
        folium_map = folium.Map(
            location=location, zoom_start=zoom_start, tiles=None, min_zoom=_MAP_MIN_ZOOM
        )
        folium.TileLayer(
            tiles=tiles,
            attr=tile_attribution or "",
            name="Base map",
            max_zoom=19,
            max_native_zoom=19,
            min_zoom=_MAP_MIN_ZOOM,
        ).add_to(folium_map)
    else:
        folium_map = folium.Map(
            location=location, zoom_start=zoom_start, tiles=tiles, min_zoom=_MAP_MIN_ZOOM
        )

    _add_basemaps(folium_map, extra_tile_layers)
    _add_wms_overlays(folium_map, wms_layers)
    faults_present = (
        fault_geojson is not None and _feature_count(_geojson_data(fault_geojson)) > 0
    )
    # Without faults: the orange Top-25 footprints are the headline layer. With
    # faults: the distance-coloured dolines layer is, so the plain orange
    # footprints are skipped (they would mask the distance colours).
    if not faults_present:
        _add_depression_geometries(folium_map, selected)
    _add_all_depression_footprints(folium_map, all_depressions)
    _add_fault_lines(folium_map, fault_geojson)
    _add_numbered_markers(folium_map, selected)
    conduit_present = (
        conduit_geojson is not None and _feature_count(_geojson_data(conduit_geojson)) > 0
    )
    _add_conduit_layers(folium_map, conduit_geojson, conduit_candidates)
    if faults_present or conduit_present:
        _add_map_legend(folium_map, conduit_present=conduit_present)
    _add_image_layers(folium_map, "Hillshade", _image_layers(hillshade_layers, hillshade_layer))
    _add_image_layers(folium_map, "Streams", stream_image_layers)
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
    stream_image_layers: Sequence[ImageLayerSpec] = (),
    vector_layers: Sequence[MapLayerSpec] = (),
    all_depressions: Sequence[DepressionResult] = (),
    fault_geojson: GeoJsonLike | None = None,
    conduit_geojson: GeoJsonLike | None = None,
    conduit_candidates: Sequence[DepressionResult] = (),
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
            stream_image_layers=stream_image_layers,
            vector_layers=vector_layers,
            all_depressions=all_depressions,
            fault_geojson=fault_geojson,
            conduit_geojson=conduit_geojson,
            conduit_candidates=conduit_candidates,
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
            max_zoom=spec.max_zoom,
            max_native_zoom=spec.max_native_zoom,
            min_zoom=spec.min_zoom,
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
            opacity=spec.opacity,
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
            fields=["rank", "id", "max_depth_m", "area_m2", "lat", "lon"],
            aliases=["Rank", "ID", "Depth (m)", "Area (m2)", "Lat", "Lon"],
        ),
        style_function=lambda _feature: {
            # ARIS-style: solid orange doline footprints, clearly visible on the
            # hillshade relief.
            "color": map_palette.TOP25_FOOTPRINT_LINE,
            "fillColor": map_palette.TOP25_FOOTPRINT_FILL,
            "fillOpacity": 0.6,
            "weight": 1,
        },
    ).add_to(folium_map)


# Distance-to-fault colour ramp lives in the central palette (single source of
# truth for all map-layer colours); see karstlab.presentation.map_palette.
_FAULT_DISTANCE_COLORS = map_palette.FAULT_DISTANCE_COLORS
_FAULT_DISTANCE_LABELS: tuple[tuple[str, str], ...] = (
    ("<=50m", "≤ 50 m (on a fault)"),
    ("<=100m", "≤ 100 m"),
    ("<=250m", "≤ 250 m"),
    (">250m", "> 250 m"),
)


def _fault_distance_class(distance_m: float | None) -> str:
    if distance_m is None:
        return "none"
    if distance_m <= 50:
        return "<=50m"
    if distance_m <= 100:
        return "<=100m"
    if distance_m <= 250:
        return "<=250m"
    return ">250m"


def _add_all_depression_footprints(
    folium_map: folium.Map, depressions: Sequence[DepressionResult]
) -> None:
    """Add every detected depression as a footprint layer.

    When fault distances are present the footprints are coloured by distance
    class (red ≤50 m → grey >250 m) and depressions on a fault running parallel
    to the cave line get a bolder outline; the popup carries id/area/depth/fault
    distance/type/orientation. Dropped if it would exceed the overlay budget.
    """
    has_faults = any(d.distance_to_fault_m is not None for d in depressions)
    features = []
    for number, depression in enumerate(depressions, start=1):
        if not depression.geometry:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": depression.geometry,
                "properties": {
                    "n": number,
                    "id": depression.id,
                    "area_m2": round(depression.area_m2, 1),
                    "max_depth_m": round(depression.max_depth_m, 2),
                    "lat": round(depression.centroid.lat, 6),
                    "lon": round(depression.centroid.lon, 6),
                    "fault_m": depression.distance_to_fault_m,
                    "fault_type": depression.nearest_fault_type,
                    "orientation": depression.fault_orientation,
                    "dist_class": _fault_distance_class(depression.distance_to_fault_m),
                },
            }
        )
    if not features or len(features) > _MAX_OVERLAY_FEATURES:
        return

    name = (
        f"Dolines by fault distance ({len(features)})"
        if has_faults
        else f"All depressions ({len(features)})"
    )
    fields = ["n", "id", "area_m2", "max_depth_m", "lat", "lon"]
    aliases = ["#", "ID", "Area (m2)", "Depth (m)", "Lat", "Lon"]
    if has_faults:
        fields[4:4] = ["fault_m", "fault_type", "orientation"]
        aliases[4:4] = ["Fault dist (m)", "Fault type", "Orientation vs cave"]

    folium.GeoJson(
        {"type": "FeatureCollection", "features": features},
        name=name,
        show=True,
        popup=folium.GeoJsonPopup(fields=fields, aliases=aliases),
        tooltip=folium.GeoJsonTooltip(fields=["id", "fault_m"], aliases=["ID", "Fault (m)"]),
        style_function=_depression_fault_style if has_faults else _depression_plain_style,
    ).add_to(folium_map)


def _add_fault_lines(folium_map: folium.Map, fault_geojson: GeoJsonLike | None) -> None:
    """Add the BDCharm50 fault lines: observed solid, supposed dashed."""
    if fault_geojson is None:
        return
    data = _geojson_data(fault_geojson)
    if _feature_count(data) == 0 or _feature_count(data) > _MAX_OVERLAY_FEATURES:
        return
    folium.GeoJson(
        data,
        name="Faults (BDCharm50)",
        show=True,
        tooltip=folium.GeoJsonTooltip(
            fields=["fault_class", "bearing_deg"], aliases=["Fault", "Bearing (deg)"]
        ),
        style_function=_fault_line_style,
    ).add_to(folium_map)


def _conduit_isoline_style(feature: dict[str, Any]) -> dict[str, Any]:
    """Thicker lines for higher relative likelihood; all in the conduit hue."""
    value = feature.get("properties", {}).get("relative_likelihood", 0.0)
    weight = 4.0 if value >= 0.5 else 2.5 if value >= 0.2 else 1.5
    return {
        "color": map_palette.CONDUIT_CORRIDOR,
        "weight": weight,
        "opacity": 0.9,
        "fillOpacity": 0.0,
    }


def _add_conduit_layers(
    folium_map: folium.Map,
    conduit_geojson: GeoJsonLike | None,
    candidates: Sequence[DepressionResult],
) -> None:
    """Add the predicted-conduit corridor isolines + ranked candidate-doline markers."""
    if conduit_geojson is not None:
        data = _geojson_data(conduit_geojson)
        if 0 < _feature_count(data) <= _MAX_OVERLAY_FEATURES:
            folium.GeoJson(
                data,
                name="Predicted conduit corridor",
                show=True,
                tooltip=folium.GeoJsonTooltip(
                    fields=["relative_likelihood"], aliases=["Relative likelihood"]
                ),
                style_function=_conduit_isoline_style,
            ).add_to(folium_map)

    if not candidates:
        return
    group = folium.FeatureGroup(name="Conduit candidate dolines", show=True)
    for rank, depression in enumerate(candidates, start=1):
        safe_id = escape(depression.id, quote=True)
        folium.Marker(
            location=(depression.centroid.lat, depression.centroid.lon),
            tooltip=f"Conduit candidate {rank} — {safe_id}",
            icon=folium.DivIcon(
                html=(
                    '<div style="transform:rotate(45deg);'
                    f"background:{map_palette.CONDUIT_CORRIDOR};color:white;"
                    "border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,.35);"
                    "font:700 11px/20px sans-serif;height:20px;width:20px;"
                    'text-align:center;"><span style="display:inline-block;'
                    f'transform:rotate(-45deg);">{rank}</span></div>'
                ),
                icon_size=(20, 20),
                icon_anchor=(10, 10),
            ),
        ).add_to(group)
    group.add_to(folium_map)


def _swatch_box(color: str, label: str) -> str:
    """A filled square swatch + label (for area/ramp layers)."""
    return (
        f'<div><span style="display:inline-block;width:12px;height:12px;'
        f'background:{color};border:1px solid #555;'
        f'margin-right:6px;vertical-align:middle;"></span>{label}</div>'
    )


def _swatch_line(color: str, label: str, *, dashed: bool = False, weight: int = 3) -> str:
    """A short line swatch + label (for line layers: contours, streams, faults)."""
    border = "dashed" if dashed else "solid"
    return (
        f'<div><span style="display:inline-block;width:20px;'
        f'border-top:{weight}px {border} {color};'
        f'margin-right:6px;vertical-align:middle;"></span>{label}</div>'
    )


def _add_map_legend(folium_map: folium.Map, *, conduit_present: bool = False) -> None:
    """Add a fixed HTML legend covering every styled map layer.

    Colours are pulled from :mod:`karstlab.presentation.map_palette` so the
    legend can never drift from what the layers actually render.
    """
    ramp = "".join(
        _swatch_box(_FAULT_DISTANCE_COLORS[key], label) for key, label in _FAULT_DISTANCE_LABELS
    )
    conduit_row = (
        _swatch_line(map_palette.CONDUIT_CORRIDOR, "predicted conduit corridor", weight=4)
        if conduit_present
        else ""
    )
    legend = (
        '<div style="position:fixed;bottom:22px;left:12px;z-index:9999;'
        'background:rgba(255,255,255,0.93);padding:8px 10px;border:1px solid #888;'
        'border-radius:6px;font:12px/1.45 sans-serif;color:#222;'
        'box-shadow:0 1px 4px rgba(0,0,0,.3);">'
        "<b>Doline → nearest fault</b>"
        f"{ramp}"
        '<div style="margin-top:6px;border-top:1px solid #ccc;padding-top:5px;">'
        "<b>Layers</b></div>"
        f"{_swatch_line(map_palette.CONTOURS, 'contour (elevation)', weight=2)}"
        f"{_swatch_line(map_palette.STREAMS, 'stream', weight=3)}"
        f"{_swatch_line(map_palette.FAULTS, 'fault observed', weight=3)}"
        f"{_swatch_line(map_palette.FAULTS, 'fault supposed', dashed=True, weight=3)}"
        f"{_swatch_line(map_palette.SURVEY_REPRESENTATIVE, 'imported survey / cave line')}"
        f"{conduit_row}"
        '<div style="margin-top:5px;">⬤ black bold outline = on a fault '
        "<b>parallel</b> to the cave line</div>"
        '<div style="margin-top:5px;color:#555;">Numbered pins = Top-25 by depth '
        "(rank), <i>not</i> the doline id. Imported-file colours vary per file.</div>"
        "</div>"
    )
    # get_root() is typed as Element but the map root is a Figure at runtime,
    # which exposes the .html container the legend is appended to.
    folium_map.get_root().html.add_child(folium.Element(legend))  # type: ignore[attr-defined]


def _fault_line_style(feature: dict[str, Any]) -> dict[str, Any]:
    fault_class = feature.get("properties", {}).get("fault_class")
    # Observed faults solid; supposed/other dashed.
    dash = None if fault_class == "observed" else "6,5"
    return {"color": map_palette.FAULTS, "weight": 2, "opacity": 0.9, "dashArray": dash}


def _depression_plain_style(_feature: dict[str, Any]) -> dict[str, Any]:
    return {
        "color": map_palette.DEPRESSION_PLAIN_LINE,
        "fillColor": map_palette.DEPRESSION_PLAIN_FILL,
        "fillOpacity": 0.18,
        "weight": 1,
    }


def _depression_fault_style(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties", {})
    dist_class = props.get("dist_class", "none")
    color = _FAULT_DISTANCE_COLORS.get(dist_class, _FAULT_DISTANCE_COLORS[">250m"])
    # White outline for contrast against the fill; a doline on a fault parallel to
    # the cave line (likely conduit line) gets a black bold outline to stand out.
    parallel = props.get("orientation") == "parallel"
    return {
        "color": map_palette.PARALLEL_OUTLINE if parallel else map_palette.DEFAULT_OUTLINE,
        "fillColor": color,
        "fillOpacity": 0.85,
        "weight": 2.5 if parallel else 1,
    }


def _add_numbered_markers(folium_map: folium.Map, depressions: Sequence[DepressionResult]) -> None:
    marker_group = folium.FeatureGroup(name="Top 25 depression markers", show=True)
    for index, depression in enumerate(depressions, start=1):
        number = depression.rank if depression.rank is not None else index
        safe_id = escape(depression.id, quote=True)
        folium.Marker(
            location=(depression.centroid.lat, depression.centroid.lon),
            tooltip=f"Rank {number} — {safe_id}",
            popup=folium.Popup(_popup_html(depression, number), max_width=260),
            icon=folium.DivIcon(
                html=(
                    '<div class="karstlab-rank-marker" '
                    f'style="background:{map_palette.TOP25_MARKER_BG};color:white;'
                    'border:2px solid white;'
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


# Defence-in-depth: a vector overlay with this many features would inflate the
# inline GeoJSON to hundreds of MB and prevent the map from loading. Such a
# layer is dropped rather than embedded, keeping the map renderable regardless
# of input scale. (Streams are rendered as a raster overlay specifically to stay
# well under this.)
_MAX_OVERLAY_FEATURES = 50_000


def _add_overlay_layers(
    folium_map: folium.Map, group_name: str, layers: Sequence[MapLayerSpec]
) -> None:
    for layer in layers:
        data = _geojson_data(layer.data)
        if _feature_count(data) > _MAX_OVERLAY_FEATURES:
            continue
        folium.GeoJson(
            data,
            name=f"{group_name}: {layer.name}",
            show=layer.show,
            style_function=_style_function(layer.style),
        ).add_to(folium_map)


def _feature_count(data: Mapping[str, Any]) -> int:
    features = data.get("features") if isinstance(data, Mapping) else None
    return len(features) if isinstance(features, list) else 0


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
        "lat": round(depression.centroid.lat, 6),
        "lon": round(depression.centroid.lon, 6),
        "fault_m": depression.distance_to_fault_m,
    }


def _popup_html(depression: DepressionResult, number: int) -> str:
    safe_id = escape(depression.id, quote=True)
    lat = depression.centroid.lat
    lon = depression.centroid.lon
    # Centroid coordinate, shown as copyable text plus a link to open the exact
    # point in an external map for field exploration.
    coord = f"{lat:.6f}, {lon:.6f}"
    fault_line = (
        f"Nearest fault: {depression.distance_to_fault_m:.0f} m<br>"
        if depression.distance_to_fault_m is not None
        else ""
    )
    return (
        f"<strong>#{number} {safe_id}</strong><br>"
        f"Depth: {depression.max_depth_m:.2f} m<br>"
        f"Area: {depression.area_m2:.1f} m2<br>"
        f"{fault_line}"
        f"Centre: <code>{coord}</code><br>"
        f'<a href="https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}'
        f'#map=18/{lat:.6f}/{lon:.6f}" target="_blank" rel="noopener">Open location</a>'
    )
