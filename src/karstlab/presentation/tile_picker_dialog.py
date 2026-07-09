"""Interactive map-based tile picker for RGE ALTI ASC tile selection."""

from __future__ import annotations

import json
import math
import re
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# ── Lambert93 (EPSG:2154) → WGS84 inverse projection ────────────────────────
_a = 6378137.0
_e2 = 0.00669437999014
_e = math.sqrt(_e2)
_X0 = 700000.0
_Y0 = 6600000.0
_lam0 = math.radians(3.0)


def _precompute() -> tuple[float, float, float]:
    phi1, phi2, phi0 = math.radians(44.0), math.radians(49.0), math.radians(46.5)

    def _m(ph: float) -> float:
        return math.cos(ph) / math.sqrt(1.0 - _e2 * math.sin(ph) ** 2)

    def _t(ph: float) -> float:
        s = _e * math.sin(ph)
        return float(
            math.tan(math.pi / 4.0 - ph / 2.0)
            / ((1.0 - s) / (1.0 + s)) ** (_e / 2.0)
        )

    m1, m2 = _m(phi1), _m(phi2)
    t0, t1, t2 = _t(phi0), _t(phi1), _t(phi2)
    n = (math.log(m1) - math.log(m2)) / (math.log(t1) - math.log(t2))
    big_f = m1 / (n * t1 ** n)
    rho0 = _a * big_f * t0 ** n
    return n, big_f, rho0


_n, _F, _rho0 = _precompute()


def _l93_to_wgs84(x: float, y: float) -> tuple[float, float]:
    dx = x - _X0
    drho = _rho0 - (y - _Y0)
    rho = math.sqrt(dx * dx + drho * drho)
    theta = math.atan2(dx, drho)
    lam = theta / _n + _lam0
    tv = (rho / (_a * _F)) ** (1.0 / _n)
    phi = math.pi / 2.0 - 2.0 * math.atan(tv)
    for _ in range(10):
        s = _e * math.sin(phi)
        phi_new = math.pi / 2.0 - 2.0 * math.atan(tv * ((1.0 - s) / (1.0 + s)) ** (_e / 2.0))
        if abs(phi_new - phi) < 1e-12:
            break
        phi = phi_new
    return math.degrees(phi), math.degrees(lam)


# ── Tile geometry helpers ────────────────────────────────────────────────────
_TILE_RE = re.compile(r"_(\d{4})_(\d{4})_")


def _key_from_path(path: Path) -> str | None:
    m = _TILE_RE.search(path.stem)
    return f"{m.group(1)}_{m.group(2)}" if m else None


# Tile rasters arrive as ASC grids or GeoTIFFs; IGN LHD downloads are GeoTIFFs
# shipped without a file extension, so extensionless files are accepted when
# their leading bytes are the TIFF magic number.
_RASTER_SUFFIXES = {".asc", ".tif", ".tiff"}
_TIFF_MAGIC = (b"II*\x00", b"MM\x00*")


def _is_dem_tile_file(path: Path) -> bool:
    if not path.is_file():
        return False
    suffix = path.suffix.lower()
    if suffix in _RASTER_SUFFIXES:
        return True
    if suffix:
        return False
    try:
        with path.open("rb") as handle:
            return handle.read(4) in _TIFF_MAGIC
    except OSError:
        return False


def _bounds_l93(key: str) -> tuple[float, float, float, float]:
    """SW/NE corners in Lambert93 for tile key XXXX_YYYY."""
    x_km = int(key[:4])
    y_km = int(key[5:])
    # Based on RGE ALTI header convention: xllcorner = X*1000 - 0.5, yllcorner = (Y-1)*1000 + 0.5
    xmin = x_km * 1000.0 - 0.5
    ymin = (y_km - 1) * 1000.0 + 0.5
    return xmin, ymin, xmin + 1000.0, ymin + 1000.0


def _polygon_wgs84(key: str) -> list[list[float]]:
    xmin, ymin, xmax, ymax = _bounds_l93(key)
    ring: list[list[float]] = []
    for cx, cy in [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]:
        lat, lon = _l93_to_wgs84(cx, cy)
        ring.append([round(lon, 6), round(lat, 6)])
    ring.append(ring[0])
    return ring


# ── GeoJSON builder ──────────────────────────────────────────────────────────
def _build_geojson(tiles: dict[str, Path]) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for key in sorted(tiles):
        try:
            ring = _polygon_wgs84(key)
        except Exception:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {"k": key},
            }
        )
    return {"type": "FeatureCollection", "features": features}


