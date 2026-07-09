"""Tests for fault loading + distance-to-fault analysis (no network)."""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Any

import geopandas as gpd
import shapely.geometry as sgeom
from pyproj import Transformer

from karstlab.business import faults
from karstlab.data.schemas import Coordinate, DepressionResult

_TO_WGS84 = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)


def _l93_to_wgs84(x: float, y: float) -> Coordinate:
    lon, lat = _TO_WGS84.transform(x, y)
    return Coordinate(lat=lat, lon=lon)


def _depression(did: str, centroid: Coordinate) -> DepressionResult:
    lon, lat = centroid.lon, centroid.lat
    return DepressionResult.model_validate(
        {
            "id": did,
            "max_depth_m": 3.0,
            "area_m2": 100.0,
            "centroid": {"lat": lat, "lon": lon},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[lon, lat], [lon + 1e-4, lat], [lon + 1e-4, lat + 1e-4], [lon, lat]]
                ],
            },
        }
    )


def _write_fault_shapefile(path: Path) -> None:
    # A vertical fault line at x=948000, plus a labelled type column (DESCR).
    gdf = gpd.GeoDataFrame(
        {"DESCR": ["Faille observée"]},
        geometry=[sgeom.LineString([(948000.0, 6699000.0), (948000.0, 6701000.0)])],
        crs="EPSG:2154",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path)


def test_load_fault_lines_from_shapefile(tmp_path: Path) -> None:
    shp = tmp_path / "faults.shp"
    _write_fault_shapefile(shp)
    faults_gdf = faults.load_fault_lines(shp)
    assert faults_gdf is not None
    assert faults_gdf.crs.to_epsg() == 2154
    assert (faults_gdf.geom_type == "LineString").all()


def test_load_fault_lines_from_directory(tmp_path: Path) -> None:
    _write_fault_shapefile(tmp_path / "GEO050K_HARM_025_L_STRUCT_2154.shp")
    faults_gdf = faults.load_fault_lines(tmp_path)
    assert faults_gdf is not None and len(faults_gdf) == 1


def test_load_fault_lines_missing_returns_none(tmp_path: Path) -> None:
    assert faults.load_fault_lines(tmp_path / "nope.shp") is None


def test_annotate_fault_distances_sets_metres_and_type(tmp_path: Path) -> None:
    shp = tmp_path / "faults.shp"
    _write_fault_shapefile(shp)
    faults_gdf = faults.load_fault_lines(shp)
    assert faults_gdf is not None

    on_fault = _depression("near", _l93_to_wgs84(948000.0, 6700000.0))  # on the line
    off_fault = _depression("far", _l93_to_wgs84(948500.0, 6700000.0))  # ~500 m east

    out = faults.annotate_fault_distances([on_fault, off_fault], faults_gdf)
    near, far = out
    assert near.distance_to_fault_m is not None and near.distance_to_fault_m < 5.0
    assert far.distance_to_fault_m is not None and 480.0 < far.distance_to_fault_m < 520.0
    assert near.nearest_fault_type == "Faille observée"


def test_annotate_fault_distances_no_faults_is_noop(tmp_path: Path) -> None:
    empty = gpd.GeoDataFrame(geometry=[], crs="EPSG:2154")
    dep = _depression("d", _l93_to_wgs84(948000.0, 6700000.0))
    assert faults.annotate_fault_distances([dep], empty) == [dep]


def test_download_bdcharm_faults_caches(tmp_path: Path, monkeypatch: Any) -> None:
    import io

    class _Resp(io.BytesIO):
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

    monkeypatch.setattr(
        urllib.request, "urlopen", lambda *_a, **_k: _Resp(b"ZIPDATA")
    )
    out = faults.download_bdcharm_faults("25", cache_dir=tmp_path)
    assert out is not None and out.name == "GEO050K_HARM_025.zip"
    assert out.read_bytes() == b"ZIPDATA"

    # Second call reuses the cached file (no network needed).
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not fetch")),
    )
    assert faults.download_bdcharm_faults("25", cache_dir=tmp_path) == out


def test_line_bearing_and_distance_class() -> None:
    import shapely.geometry as sgeom

    ns = sgeom.LineString([(948000, 6699000), (948000, 6701000)])  # south->north
    ew = sgeom.LineString([(948000, 6700000), (949000, 6700000)])  # west->east
    ns_bearing = faults.line_bearing_deg(ns)
    ew_bearing = faults.line_bearing_deg(ew)
    assert ns_bearing is not None and ew_bearing is not None
    assert abs(ns_bearing - 0.0) < 1e-6
    assert abs(ew_bearing - 90.0) < 1e-6
    assert faults.fault_distance_class(10) == "<=50m"
    assert faults.fault_distance_class(75) == "<=100m"
    assert faults.fault_distance_class(300) == ">250m"
    assert faults.fault_distance_class(None) == "none"


def test_fault_orientation_label() -> None:
    assert faults.fault_orientation_label(10.0, 20.0) == "parallel"   # ~10° apart
    assert faults.fault_orientation_label(10.0, 85.0) == "transverse"  # ~75° apart
    assert faults.fault_orientation_label(10.0, 55.0) == "oblique"     # ~45° apart
    assert faults.fault_orientation_label(10.0, None) is None


def test_caveline_bearing_from_lines() -> None:
    line = gpd.GeoDataFrame(
        geometry=[sgeom.LineString([(948000, 6699000), (948000, 6701000)])], crs="EPSG:2154"
    )
    bearing = faults.caveline_bearing(line)
    assert bearing is not None
    assert abs(bearing - 0.0) < 1.0  # north-south cave line


def test_annotate_sets_orientation_vs_cave(tmp_path: Path) -> None:
    # Fault runs N-S; cave line N-S → the doline's nearest fault is "parallel".
    shp = tmp_path / "f.shp"
    _write_fault_shapefile(shp)  # N-S fault at x=948000
    faults_gdf = faults.load_fault_lines(shp)
    dep = _depression("d", _l93_to_wgs84(948100.0, 6700000.0))
    out = faults.annotate_fault_distances([dep], faults_gdf, cave_bearing=0.0)
    assert out[0].nearest_fault_bearing_deg is not None
    assert out[0].fault_orientation == "parallel"


def test_faults_to_geojson_classes(tmp_path: Path) -> None:
    gdf = gpd.GeoDataFrame(
        {"DESCR": ["Faille observée, visible", "Faille supposée, masquée"]},
        geometry=[
            sgeom.LineString([(948000, 6699000), (948000, 6701000)]),
            sgeom.LineString([(949000, 6699000), (949500, 6700000)]),
        ],
        crs="EPSG:2154",
    )
    fc = faults.faults_to_geojson(gdf)
    classes = {f["properties"]["fault_class"] for f in fc["features"]}
    assert classes == {"observed", "supposed"}
    assert all(f["properties"]["bearing_deg"] is not None for f in fc["features"])
