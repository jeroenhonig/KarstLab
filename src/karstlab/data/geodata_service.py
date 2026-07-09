"""Generic WFS geodata fetch service (BRGM/IGN OGC services).

Mirrors the robustness contract of :mod:`karstlab.data.poi`: fetches happen
server-side (no browser/CORS), the function **never raises** on network or parse
failure (returns ``None``), and raw responses are cached to disk. Output is a
WGS84 (EPSG:4326) GeoJSON ``FeatureCollection`` dict ready for Leaflet.

Supports both WFS dialects observed on French services:
- WFS 2.0.0 (``typeNames`` / ``count`` / ``startIndex``) — e.g. infoterre GeoServer
- WFS 1.0.0/1.1.0 (``typeName`` / ``maxFeatures``) — older MapServer endpoints

and both output formats: ``application/json`` (GeoServer) and GML (MapServer is
GML-only). Parsing for GeoJSON, GML and shapefiles is handled uniformly by
``geopandas`` / ``pyogrio`` (GDAL), which are already dependencies.
"""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import geopandas as gpd

logger = logging.getLogger(__name__)

# WFS 2.0 uses count/typeNames; 1.x uses maxFeatures/typeName.
_WFS2_PREFIX = "2."

BBox = tuple[float, float, float, float]  # (xmin, ymin, xmax, ymax)


def build_wfs_getfeature_url(
    base_url: str,
    typename: str,
    *,
    version: str = "2.0.0",
    output_format: str = "application/json",
    srs: str = "EPSG:2154",
    bbox: BBox | None = None,
    bbox_srs: str = "EPSG:2154",
    max_features: int = 5000,
    cql_filter: str | None = None,
    geometry_name: str = "geom",
) -> str:
    """Build a WFS GetFeature request URL for either WFS dialect (pure function).

    GeoServer rejects a ``BBOX`` parameter combined with ``CQL_FILTER``; when both
    a bbox and a filter are supplied the bbox is folded into the CQL via the
    ``BBOX(<geometry>, ...)`` predicate instead.
    """
    params: dict[str, str] = {
        "service": "WFS",
        "version": version,
        "request": "GetFeature",
        "outputFormat": output_format,
        "srsName": srs,
    }
    is_wfs2 = version.startswith(_WFS2_PREFIX)
    if is_wfs2:
        params["typeNames"] = typename
        params["count"] = str(max_features)
    else:
        params["typeName"] = typename
        params["maxFeatures"] = str(max_features)
    if bbox is not None and cql_filter:
        xmin, ymin, xmax, ymax = bbox
        spatial = f"BBOX({geometry_name},{xmin},{ymin},{xmax},{ymax},'{bbox_srs}')"
        params["cql_filter"] = f"({cql_filter}) AND {spatial}"
    elif bbox is not None:
        params["bbox"] = ",".join(str(v) for v in bbox) + f",{bbox_srs}"
    elif cql_filter:
        params["cql_filter"] = cql_filter
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urllib.parse.urlencode(params)}"


def fetch_wfs_geojson(
    *,
    base_url: str,
    typename: str,
    version: str = "2.0.0",
    output_format: str = "application/json",
    srs: str = "EPSG:2154",
    bbox: BBox | None = None,
    bbox_srs: str = "EPSG:2154",
    max_features: int = 5000,
    cql_filter: str | None = None,
    geometry_name: str = "geom",
    target_crs: str = "EPSG:4326",
    cache_dir: Path | None = None,
    timeout: float = 20.0,
) -> dict[str, Any] | None:
    """Fetch a WFS layer and return a WGS84 GeoJSON FeatureCollection, or ``None``.

    Never raises: returns ``None`` on any network/parse failure, falling back to a
    cached raw response when available.
    """
    url = build_wfs_getfeature_url(
        base_url,
        typename,
        version=version,
        output_format=output_format,
        srs=srs,
        bbox=bbox,
        bbox_srs=bbox_srs,
        max_features=max_features,
        cql_filter=cql_filter,
        geometry_name=geometry_name,
    )
    cache_path = _cache_path(cache_dir, url, output_format) if cache_dir else None

    raw = _http_get(url, timeout=timeout)
    if raw is not None and cache_path is not None:
        try:
            cache_path.write_bytes(raw)
        except OSError:
            logger.debug("Could not write WFS cache %s", cache_path)
    if raw is None and cache_path is not None and cache_path.exists():
        raw = cache_path.read_bytes()
    if raw is None:
        return None

    return _parse_to_geojson(raw, source_srs=srs, target_crs=target_crs)


def _http_get(url: str, *, timeout: float) -> bytes | None:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "KarstLab"})
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https OGC endpoints
            return bytes(response.read())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("WFS fetch failed for %s: %s", url, exc)
        return None


def _parse_to_geojson(
    raw: bytes, *, source_srs: str, target_crs: str
) -> dict[str, Any] | None:
    """Parse raw WFS bytes (GeoJSON/GML) → reprojected GeoJSON FeatureCollection.

    Returns an empty FeatureCollection when the response has no features, and
    ``None`` when the bytes are not a readable feature collection (e.g. a WFS
    ``ServiceException`` XML document).
    """
    import io

    try:
        frame = gpd.read_file(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001 - any unreadable payload → treat as miss
        logger.warning("WFS payload not parseable as features: %s", exc)
        return None

    if frame.empty:
        return {"type": "FeatureCollection", "features": []}
    if frame.crs is None:
        frame = frame.set_crs(source_srs, allow_override=True)
    frame = frame.to_crs(target_crs)
    return dict(json.loads(frame.to_json()))


def _cache_path(cache_dir: Path, url: str, output_format: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    suffix = ".json" if "json" in output_format.lower() else ".gml"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"wfs_{digest}{suffix}"


__all__ = ["BBox", "build_wfs_getfeature_url", "fetch_wfs_geojson"]