# ── Leaflet HTML ─────────────────────────────────────────────────────────────
_MAP_HTML_TMPL = """\
<!DOCTYPE html><html><head><meta charset="utf-8"/>
HEAD_ASSETS_PLACEHOLDER
<style>
html,body{margin:0;padding:0;height:100%}
#map{width:100%;height:100vh;background:#e5e7eb}
</style></head><body><div id="map"></div><script>
var td=GEOJSON_PLACEHOLDER;
var sel={};var lyr={};
var map=L.map('map').setView([LAT_PLACEHOLDER,LON_PLACEHOLDER],ZOOM_PLACEHOLDER);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  {attribution:'&copy; OpenStreetMap contributors',maxZoom:19}).addTo(map);
function sty(k){
  return sel[k]
    ?{color:'#0ea5e9',weight:2,fillColor:'#0ea5e9',fillOpacity:0.45}
    :{color:'#9ca3af',weight:1,fillColor:'#6b7280',fillOpacity:0.07};
}
var drawMode=false;var drawStart=null;var rectLayer=null;
L.geoJSON(td,{
  style:function(f){return sty(f.properties.k);},
  onEachFeature:function(f,l){
    var k=f.properties.k;lyr[k]=l;
    l.bindTooltip(k,{sticky:true,direction:'top'});
    l.on('click',function(e){
      if(drawMode){return;}
      L.DomEvent.stopPropagation(e);
      window.location.href='karstlab://tiletoggle?id='+encodeURIComponent(k);
    });
  }
}).addTo(map);
window.applyToggle=function(k){
  if(sel[k]){delete sel[k];}else{sel[k]=true;}
  if(lyr[k])lyr[k].setStyle(sty(k));
};
window.applyClearAll=function(){
  sel={};
  for(var k in lyr)lyr[k].setStyle(sty(k));
};
window.applySelectAll=function(){
  for(var k in lyr){sel[k]=true;lyr[k].setStyle(sty(k));}
};
window.applySelectKeys=function(keys){
  for(var i=0;i<keys.length;i++){var k=keys[i];if(lyr[k]){sel[k]=true;lyr[k].setStyle(sty(k));}}
};
// Draw-rectangle selection. While active the map stops panning so a drag draws
// a selection box; releasing selects every tile the box intersects. Toggling it
// off restores normal pan/zoom.
window.setDrawMode=function(on){
  drawMode=on;
  if(on){map.dragging.disable();map.getContainer().style.cursor='crosshair';}
  else{
    map.dragging.enable();map.getContainer().style.cursor='';
    drawStart=null;
    if(rectLayer){map.removeLayer(rectLayer);rectLayer=null;}
  }
};
map.on('mousedown',function(e){
  if(!drawMode){return;}
  drawStart=e.latlng;
  if(rectLayer){map.removeLayer(rectLayer);}
  rectLayer=L.rectangle([drawStart,drawStart],
    {color:'#f59e0b',weight:2,fillColor:'#f59e0b',fillOpacity:0.1}).addTo(map);
});
map.on('mousemove',function(e){
  if(!drawMode||!drawStart||!rectLayer){return;}
  rectLayer.setBounds(L.latLngBounds(drawStart,e.latlng));
});
map.on('mouseup',function(e){
  if(!drawMode||!drawStart){return;}
  var box=L.latLngBounds(drawStart,e.latlng);drawStart=null;
  var hit=[];
  for(var k in lyr){
    if(box.intersects(lyr[k].getBounds())){sel[k]=true;lyr[k].setStyle(sty(k));hit.push(k);}
  }
  if(rectLayer){map.removeLayer(rectLayer);rectLayer=null;}
  if(hit.length){window.location.href='karstlab://tileselect?ids='+encodeURIComponent(hit.join(','));}
});
</script></body></html>"""


_LEAFLET_DIR = Path(__file__).resolve().parent.parent / "resources" / "leaflet"


def _head_assets() -> str:
    """Inline the vendored Leaflet css+js into the page <head>.

    Inlining (rather than file:// links) is what makes the picker robust: the
    HTML is loaded via ``setHtml`` with an https base URL so the OSM basemap
    tiles load, and an https-origin page cannot pull file:// subresources — so
    the Leaflet library must be embedded directly. Falls back to the unpkg CDN
    if the vendored copy is missing.
    """
    css = _LEAFLET_DIR / "leaflet.css"
    js = _LEAFLET_DIR / "leaflet.js"
    if css.is_file() and js.is_file():
        return (
            f"<style>{css.read_text(encoding='utf-8')}</style>"
            f"<script>{js.read_text(encoding='utf-8')}</script>"
        )
    return (
        '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>'
        '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>'
    )


def _render_html(geojson: dict[str, Any], center_lat: float, center_lon: float, zoom: int) -> str:
    return (
        _MAP_HTML_TMPL.replace("HEAD_ASSETS_PLACEHOLDER", _head_assets())
        .replace("GEOJSON_PLACEHOLDER", json.dumps(geojson))
        .replace("LAT_PLACEHOLDER", str(round(center_lat, 5)))
        .replace("LON_PLACEHOLDER", str(round(center_lon, 5)))
        .replace("ZOOM_PLACEHOLDER", str(zoom))
    )


