from __future__ import annotations

from pathlib import Path

from karstlab.presentation.tile_picker_dialog import (
    _bounds_l93,
    _build_geojson,
    _head_assets,
    _l93_to_wgs84,
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


def test_head_assets_inline_vendored_leaflet_not_cdn() -> None:
    head = _head_assets()
    # Leaflet inlined (offline-safe) — no external CDN script/link tags.
    assert "unpkg.com" not in head
    assert "leaflet" in head.lower()
    assert "<script>" in head


def test_render_html_inlines_leaflet_and_stays_under_sethtml_limit() -> None:
    geojson = _build_geojson(
        {f"{900 + i % 40:04d}_{6700 + i // 40:04d}": Path(f"/x/{i}.asc") for i in range(4240)}
    )
    html = _render_html(geojson, 47.2, 6.3, 10)
    assert "unpkg.com" not in html
    # Inlined Leaflet + 4240 footprints must fit the QWebEngineView setHtml budget.
    assert len(html.encode("utf-8")) < 1_800_000


def test_l93_inverse_places_doubs_tile_in_france() -> None:
    xmin, ymin, xmax, ymax = _bounds_l93("0935_6705")
    lat, lon = _l93_to_wgs84((xmin + xmax) / 2, (ymin + ymax) / 2)
    assert 47.0 < lat < 48.0
    assert 5.5 < lon < 7.5
