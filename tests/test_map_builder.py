from __future__ import annotations

import pytest

from karstlab.data.schemas import DepressionResult
from karstlab.presentation.map_builder import (
    ImageLayerSpec,
    MapLayerSpec,
    build_top_depressions_map,
    render_top_depressions_map_html,
)


def depression(
    depression_id: str,
    *,
    rank: int,
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
