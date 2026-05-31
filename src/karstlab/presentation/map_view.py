"""Folium/Leaflet map container widget for KarstLab."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

_CLICK_HANDLER_JS = """
(function() {
    if (window._karstlab_click_active) return;
    window._karstlab_click_active = true;
    window._kl_marker_handler = function(e) {
        window.location.href = 'karstlab://addmarker?lat='
            + e.latlng.lat.toFixed(6) + '&lon='
            + e.latlng.lng.toFixed(6);
    };
    for (var k in window) {
        try {
            var o = window[k];
            if (o && typeof o === 'object' && o._leaflet_id !== undefined
                    && typeof o.on === 'function') {
                window._kl_marker_map = o;
                o.on('click', window._kl_marker_handler);
                break;
            }
        } catch (_) {}
    }
})();
"""

_CLEAR_CLICK_JS = """
(function() {
    var m = window._kl_marker_map;
    if (m && window._kl_marker_handler) {
        // Remove only the marker-placement handler so the distance/profile
        // tools keep their own click handlers intact.
        m.off('click', window._kl_marker_handler);
    }
    window._karstlab_click_active = false;
    window._kl_marker_handler = null;
})();
"""

_DISTANCE_HANDLER_JS = """
(function() {
    if (window._kl_dist_active) return;
    window._kl_dist_active = true;
    window._kl_dist_p1 = null;
    window._kl_dist_layers = [];
    for (var k in window) {
        try {
            var m = window[k];
            if (m && typeof m === 'object' && m._leaflet_id !== undefined
                    && typeof m.on === 'function') {
                window._kl_dist_map = m;
                window._kl_dist_handler = function(e) {
                    if (!window._kl_dist_p1) {
                        window._kl_dist_p1 = e.latlng;
                        window._kl_dist_marker = L.circleMarker(
                            e.latlng, {radius: 5, color: '#f59e0b'}).addTo(m);
                        window._kl_dist_layers.push(window._kl_dist_marker);
                    } else {
                        var d = m.distance(window._kl_dist_p1, e.latlng);
                        var line = L.polyline(
                            [window._kl_dist_p1, e.latlng],
                            {color: '#f59e0b', dashArray: '6'}).addTo(m);
                        window._kl_dist_layers.push(line);
                        L.popup().setLatLng(e.latlng)
                            .setContent('<b>' + (d >= 1000
                                ? (d / 1000).toFixed(2) + ' km'
                                : Math.round(d) + ' m') + '</b>')
                            .openOn(m);
                        window._kl_dist_p1 = null;
                        if (window._kl_dist_marker) {
                            window._kl_dist_marker.remove();
                            window._kl_dist_marker = null;
                        }
                    }
                };
                m.on('click', window._kl_dist_handler);
                break;
            }
        } catch (_) {}
    }
})();
"""

_CLEAR_DISTANCE_JS = """
(function() {
    var m = window._kl_dist_map;
    if (m && window._kl_dist_handler) {
        m.off('click', window._kl_dist_handler);
    }
    if (window._kl_dist_layers) {
        window._kl_dist_layers.forEach(function(layer) {
            try { layer.remove(); } catch (_) {}
        });
    }
    if (window._kl_dist_marker) {
        try { window._kl_dist_marker.remove(); } catch (_) {}
    }
    window._kl_dist_active = false;
    window._kl_dist_p1 = null;
    window._kl_dist_layers = [];
    window._kl_dist_marker = null;
    window._kl_dist_handler = null;
})();
"""


_INJECT_POI_JS = """
(function() {
    var geojson = JSON.parse(__DATA__);
    var layerName = __LAYER__;
    var color = __COLOR__;
    for (var k in window) {
        try {
            var m = window[k];
            if (m && typeof m === 'object' && m._leaflet_id !== undefined
                    && typeof m.addLayer === 'function') {
                L.geoJSON(geojson, {
                    pointToLayer: function(f, ll) {
                        return L.circleMarker(ll, {
                            radius: 6, color: color,
                            fillColor: color, fillOpacity: 0.85, weight: 1
                        });
                    },
                    onEachFeature: function(f, l) {
                        var p = f.properties || {};
                        // Build DOM nodes with textContent so external BRGM
                        // name/description cannot inject HTML into the page.
                        var tip = document.createElement('span');
                        tip.textContent = p.name || 'Cave';
                        l.bindTooltip(tip);
                        var box = document.createElement('div');
                        var title = document.createElement('b');
                        title.textContent = p.name || '';
                        box.appendChild(title);
                        if (p.description) {
                            box.appendChild(document.createElement('br'));
                            box.appendChild(document.createTextNode(p.description));
                        }
                        l.bindPopup(box);
                    }
                }).addTo(m);
                break;
            }
        } catch (_) {}
    }
})();
"""


_PROFILE_HANDLER_JS = """
(function() {
    if (window._kl_prof_active) return;
    window._kl_prof_active = true;
    window._kl_prof_p1 = null;
    window._kl_prof_layers = [];
    for (var k in window) {
        try {
            var m = window[k];
            if (m && typeof m === 'object' && m._leaflet_id !== undefined
                    && typeof m.on === 'function') {
                window._kl_prof_map = m;
                window._kl_prof_handler = function(e) {
                    var dot = L.circleMarker(e.latlng,
                        {radius: 5, color: '#f59e0b'}).addTo(m);
                    window._kl_prof_layers.push(dot);
                    window.location.href = 'karstlab://profile?lat='
                        + e.latlng.lat.toFixed(6) + '&lon='
                        + e.latlng.lng.toFixed(6);
                };
                m.on('click', window._kl_prof_handler);
                break;
            }
        } catch (_) {}
    }
})();
"""

_CLEAR_PROFILE_JS = """
(function() {
    var m = window._kl_prof_map;
    if (m && window._kl_prof_handler) {
        m.off('click', window._kl_prof_handler);
    }
    if (window._kl_prof_layers) {
        window._kl_prof_layers.forEach(function(layer) {
            try { layer.remove(); } catch (_) {}
        });
    }
    window._kl_prof_active = false;
    window._kl_prof_p1 = null;
    window._kl_prof_layers = [];
    window._kl_prof_handler = null;
})();
"""


class MapView(QWidget):
    """Map container using QWebEngineView when available, QTextBrowser otherwise."""

    marker_placed = Signal(float, float)
    profile_point_placed = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._web_view: Any | None = None
        self._fallback: QTextBrowser | None = None

        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            self._fallback = QTextBrowser()
            self._fallback.setOpenExternalLinks(True)
            layout.addWidget(self._fallback)
        else:
            self._init_web_view(layout)

        self.set_empty_state()

    def _init_web_view(self, layout: QVBoxLayout) -> None:
        try:
            from PySide6.QtCore import QUrlQuery
            from PySide6.QtWebEngineCore import QWebEnginePage
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except ImportError:
            self._fallback = QTextBrowser()
            self._fallback.setOpenExternalLinks(True)
            layout.addWidget(self._fallback)
            return

        outer = self

        class _KarstLabPage(QWebEnginePage):
            def acceptNavigationRequest(
                self_page,
                url: Any,
                nav_type: Any,
                is_main_frame: bool,
            ) -> bool:
                if url.scheme() == "karstlab" and url.host() == "addmarker":
                    q = QUrlQuery(url.query())
                    try:
                        lat = float(q.queryItemValue("lat"))
                        lon = float(q.queryItemValue("lon"))
                        outer.marker_placed.emit(lat, lon)
                    except ValueError:
                        pass
                    return False
                if url.scheme() == "karstlab" and url.host() == "profile":
                    q = QUrlQuery(url.query())
                    try:
                        lat = float(q.queryItemValue("lat"))
                        lon = float(q.queryItemValue("lon"))
                        outer.profile_point_placed.emit(lat, lon)
                    except ValueError:
                        pass
                    return False
                result: bool = super().acceptNavigationRequest(url, nav_type, is_main_frame)
                return result

        self._web_view = QWebEngineView()
        self._web_view.setPage(_KarstLabPage(self._web_view))
        layout.addWidget(self._web_view)

    def inject_click_handler(self) -> None:
        if self._web_view is not None:
            self._web_view.page().runJavaScript(_CLICK_HANDLER_JS)

    def clear_click_handler(self) -> None:
        if self._web_view is not None:
            self._web_view.page().runJavaScript(_CLEAR_CLICK_JS)

    def start_distance_mode(self) -> None:
        if self._web_view is not None:
            self._web_view.page().runJavaScript(_DISTANCE_HANDLER_JS)

    def clear_distance_mode(self) -> None:
        if self._web_view is not None:
            self._web_view.page().runJavaScript(_CLEAR_DISTANCE_JS)

    def start_profile_mode(self) -> None:
        if self._web_view is not None:
            self._web_view.page().runJavaScript(_PROFILE_HANDLER_JS)

    def clear_profile_mode(self) -> None:
        if self._web_view is not None:
            self._web_view.page().runJavaScript(_CLEAR_PROFILE_JS)

    def inject_poi_layer(
        self,
        geojson_str: str,
        layer_name: str = "BRGM Cavités",
        color: str = "#dc2626",
    ) -> None:
        if self._web_view is None:
            return
        script = (
            _INJECT_POI_JS.replace("__DATA__", json.dumps(geojson_str))
            .replace("__LAYER__", json.dumps(layer_name))
            .replace("__COLOR__", json.dumps(color))
        )
        self._web_view.page().runJavaScript(script)

    def set_empty_state(self) -> None:
        self.set_html(
            """
            <html>
                <body style="margin:0;background:#1a1f2e;color:#e8eaf0;
                           font-family:Arial;">
                <div style="height:100vh;display:flex;align-items:center;
                            justify-content:center;text-align:center;">
                  <div>
                    <h1 style="font-size:20px;margin:0 0 8px;">KarstLab</h1>
                    <p style="color:#9ca3b8;margin:0;">Select a DEM and run analysis.</p>
                  </div>
                </div>
              </body>
            </html>
            """
        )

    def load_file(self, path: Path) -> None:
        if self._web_view is not None:
            self._web_view.setUrl(QUrl.fromLocalFile(str(path)))
            return
        if self._fallback is not None:
            self._fallback.setSource(path.as_uri())

    def set_html(self, html: str) -> None:
        if self._web_view is not None:
            self._web_view.setHtml(html)
        elif self._fallback is not None:
            self._fallback.setHtml(html)


__all__ = ["MapView"]
