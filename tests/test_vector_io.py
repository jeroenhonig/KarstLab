from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import geopandas as gpd
import gpxpy
import pytest
from pyproj import CRS
from shapely.geometry import LineString, Point, Polygon

from karstlab.data.vector_io import (
    _as_wgs84,
    _description,
    read_gpx_track,
    read_gpx_waypoints,
    read_kml_lines,
    read_kml_points,
    survey_line_geometry,
    to_geojson,
    to_gpx,
    to_kml,
)


def test_to_geojson_writes_feature_collection(tmp_path) -> None:  # type: ignore[no-untyped-def]
    frame = gpd.GeoDataFrame(
        [{"name": "Doline 1", "depth_m": 4.2, "geometry": Point(5.1, 43.2)}],
        geometry="geometry",
        crs="EPSG:4326",
    )

    output = to_geojson(frame, tmp_path / "dolines.geojson")

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["type"] == "FeatureCollection"
    assert payload["features"][0]["properties"]["name"] == "Doline 1"
    assert payload["features"][0]["geometry"]["type"] == "Point"


def test_as_wgs84_uses_semantic_crs_equality() -> None:
    frame = gpd.GeoDataFrame(
        [{"name": "Marker", "geometry": Point(5.1, 43.2)}],
        geometry="geometry",
        crs=CRS.from_string("OGC:CRS84"),
    )

    assert _as_wgs84(frame) is frame


def test_description_does_not_mutate_properties() -> None:
    properties = {"name": "Doline 1", "geometry": Point(5.1, 43.2)}

    description = _description(properties)

    assert json.loads(description) == {"name": "Doline 1"}
    assert "geometry" in properties


def test_to_kml_writes_points_lines_and_polygons(tmp_path) -> None:  # type: ignore[no-untyped-def]
    frame = gpd.GeoDataFrame(
        [
            {"name": "Point", "geometry": Point(5.1, 43.2)},
            {"name": "Line", "geometry": LineString([(5.1, 43.2), (5.2, 43.3)])},
            {
                "name": "Polygon",
                "geometry": Polygon([(5.1, 43.2), (5.2, 43.2), (5.2, 43.3), (5.1, 43.2)]),
            },
        ],
        geometry="geometry",
        crs="EPSG:4326",
    )

    output = to_kml(frame, tmp_path / "vectors.kml")
    root = ET.parse(output).getroot()
    namespace = {"kml": "http://www.opengis.net/kml/2.2"}

    assert len(root.findall(".//kml:Placemark", namespace)) == 3
    assert root.find(".//kml:Point", namespace) is not None
    assert root.find(".//kml:LineString", namespace) is not None
    assert root.find(".//kml:Polygon", namespace) is not None


def test_to_gpx_writes_waypoints_and_import_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    frame = gpd.GeoDataFrame(
        [
            {"name": "Doline 1", "geometry": Point(5.1, 43.2)},
            {"name": "Doline 2", "geometry": Point(5.2, 43.3)},
        ],
        geometry="geometry",
        crs="EPSG:4326",
    )

    output = to_gpx(frame, tmp_path / "top_depressions.gpx")
    with output.open(encoding="utf-8") as handle:
        parsed = gpxpy.parse(handle)
    loaded = read_gpx_waypoints(output)

    assert [waypoint.name for waypoint in parsed.waypoints] == ["Doline 1", "Doline 2"]
    assert loaded.crs == "EPSG:4326"
    assert loaded["name"].to_list() == ["Doline 1", "Doline 2"]
    assert loaded.geometry.iloc[0].x == 5.1
    assert loaded.geometry.iloc[0].y == 43.2


def test_to_gpx_rejects_non_point_geometries_before_writing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    frame = gpd.GeoDataFrame(
        [{"name": "Line", "geometry": LineString([(5.1, 43.2), (5.2, 43.3)])}],
        geometry="geometry",
        crs="EPSG:4326",
    )
    output = tmp_path / "bad.gpx"

    with pytest.raises(ValueError, match="point geometries"):
        to_gpx(frame, output)

    assert not output.exists()


