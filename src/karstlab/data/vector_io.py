"""Vector format helpers for GeoJSON, KML, and GPX data."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import geopandas as gpd
import gpxpy
import gpxpy.gpx
import simplekml
from pyproj import CRS
from shapely.geometry import LineString, Point, Polygon

WGS84_CRS = "EPSG:4326"
WGS84 = CRS.from_user_input(WGS84_CRS)


def to_geojson(frame: gpd.GeoDataFrame, path: Path) -> Path:
    """Write a GeoDataFrame to GeoJSON in WGS84 coordinates."""
    output = _as_wgs84(frame)
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_file(path, driver="GeoJSON")
    return path


def to_kml(frame: gpd.GeoDataFrame, path: Path, *, name_field: str = "name") -> Path:
    """Write points, lines, and polygons from a GeoDataFrame to KML."""
    output = _as_wgs84(frame)
    kml = simplekml.Kml()

    for index, row in output.iterrows():
        geometry = row.geometry
        name = str(row.get(name_field, index))
        description = _description(row.to_dict())
        _add_geometry_to_kml(kml, geometry, name=name, description=description)

    path.parent.mkdir(parents=True, exist_ok=True)
    kml.save(str(path))
    return path


def to_gpx(frame: gpd.GeoDataFrame, path: Path, *, name_field: str = "name") -> Path:
    """Write point geometries from a GeoDataFrame to GPX waypoints."""
    output = _as_wgs84(frame)
    if not all(isinstance(geometry, Point) for geometry in output.geometry):
        raise ValueError("GPX export supports point geometries only")

    gpx = gpxpy.gpx.GPX()

    for index, row in output.iterrows():
        geometry = row.geometry
        name = str(row.get(name_field, index))
        gpx.waypoints.append(
            gpxpy.gpx.GPXWaypoint(latitude=geometry.y, longitude=geometry.x, name=name)
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(gpx.to_xml(), encoding="utf-8")
    return path


def read_gpx_waypoints(path: Path) -> gpd.GeoDataFrame:
    """Read GPX waypoints into a WGS84 GeoDataFrame."""
    with path.open(encoding="utf-8") as handle:
        gpx = gpxpy.parse(handle)

    records = [
        {
            "name": waypoint.name,
            "description": waypoint.description,
            "elevation": waypoint.elevation,
            "geometry": Point(waypoint.longitude, waypoint.latitude),
        }
        for waypoint in gpx.waypoints
    ]
    return gpd.GeoDataFrame(records, geometry="geometry", crs=WGS84_CRS)


def read_kml_points(path: Path) -> gpd.GeoDataFrame:
    """Read Point Placemarks from a KML file into a WGS84 GeoDataFrame."""
    root = ET.parse(path).getroot()
    namespace = _xml_namespace(root.tag)
    placemark_path = ".//kml:Placemark" if namespace else ".//Placemark"
    name_path = "kml:name" if namespace else "name"
    coordinates_path = ".//kml:Point/kml:coordinates" if namespace else ".//Point/coordinates"
    ns = {"kml": namespace} if namespace else {}

    records: list[dict[str, Any]] = []
    for placemark in root.findall(placemark_path, ns):
        coordinates = placemark.findtext(coordinates_path, namespaces=ns)
        if coordinates is None:
            continue
        lon, lat, *_ = [float(value) for value in coordinates.strip().split(",")]
        records.append(
            {
                "name": placemark.findtext(name_path, default="", namespaces=ns),
                "geometry": Point(lon, lat),
            }
        )

    return gpd.GeoDataFrame(records, geometry="geometry", crs=WGS84_CRS)


def _as_wgs84(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if frame.crs is None:
        raise ValueError("Vector data must have a CRS before export")
    if CRS.from_user_input(frame.crs).equals(WGS84, ignore_axis_order=True):
        return frame
    return frame.to_crs(WGS84_CRS)


def _description(properties: dict[str, Any]) -> str:
    filtered = {key: value for key, value in properties.items() if key != "geometry"}
    return json.dumps(filtered, ensure_ascii=False, default=str)


def _add_geometry_to_kml(
    kml: simplekml.Kml,
    geometry: Any,
    *,
    name: str,
    description: str,
) -> None:
    if isinstance(geometry, Point):
        placemark = kml.newpoint(name=name, coords=[(geometry.x, geometry.y)])
    elif isinstance(geometry, LineString):
        placemark = kml.newlinestring(name=name, coords=list(geometry.coords))
    elif isinstance(geometry, Polygon):
        placemark = kml.newpolygon(
            name=name,
            outerboundaryis=list(geometry.exterior.coords),
            innerboundaryis=[list(interior.coords) for interior in geometry.interiors],
        )
    else:
        raise ValueError(f"Unsupported KML geometry type: {geometry.geom_type}")
    placemark.description = description


def _xml_namespace(tag: str) -> str:
    if tag.startswith("{"):
        return tag[1:].split("}", maxsplit=1)[0]
    return ""
