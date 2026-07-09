"""Tests for the generic WFS geodata service (no network — fetch is monkeypatched)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import shapely.geometry as sgeom

from karstlab.data import geodata_service as gs

# ─── URL building (pure) ─────────────────────────────────────────────────────


def test_build_url_wfs2_uses_count_and_typenames() -> None:
    url = gs.build_wfs_getfeature_url(
        "https://infoterre.brgm.fr/geoserver/ows",
        "BRGM:c50_l_divers",
        version="2.0.0",
        bbox=(920000.0, 6650000.0, 1010000.0, 6740000.0),
        max_features=5000,
    )
    assert "typeNames=BRGM%3Ac50_l_divers" in url
    assert "count=5000" in url and "maxFeatures" not in url
    # bbox-only request keeps the BBOX parameter.
    assert "bbox=920000.0%2C6650000.0%2C1010000.0%2C6740000.0%2CEPSG%3A2154" in url
    assert "outputFormat=application%2Fjson" in url


def test_build_url_folds_bbox_into_cql_when_both_present() -> None:
    # GeoServer rejects BBOX param + CQL_FILTER together → fold bbox into the CQL.
    url = gs.build_wfs_getfeature_url(
        "https://infoterre.brgm.fr/geoserver/ows",
        "BRGM:c50_l_divers",
        bbox=(920000.0, 6650000.0, 1010000.0, 6740000.0),
        cql_filter="code=8",
        geometry_name="geom",
    )
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(url).query)
    assert "bbox" not in qs  # no standalone BBOX param
    expected = "(code=8) AND BBOX(geom,920000.0,6650000.0,1010000.0,6740000.0,'EPSG:2154')"
    assert qs["cql_filter"] == [expected]


def test_build_url_wfs1_uses_maxfeatures_and_typename() -> None:
    url = gs.build_wfs_getfeature_url(
        "https://geoservices.brgm.fr/geologie",
        "BSS_EAU_POINT",
        version="1.0.0",
        output_format="GML2",
    )
    assert "typeName=BSS_EAU_POINT" in url and "typeNames" not in url
    assert "maxFeatures=5000" in url and "count=" not in url


# ─── Parsing + reprojection ──────────────────────────────────────────────────


def _l93_geojson_bytes() -> bytes:
    # A GeoServer-style GeoJSON line near the Doubs in Lambert-93 (no RFC crs
    # member → service SRS supplied by the caller, exercising the set_crs branch).
    fc = {
        "type": "FeatureCollection",
        # GeoServer WFS emits the source CRS as a (legacy) crs member; GDAL honours it.
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}},
        "features": [
            {
                "type": "Feature",
                "properties": {"code": 8, "attr": "Dolines"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[948000.0, 6700000.0], [948100.0, 6700100.0]],
                },
            }
        ],
    }
    return json.dumps(fc).encode("utf-8")


def test_parse_geojson_reprojects_l93_to_wgs84() -> None:
    result = gs._parse_to_geojson(
        _l93_geojson_bytes(), source_srs="EPSG:2154", target_crs="EPSG:4326"
    )
    assert result is not None
    lon, lat = result["features"][0]["geometry"]["coordinates"][0]
    assert 5.0 < lon < 7.5  # Doubs longitude
    assert 46.5 < lat < 48.0  # Doubs latitude


def test_parse_gml_reprojects_l93_to_wgs84(tmp_path: Path) -> None:
    # Build a real GML payload in EPSG:2154 (the BSS_EAU_POINT format), then parse.
    gdf = gpd.GeoDataFrame(
        {"nature_pe": ["Source"]},
        geometry=[sgeom.Point(948000.0, 6700000.0)],
        crs="EPSG:2154",
    )
    gml_path = tmp_path / "points.gml"
    gdf.to_file(gml_path, driver="GML")
    result = gs._parse_to_geojson(
        gml_path.read_bytes(), source_srs="EPSG:2154", target_crs="EPSG:4326"
    )
    assert result is not None
    assert result["features"][0]["geometry"]["type"] == "Point"
    lon, lat = result["features"][0]["geometry"]["coordinates"]
    assert 5.0 < lon < 7.5 and 46.5 < lat < 48.0


def test_parse_empty_collection_returns_empty() -> None:
    empty = json.dumps({"type": "FeatureCollection", "features": []}).encode()
    result = gs._parse_to_geojson(empty, source_srs="EPSG:2154", target_crs="EPSG:4326")
    assert result == {"type": "FeatureCollection", "features": []}


def test_parse_service_exception_returns_none() -> None:
    xml = (
        b"<?xml version='1.0'?><ServiceExceptionReport>"
        b"<ServiceException>boom</ServiceException></ServiceExceptionReport>"
    )
    assert gs._parse_to_geojson(xml, source_srs="EPSG:2154", target_crs="EPSG:4326") is None


# ─── Fetch orchestration (never raises; caches) ──────────────────────────────


def test_fetch_returns_none_on_network_failure(monkeypatch: Any) -> None:
    monkeypatch.setattr(gs, "_http_get", lambda *_a, **_k: None)
    assert (
        gs.fetch_wfs_geojson(base_url="https://x/ows", typename="T", cache_dir=None) is None
    )


def test_fetch_parses_and_caches_then_serves_from_cache(
    tmp_path: Path, monkeypatch: Any
) -> None:
    payload = _l93_geojson_bytes()
    monkeypatch.setattr(gs, "_http_get", lambda *_a, **_k: payload)
    first = gs.fetch_wfs_geojson(
        base_url="https://x/ows", typename="T", srs="EPSG:2154", cache_dir=tmp_path
    )
    assert first is not None and first["features"]
    # A raw cache file was written.
    assert any(p.suffix == ".json" for p in tmp_path.iterdir())

    # Network now fails, but the cached raw response still yields the layer.
    monkeypatch.setattr(gs, "_http_get", lambda *_a, **_k: None)
    second = gs.fetch_wfs_geojson(
        base_url="https://x/ows", typename="T", srs="EPSG:2154", cache_dir=tmp_path
    )
    assert second is not None and second["features"]
