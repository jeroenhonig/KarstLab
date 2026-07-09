from __future__ import annotations

import pytest

from karstlab.data.schemas import DepressionResult
from karstlab.presentation import map_palette
from karstlab.presentation.map_builder import (
    ImageLayerSpec,
    MapLayerSpec,
    TileLayerSpec,
    WmsLayerSpec,
    build_top_depressions_map,
    render_top_depressions_map_html,
)


def depression(
    depression_id: str,
    *,
    rank: int | None,
    lat: float,
    lon: float,
    max_depth_m: float = 4.2,
    area_m2: float = 120.0,
) -> DepressionResult:
    return DepressionResult.model_validate(
        {
            "id": depression_id,
            "rank": rank,
            "max_depth_m": max_depth_m,
            "area_m2": area_m2,
            "centroid": {"lat": lat, "lon": lon},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [lon - 0.01, lat - 0.01],
                        [lon + 0.01, lat - 0.01],
                        [lon + 0.01, lat + 0.01],
                        [lon - 0.01, lat + 0.01],
                        [lon - 0.01, lat - 0.01],
                    ]
                ],
            },
        }
    )


def feature_collection(name: str) -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": name},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[1.19, 44.09], [1.21, 44.11]],
                },
            }
        ],
    }


def point_feature_collection(name: str) -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": name},
                "geometry": {"type": "Point", "coordinates": [1.20, 44.10]},
            }
        ],
    }


def test_render_top_depressions_map_html_contains_ranked_markers_and_footprints() -> None:
    html = render_top_depressions_map_html(
        [
            depression("doline-alpha", rank=1, lat=44.10, lon=1.20),
            depression("doline-beta", rank=2, lat=44.12, lon=1.22),
        ]
    )

    assert "Top 25 depression footprints" in html
    assert "Top 25 depression markers" in html
    assert "doline-alpha" in html
    assert "doline-beta" in html
    assert "#1 doline-alpha" in html
    assert "#2 doline-beta" in html
    assert "karstlab-rank-marker" in html


def test_all_depressions_layer_lists_every_numbered_footprint() -> None:
    ranked = [depression("doline-0001", rank=1, lat=44.10, lon=1.20)]
    everything = [
        depression(f"doline-{i:04d}", rank=None, lat=44.10 + i * 0.001, lon=1.20)
        for i in range(1, 6)
    ]
    html = render_top_depressions_map_html(ranked, all_depressions=everything)
    assert "All depressions (5)" in html
    # Every depression footprint is present, not just the ranked one.
    assert "doline-0005" in html


def test_all_depressions_layer_dropped_when_over_feature_budget() -> None:
    from karstlab.presentation.map_builder import _MAX_OVERLAY_FEATURES

    ranked = [depression("doline-0001", rank=1, lat=44.10, lon=1.20)]
    huge = [
        depression(f"doline-{i:05d}", rank=None, lat=44.10, lon=1.20)
        for i in range(_MAX_OVERLAY_FEATURES + 1)
    ]
    html = render_top_depressions_map_html(ranked, all_depressions=huge)
    assert "All depressions (" not in html  # dropped to keep the map renderable


def test_map_exposes_depression_centroid_coordinates() -> None:
    html = render_top_depressions_map_html(
        [depression("doline-alpha", rank=1, lat=44.123456, lon=1.234567)],
        all_depressions=[depression("doline-alpha", rank=1, lat=44.123456, lon=1.234567)],
    )
    # Centroid is shown in the marker popup (copyable + external map link) and
    # carried as tooltip fields on the footprint layers.
    assert "44.123456, 1.234567" in html
    assert "openstreetmap.org/?mlat=44.123456" in html
    assert '"lat"' in html and '"lon"' in html


def test_oversized_vector_layer_is_dropped_to_keep_map_renderable() -> None:
    # A layer with too many features would inflate the inline GeoJSON to
    # hundreds of MB and blank the map; it is dropped instead of embedded.
    from karstlab.presentation.map_builder import _MAX_OVERLAY_FEATURES

    feature = {
        "type": "Feature",
        "properties": {"value": 1.0},
        "geometry": {"type": "Point", "coordinates": [1.2, 44.1]},
    }
    huge = {
        "type": "FeatureCollection",
        "features": [feature] * (_MAX_OVERLAY_FEATURES + 1),
    }
    html = render_top_depressions_map_html(
        [depression("doline-alpha", rank=1, lat=44.10, lon=1.20)],
        vector_layers=[MapLayerSpec(name="Massive layer", data=huge)],
    )
    assert "Vectors: Massive layer" not in html