# ── Dialog ───────────────────────────────────────────────────────────────────
class TilePickerDialog(QDialog):
    """Map-based dialog for selecting RGE ALTI ASC tiles from a directory."""

    def __init__(self, initial_dir: Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Select DEM tiles"))
        self.resize(1000, 700)

        self._tiles: dict[str, Path] = {}
        self._selected: set[str] = set()
        self._html_tmp: Path | None = None
        self._web_view: QWidget | None = None
        self._page: object | None = None

        # ── Directory row
        self._dir_edit = QLineEdit()
        self._dir_edit.setReadOnly(True)
        self._dir_edit.setPlaceholderText(self.tr("No directory selected"))
        browse_btn = QPushButton(self.tr("Browse…"))
        browse_btn.clicked.connect(self._browse_dir)

        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel(self.tr("Tile directory:")))
        dir_row.addWidget(self._dir_edit, 1)
        dir_row.addWidget(browse_btn)

        # ── Action buttons
        self._draw_btn = QPushButton(self.tr("Draw area"))
        self._draw_btn.setCheckable(True)
        self._draw_btn.setToolTip(
            self.tr("Drag a rectangle on the map to select the tiles it covers")
        )
        self._draw_btn.toggled.connect(self._set_draw_mode)
        self._draw_btn.setEnabled(False)

        self._select_all_btn = QPushButton(self.tr("Select all"))
        self._select_all_btn.clicked.connect(self._select_all)
        self._select_all_btn.setEnabled(False)

        self._clear_btn = QPushButton(self.tr("Clear selection"))
        self._clear_btn.clicked.connect(self._clear_all)
        self._clear_btn.setEnabled(False)
        self._count_label = QLabel(self.tr("No tiles loaded"))

        action_row = QHBoxLayout()
        action_row.addWidget(self._count_label, 1)
        action_row.addWidget(self._draw_btn)
        action_row.addWidget(self._select_all_btn)
        action_row.addWidget(self._clear_btn)

        # ── Map area
        self._map_placeholder = QLabel(self.tr("Browse to a tile directory to load the map."))
        self._map_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        map_widget = self._create_web_view()

        # ── OK/Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setEnabled(False)

        # ── Layout
        layout = QVBoxLayout(self)
        layout.addLayout(dir_row)
        layout.addLayout(action_row)
        layout.addWidget(map_widget, 1)
        layout.addWidget(buttons)

        if initial_dir is not None and initial_dir.is_dir():
            self._load_directory(initial_dir)

    # ── Web view setup ────────────────────────────────────────────────────────
    def _create_web_view(self) -> QWidget:
        try:
            from PySide6.QtCore import QUrlQuery as _UQ
            from PySide6.QtWebEngineCore import QWebEnginePage
            from PySide6.QtWebEngineWidgets import QWebEngineView

            dialog_ref = self

            class _Page(QWebEnginePage):
                def acceptNavigationRequest(
                    self_page,
                    url: QUrl | str,
                    nav_type: QWebEnginePage.NavigationType,
                    is_main_frame: bool,
                ) -> bool:
                    if (
                        isinstance(url, QUrl)
                        and url.scheme() == "karstlab"
                        and url.host() == "tiletoggle"
                    ):
                        key = _UQ(url.query()).queryItemValue("id")
                        if key:
                            QTimer.singleShot(0, lambda k=key: dialog_ref._toggle(k))
                        return False
                    if (
                        isinstance(url, QUrl)
                        and url.scheme() == "karstlab"
                        and url.host() == "tileselect"
                    ):
                        ids = _UQ(url.query()).queryItemValue("ids")
                        if ids:
                            keys = [k for k in ids.split(",") if k]
                            QTimer.singleShot(0, lambda ks=keys: dialog_ref._add_selection(ks))
                        return False
                    result: bool = super().acceptNavigationRequest(url, nav_type, is_main_frame)
                    return result

            self._web_view = QWebEngineView()
            self._page = _Page(self._web_view)
            self._web_view.setPage(self._page)
            return self._web_view

        except ImportError:
            return QLabel(self.tr("QWebEngineView not available."))

    # ── Directory loading ─────────────────────────────────────────────────────
    def _browse_dir(self) -> None:
        current = self._dir_edit.text() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, self.tr("Select tile directory"), current)
        if path:
            self._load_directory(Path(path))

    def _load_directory(self, directory: Path) -> None:
        self._dir_edit.setText(str(directory))
        tiles: dict[str, Path] = {}
        for f in sorted(directory.rglob("*")):
            key = _key_from_path(f)
            if key and _is_dem_tile_file(f):
                tiles[key] = f

        self._tiles = tiles
        self._selected.clear()

        if not tiles:
            self._count_label.setText(self.tr("No tiles found in directory."))
            self._ok_btn.setEnabled(False)
            for btn in (self._clear_btn, self._select_all_btn, self._draw_btn):
                btn.setEnabled(False)
            return

        self._count_label.setText(self.tr("{0} tiles found — 0 selected").format(len(tiles)))
        for btn in (self._clear_btn, self._select_all_btn, self._draw_btn):
            btn.setEnabled(True)
        # Fresh map → draw mode starts off (button unchecked, signal silent).
        self._draw_btn.blockSignals(True)
        self._draw_btn.setChecked(False)
        self._draw_btn.blockSignals(False)
        self._load_map()

    def _load_map(self) -> None:
        if self._web_view is None:
            return

        geojson = _build_geojson(self._tiles)

        # Compute map center from tile centroids
        lats, lons = [], []
        for key in self._tiles:
            try:
                xmin, ymin, xmax, ymax = _bounds_l93(key)
                lat, lon = _l93_to_wgs84((xmin + xmax) / 2, (ymin + ymax) / 2)
                lats.append(lat)
                lons.append(lon)
            except Exception:
                pass
        center_lat = sum(lats) / len(lats) if lats else 47.0
        center_lon = sum(lons) / len(lons) if lons else 3.0
        zoom = 10 if len(self._tiles) > 50 else 12

        html = _render_html(geojson, center_lat, center_lon, zoom)

        web_view = self._web_view
        if web_view is None:
            return
        # Load with an https base URL so the remote OSM basemap tiles are allowed
        # (a file:// origin blocks remote sub-resources). Leaflet itself is inlined
        # in the HTML, so it still renders offline; only the basemap needs network.
        # setHtml caps content at ~2 MB; fall back to a temp file for very large
        # tile sets (footprints still render, basemap stays grey).
        if len(html.encode("utf-8")) < 1_800_000 and hasattr(web_view, "setHtml"):
            web_view.setHtml(html, QUrl("https://karstlab.local/"))
        elif hasattr(web_view, "setUrl"):
            if self._html_tmp is not None:
                with suppress(Exception):
                    self._html_tmp.unlink(missing_ok=True)
            with tempfile.NamedTemporaryFile(
                suffix=".html", delete=False, mode="w", encoding="utf-8"
            ) as tmp:
                tmp.write(html)
                self._html_tmp = Path(tmp.name)
            web_view.setUrl(QUrl.fromLocalFile(str(self._html_tmp)))

    # ── Selection management ──────────────────────────────────────────────────
    def _toggle(self, key: str) -> None:
        if key not in self._tiles:
            return
        if key in self._selected:
            self._selected.discard(key)
        else:
            self._selected.add(key)
        self._update_count()
        if self._web_view is not None:
            js = f"window.applyToggle({json.dumps(key)});"
            page = self._web_view.page() if hasattr(self._web_view, "page") else None
            if page is not None:
                page.runJavaScript(js)

    def _clear_all(self) -> None:
        self._selected.clear()
        self._update_count()
        self._run_js("window.applyClearAll();")

    def _select_all(self) -> None:
        self._selected = set(self._tiles)
        self._update_count()
        self._run_js("window.applySelectAll();")

    def _add_selection(self, keys: list[str]) -> None:
        """Add map-drawn tile keys to the selection (rectangle-draw result)."""
        added = {k for k in keys if k in self._tiles}
        if not added:
            return
        self._selected |= added
        self._update_count()
        self._run_js(f"window.applySelectKeys({json.dumps(sorted(added))});")

    def _set_draw_mode(self, enabled: bool) -> None:
        """Toggle rectangle-draw selection; map panning is disabled while active."""
        self._run_js(f"window.setDrawMode({json.dumps(bool(enabled))});")

    def _run_js(self, script: str) -> None:
        if self._web_view is None:
            return
        page = self._web_view.page() if hasattr(self._web_view, "page") else None
        if page is not None:
            page.runJavaScript(script)

    def _update_count(self) -> None:
        n_total = len(self._tiles)
        n_sel = len(self._selected)
        self._count_label.setText(
            self.tr("{0} tiles found — {1} selected").format(n_total, n_sel)
        )
        self._ok_btn.setEnabled(n_sel > 0)

    # ── Result ────────────────────────────────────────────────────────────────
    def selected_paths(self) -> list[Path]:
        """Return sorted list of selected ASC file paths."""
        return sorted(self._tiles[k] for k in self._selected if k in self._tiles)

    def done(self, result: int) -> None:
        # Clean up temp file on close
        if self._html_tmp is not None:
            with suppress(Exception):
                self._html_tmp.unlink(missing_ok=True)
            self._html_tmp = None
        super().done(result)


__all__ = ["TilePickerDialog"]
