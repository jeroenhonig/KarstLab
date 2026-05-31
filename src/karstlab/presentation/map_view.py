"""Folium/Leaflet map container widget for KarstLab."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

_CLICK_HANDLER_JS = """
(function() {
    if (window._karstlab_click_active) return;
    window._karstlab_click_active = true;
    for (var k in window) {
        try {
            var o = window[k];
            if (o && typeof o === 'object' && o._leaflet_id !== undefined
                    && typeof o.on === 'function') {
                o.on('click', function(e) {
                    window.location.href = 'karstlab://addmarker?lat='
                        + e.latlng.lat.toFixed(6) + '&lon='
                        + e.latlng.lng.toFixed(6);
                });
            }
        } catch (_) {}
    }
})();
"""

_CLEAR_CLICK_JS = """
(function() {
    window._karstlab_click_active = false;
    for (var k in window) {
        try {
            var o = window[k];
            if (o && typeof o === 'object' && o._leaflet_id !== undefined
                    && typeof o.off === 'function') {
                o.off('click');
            }
        } catch (_) {}
    }
})();
"""


class MapView(QWidget):
    """Map container using QWebEngineView when available, QTextBrowser otherwise."""

    marker_placed = Signal(float, float)

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