def test_render_top_depressions_map_html_adds_optional_contour_and_vector_layers() -> None:
    html = render_top_depressions_map_html(
        [depression("doline-alpha", rank=1, lat=44.10, lon=1.20)],
        contour_layers=[
            MapLayerSpec(
                name="Synthetic contours",
                data=feature_collection("contour-200m"),
                style={"color": "#2563eb", "weight": 1},
            )
        ],
        vector_layers=[
            MapLayerSpec(
                name="Synthetic faults",
                data=feature_collection("fault-a"),
                style={"color": "#dc2626", "weight": 2},
            )
        ],
    )

    assert "Contours: Synthetic contours" in html
    assert "Vectors: Synthetic faults" in html
    assert "contour-200m" in html
    assert "fault-a" in html
    assert "#2563eb" in html
    assert "#dc2626" in html


def test_render_top_depressions_map_html_adds_phase5_optional_layers() -> None:
    html = render_top_depressions_map_html(
        [depression("doline-alpha", rank=1, lat=44.10, lon=1.20)],
        hillshade_layers=[
            ImageLayerSpec(
                name="Synthetic hillshade",
                image=(
                    "data:image/png;base64,"
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
                    "AAAADUlEQVR42mP8z8BQDwAFgwJ/lH9P4wAAAABJRU5ErkJggg=="
                ),
                bounds=[[44.09, 1.19], [44.11, 1.21]],
            )
        ],
        contour_layers=[
            MapLayerSpec(
                name="Phase 5 contours",
                data=feature_collection("contour-250m"),
            )
        ],
        stream_layers=[
            MapLayerSpec(
                name="Phase 5 streams",
                data=feature_collection("stream-a"),
                style={"color": "#0284c7", "weight": 2},
            )
        ],
        imported_marker_layers=[
            MapLayerSpec(
                name="Imported survey markers",
                data=point_feature_collection("marker-a"),
                style={"color": "#7c3aed"},
            )
        ],
    )

    assert "Hillshade: Synthetic hillshade" in html
    assert "Contours: Phase 5 contours" in html
    assert "Streams: Phase 5 streams" in html
    assert "Imported markers: Imported survey markers" in html
    assert "contour-250m" in html
    assert "stream-a" in html
    assert "marker-a" in html
    assert "Top 25 depression markers" in html
    assert "#1 doline-alpha" in html


def test_render_top_depressions_map_html_accepts_direct_imported_marker_geojson() -> None:
    html = render_top_depressions_map_html(
        [depression("doline-alpha", rank=1, lat=44.10, lon=1.20)],
        imported_markers=point_feature_collection("marker-a"),
    )

    assert "Imported markers: Imported markers" in html
    assert "marker-a" in html
    assert "Top 25 depression markers" in html


def test_render_top_depressions_map_html_uses_custom_tile_attribution() -> None:
    html = render_top_depressions_map_html(
        [depression("doline-alpha", rank=1, lat=44.10, lon=1.20)],
        tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        tile_attribution="© OpenStreetMap contributors",
    )

    assert "OpenStreetMap contributors" in html
    assert "KarstLab contributors" not in html


def test_build_top_depressions_map_limits_results_to_25() -> None:
    depressions = [
        depression(f"doline-{index:02d}", rank=index + 1, lat=44.0, lon=1.0) for index in range(30)
    ]

    html = build_top_depressions_map(depressions).get_root().render()

    assert "doline-24" in html
    assert "doline-25" not in html
    assert "doline-29" not in html


def test_build_top_depressions_map_rejects_invalid_limit() -> None:
    with pytest.raises(ValueError, match="max_results"):
        build_top_depressions_map([], max_results=0)


def test_build_top_depressions_map_rejects_empty_depressions() -> None:
    with pytest.raises(ValueError, match="depressions"):
        build_top_depressions_map([])


def test_render_top_depressions_map_html_escapes_marker_text() -> None:
    html = render_top_depressions_map_html(
        [depression('<script>alert("x")</script>', rank=1, lat=44.10, lon=1.20)]
    )

    assert "<script>alert" not in html
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in html


def test_extra_tile_layers_render_in_html() -> None:
    html = render_top_depressions_map_html(
        [depression("d-1", rank=1, lat=44.10, lon=1.20)],
        extra_tile_layers=[
            TileLayerSpec(
                name="IGN Plan",
                url="https://example.test/wmts/{z}/{x}/{y}.png",
                attribution="© IGN",
            )
        ],
    )
    assert "example.test/wmts" in html
    assert "IGN Plan" in html


def test_wms_layers_render_in_html() -> None:
    html = render_top_depressions_map_html(
        [depression("d-1", rank=1, lat=44.10, lon=1.20)],
        wms_layers=[
            WmsLayerSpec(
                name="BRGM Géologique 50k",
                url="https://example.test/geologie",
                layers="SCAN_H_GEOL50",
                attribution="© BRGM",
            )
        ],
    )
    assert "example.test/geologie" in html
    assert "SCAN_H_GEOL50" in html
    assert "BRGM" in html


