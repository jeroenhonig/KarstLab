from __future__ import annotations

from pathlib import Path

from karstlab.presentation.tile_picker_dialog import (
    _bounds_l93,
    _build_geojson,
    _l93_to_wgs84,
    _leaflet_asset_urls,
    _render_html,
)

_LEAFLET_DIR = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "karstlab"
    / "resources"
    / "leaflet"
)


def test_leaflet_assets_are_vendored() -> None:
    assert (_LEAFLET_DIR / "leaflet.js").is_file()
    assert (_LEAFLET_DIR / "leaflet.css").is_file()


def test_render_html_references_local_leaflet_not_cdn() -> None:
    css_url, js_url = _leaflet_asset_urls()
    assert css_url.startswith("file://")
    assert js_url.startswith("file://")

    html = _render_html(_build_geojson({"0900_6700": Path("/x/a.asc")}), 47.2, 6.3, 10)
    # Leaflet library served locally (offline-safe); only the OSM basemap stays remote.
    assert "unpkg.com" not in html
    assert "file://" in html


def test_l93_inverse_places_doubs_tile_in_france() -> None:
    xmin, ymin, xmax, ymax = _bounds_l93("0935_6705")
    lat, lon = _l93_to_wgs84((xmin + xmax) / 2, (ymin + ymax) / 2)
    assert 47.0 < lat < 48.0
    assert 5.5 < lon < 7.5