def test_read_kml_points_parses_placemarks(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "markers.kml"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Cave entrance</name>
      <Point><coordinates>5.123,43.456,0</coordinates></Point>
    </Placemark>
  </Document>
</kml>
""",
        encoding="utf-8",
    )

    loaded = read_kml_points(path)

    assert loaded.crs == "EPSG:4326"
    assert loaded["name"].to_list() == ["Cave entrance"]
    assert loaded.geometry.iloc[0].x == 5.123
    assert loaded.geometry.iloc[0].y == 43.456


def test_read_gpx_track_single_segment_returns_linestring(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "survey.gpx"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="KarstLab test">
  <trk>
    <name>Survey A</name>
    <trkseg>
      <trkpt lat="43.100" lon="5.100"><time>2026-01-01T10:00:00Z</time></trkpt>
      <trkpt lat="43.101" lon="5.101"><time>2026-01-01T10:01:00Z</time></trkpt>
      <trkpt lat="43.102" lon="5.102"><time>2026-01-01T10:02:00Z</time></trkpt>
    </trkseg>
  </trk>
</gpx>
""",
        encoding="utf-8",
    )

    loaded = read_gpx_track(path)

    assert loaded.crs == "EPSG:4326"
    assert loaded["name"].to_list() == ["Survey A"]
    assert loaded.geometry.iloc[0].geom_type == "LineString"
    assert len(loaded.geometry.iloc[0].coords) == 3
    assert loaded.geometry.iloc[0].coords[0] == (5.1, 43.1)
    assert loaded["time"].iloc[0].isoformat().startswith("2026-01-01T10:00:00")


def test_read_gpx_track_merges_connected_segments_in_order(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "survey.gpx"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="KarstLab test">
  <trk>
    <name>Survey B</name>
    <trkseg>
      <trkpt lat="43.100" lon="5.100" />
      <trkpt lat="43.101" lon="5.101" />
    </trkseg>
    <trkseg>
      <trkpt lat="43.101" lon="5.101" />
      <trkpt lat="43.102" lon="5.102" />
    </trkseg>
  </trk>
</gpx>
""",
        encoding="utf-8",
    )

    loaded = read_gpx_track(path)

    assert loaded.crs == "EPSG:4326"
    assert list(loaded.geometry.iloc[0].coords) == [
        (5.1, 43.1),
        (5.101, 43.101),
        (5.101, 43.101),
        (5.102, 43.102),
    ]


def test_read_kml_lines_parses_linestring_placemarks(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "survey.kml"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Survey C</name>
      <description>main line</description>
      <LineString><coordinates>
        5.100,43.100,0 5.101,43.101,0 5.102,43.102,0
      </coordinates></LineString>
    </Placemark>
  </Document>
</kml>
""",
        encoding="utf-8",
    )

    loaded = read_kml_lines(path)

    assert loaded.crs == "EPSG:4326"
    assert loaded["name"].to_list() == ["Survey C"]
    assert loaded["description"].to_list() == ["main line"]
    assert list(loaded.geometry.iloc[0].coords) == [
        (5.1, 43.1),
        (5.101, 43.101),
        (5.102, 43.102),
    ]


def test_survey_line_geometry_reverses_when_downstream_end_is_last() -> None:
    frame = gpd.GeoDataFrame(
        [{"geometry": LineString([(5.1, 43.1), (5.2, 43.2), (5.3, 43.3)])}],
        geometry="geometry",
        crs="EPSG:4326",
    )

    default = survey_line_geometry(frame)
    reversed_line = survey_line_geometry(frame, downstream_end="last")

    assert list(default.coords) == [(5.1, 43.1), (5.2, 43.2), (5.3, 43.3)]
    assert list(reversed_line.coords) == [(5.3, 43.3), (5.2, 43.2), (5.1, 43.1)]


def test_survey_line_geometry_rejects_disconnected_segments() -> None:
    frame = gpd.GeoDataFrame(
        [
            {"geometry": LineString([(5.1, 43.1), (5.1001, 43.1001)])},
            {"geometry": LineString([(5.2, 43.2), (5.2001, 43.2001)])},
        ],
        geometry="geometry",
        crs="EPSG:4326",
    )

    with pytest.raises(ValueError, match="connected"):
        survey_line_geometry(frame)
