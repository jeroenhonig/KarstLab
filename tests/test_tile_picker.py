from __future__ import annotations

from pathlib import Path

from karstlab.presentation.tile_picker_dialog import (
    _bounds_l93,
    _build_geojson,
    _head_assets,
    _is_dem_tile_file,
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


def test_render_html_exposes_select_all_and_draw_mode_hooks() -> None:
    html = _render_html(_build_geojson({"0948_6698": Path("/x/a")}), 47.2, 6.3, 12)
    # Select-all + rectangle-draw JS entry points the dialog drives via runJavaScript.
    assert "window.applySelectAll" in html
    assert "window.applySelectKeys" in html
    assert "window.setDrawMode" in html
    # Draw mode must toggle Leaflet dragging so pan/zoom is preserved when off.
    assert "map.dragging.disable()" in html
    assert "map.dragging.enable()" in html
    assert "karstlab://tileselect" in html


def test_l93_inverse_places_doubs_tile_in_france() -> None:
    xmin, ymin, xmax, ymax = _bounds_l93("0935_6705")
    lat, lon = _l93_to_wgs84((xmin + xmax) / 2, (ymin + ymax) / 2)
    assert 47.0 < lat < 48.0
    assert 5.5 < lon < 7.5


def test_is_dem_tile_file_accepts_raster_extensions(tmp_path: Path) -> None:
    for name in ("a.asc", "b.tif", "c.TIFF"):
        p = tmp_path / name
        p.write_bytes(b"\x00\x00\x00\x00")
        assert _is_dem_tile_file(p)


def test_is_dem_tile_file_accepts_extensionless_geotiff(tmp_path: Path) -> None:
    # IGN LHD tiles ship without an extension; identified by TIFF magic bytes.
    little = tmp_path / "LHD_FXX_0948_6698_MNT_O_0M50_LAMB93_IGN69"
    little.write_bytes(b"II*\x00rest")
    big = tmp_path / "BIG_ENDIAN_0949_6699"
    big.write_bytes(b"MM\x00*rest")
    assert _is_dem_tile_file(little)
    assert _is_dem_tile_file(big)


def test_is_dem_tile_file_rejects_other_files(tmp_path: Path) -> None:
    txt = tmp_path / "notes.txt"
    txt.write_bytes(b"hello")
    extensionless_non_tiff = tmp_path / "README"
    extensionless_non_tiff.write_bytes(b"# readme")
    assert not _is_dem_tile_file(txt)
    assert not _is_dem_tile_file(extensionless_non_tiff)
    assert not _is_dem_tile_file(tmp_path / "missing.tif")  # not a file