def test_wms_layer_is_semi_transparent_by_default() -> None:
    # WMS overlays must never fully obscure the basemap/results when toggled on.
    html = render_top_depressions_map_html(
        [depression("d-1", rank=1, lat=44.10, lon=1.20)],
        wms_layers=[
            WmsLayerSpec(
                name="Geol",
                url="https://example.test/wms",
                layers="0",
                attribution="x",
                opacity=0.5,
            )
        ],
    )
    assert '"opacity": 0.5' in html


def test_tile_layers_are_basemaps_wms_are_overlays() -> None:
    folium_map = build_top_depressions_map(
        [depression("d-1", rank=1, lat=44.10, lon=1.20)],
        extra_tile_layers=[
            TileLayerSpec(name="Sat", url="https://example.test/s/{z}/{x}/{y}.jpg", attribution="x")
        ],
        wms_layers=[
            WmsLayerSpec(
                name="Karst", url="https://example.test/ows", layers="karst", attribution="x"
            )
        ],
    )
    html = folium_map.get_root().render()
    # Base tile layer registered without overlay flag; WMS registered as overlay.
    assert "example.test/s/" in html
    assert "example.test/ows" in html


def test_map_has_regional_min_zoom_floor() -> None:
    html = render_top_depressions_map_html(
        [depression("doline-alpha", rank=1, lat=44.10, lon=1.20)],
        tiles="https://tile.example/{z}/{x}/{y}.png",
        tile_attribution="x",
    )
    # A min-zoom floor prevents falling back to the repeated whole-world view.
    assert '"minZoom": 5' in html


def _fault_geojson() -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature",
             "properties": {"fault_class": "observed", "descr": "obs", "bearing_deg": 10.0},
             "geometry": {"type": "LineString", "coordinates": [[1.19, 44.09], [1.20, 44.11]]}},
            {"type": "Feature",
             "properties": {"fault_class": "supposed", "descr": "sup", "bearing_deg": 80.0},
             "geometry": {"type": "LineString", "coordinates": [[1.21, 44.09], [1.22, 44.10]]}},
        ],
    }


def test_fault_lines_layer_rendered_with_dash_for_supposed() -> None:
    html = render_top_depressions_map_html(
        [depression("doline-alpha", rank=1, lat=44.10, lon=1.20)],
        fault_geojson=_fault_geojson(),
    )
    assert "Faults (BDCharm50)" in html
    assert "dashArray" in html  # supposed faults dashed
    assert "observed" in html and "supposed" in html


def test_dolines_coloured_by_fault_distance_when_present() -> None:
    near = depression("doline-near", rank=1, lat=44.10, lon=1.20)
    far = depression("doline-far", rank=2, lat=44.12, lon=1.22)
    near = near.model_copy(update={
        "distance_to_fault_m": 12.0,
        "nearest_fault_type": "Faille observée",
        "fault_orientation": "parallel",
    })
    far = far.model_copy(update={"distance_to_fault_m": 400.0})
    html = render_top_depressions_map_html(
        [near], all_depressions=[near, far], fault_geojson=_fault_geojson()
    )
    assert "Dolines by fault distance" in html
    assert "#e60000" in html  # red class (<=50 m) present
    assert "Orientation vs cave" in html  # popup field
    assert "Doline &rarr; nearest fault" in html or "Doline" in html  # legend present
    # The legend covers every styled layer, using the central palette colours.
    assert map_palette.CONTOURS in html  # contour swatch
    assert map_palette.STREAMS in html  # stream swatch
    assert map_palette.FAULTS in html  # fault swatch
    assert "contour (elevation)" in html
    assert "stream" in html
    assert "imported survey / cave line" in html


def _conduit_geojson() -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[1.20, 44.10], [1.21, 44.11], [1.22, 44.12]],
                },
                "properties": {"relative_likelihood": 0.5},
            }
        ],
    }


def test_conduit_corridor_and_candidates_render() -> None:
    candidate = depression("doline-cand", rank=1, lat=44.115, lon=1.215)
    html = render_top_depressions_map_html(
        [candidate],
        all_depressions=[candidate],
        conduit_geojson=_conduit_geojson(),
        conduit_candidates=[candidate],
    )
    assert "Predicted conduit corridor" in html
    assert "Conduit candidate dolines" in html
    assert map_palette.CONDUIT_CORRIDOR in html  # corridor + candidate colour
    assert "relative_likelihood" in html  # isoline tooltip field
    # Legend appears (conduit present) and carries the conduit row.
    assert "predicted conduit corridor" in html


def test_no_conduit_layers_when_absent() -> None:
    only = depression("doline-x", rank=1, lat=44.10, lon=1.20)
    html = render_top_depressions_map_html([only], all_depressions=[only])
    assert "Predicted conduit corridor" not in html
    assert "Conduit candidate dolines" not in html
