"""Vector format helpers for GeoJSON, KML, and GPX data."""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import geopandas as gpd
import gpxpy
import gpxpy.gpx
import simplekml
from pyproj import CRS
from shapely import ops
from shapely.geometry import LineString, Point, Polygon

logger = logging.getLogger(__name__)

WGS84_CRS = "EPSG:4326"
WGS84 = CRS.from_user_input(WGS84_CRS)
CONNECTED_SEGMENT_TOLERANCE_M = 1.0


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


def read_gpx_track(path: Path) -> gpd.GeoDataFrame:
    """Read GPX track segments into WGS84 LineString rows."""
    with path.open(encoding="utf-8") as handle:
        gpx = gpxpy.parse(handle)

    records: list[dict[str, Any]] = []
    for track in gpx.tracks:
        coordinates: list[tuple[float, float]] = []
        first_time: datetime | None = None
        for segment_index, segment in enumerate(track.segments):
            if len(segment.points) < 2:
                logger.warning(
                    "Skipping GPX track segment %d of %r: only %d point(s), need >= 2",
                    segment_index,
                    track.name,
                    len(segment.points),
                )
                continue
            for point in segment.points:
                coordinates.append((point.longitude, point.latitude))
                if first_time is None:
                    first_time = point.time
        if coordinates:
            records.append(
                {
                    "name": track.name,
                    "time": first_time,
                    "geometry": LineString(coordinates),
                }
            )

    if not records:
        raise ValueError("No GPX track segments found")
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


def read_kml_lines(path: Path) -> gpd.GeoDataFrame:
    """Read KML LineString Placemarks into a WGS84 GeoDataFrame."""
    root = ET.parse(path).getroot()
    namespace = _xml_namespace(root.tag)
    placemark_path = ".//kml:Placemark" if namespace else ".//Placemark"
    name_path = "kml:name" if namespace else "name"
    description_path = "kml:description" if namespace else "description"
    coordinates_path = (
        ".//kml:LineString/kml:coordinates" if namespace else ".//LineString/coordinates"
    )
    ns = {"kml": namespace} if namespace else {}

    records: list[dict[str, Any]] = []
    for placemark in root.findall(placemark_path, ns):
        coordinates = placemark.findtext(coordinates_path, namespaces=ns)
        if coordinates is None:
            continue
        line_coordinates = _parse_kml_coordinates(coordinates)
        if len(line_coordinates) < 2:
            continue
        records.append(
            {
                "name": placemark.findtext(name_path, default=None, namespaces=ns),
                "description": placemark.findtext(description_path, default=None, namespaces=ns),
                "geometry": LineString(line_coordinates),
            }
        )

    if not records:
        raise ValueError("No KML LineString geometries found")
    return gpd.GeoDataFrame(records, geometry="geometry", crs=WGS84_CRS)


def read_kml_geometries(path: Path) -> gpd.GeoDataFrame:
    """Read all KML geometries (Point, LineString, Polygon) into WGS84.

    Handles geometries nested in ``<MultiGeometry>`` and is namespace-agnostic
    (matches local element names), so it tolerates the malformed namespace
    declarations some exporters emit. One row per geometry; the row ``name`` is
    the parent Placemark name. Raises ValueError if no geometry is found.
    """
    root = ET.parse(path).getroot()
    records: list[dict[str, Any]] = []
    for placemark in _iter_local(root, "Placemark"):
        name = _local_text(placemark, "name")
        for element in placemark.iter():
            geometry = _kml_element_geometry(element)
            if geometry is not None:
                records.append({"name": name, "geometry": geometry})

    if not records:
        raise ValueError("No KML geometries found")
    return gpd.GeoDataFrame(records, geometry="geometry", crs=WGS84_CRS)


def survey_line_geometry(
    gdf: gpd.GeoDataFrame,
    *,
    downstream_end: Literal["first", "last"] = "first",
) -> LineString:
    """Extract a connected survey LineString using the downstream-end convention."""
    if gdf.empty:
        raise ValueError("survey line GeoDataFrame is empty")
    if gdf.crs is None:
        raise ValueError("survey line GeoDataFrame must have a CRS")

    lines = [geometry for geometry in gdf.geometry if isinstance(geometry, LineString)]
    if len(lines) != len(gdf):
        raise ValueError("survey line GeoDataFrame must contain only LineString geometries")

    metric_lines = _metric_lines(gdf)
    coordinates: list[tuple[float, float]] = []
    for index, line in enumerate(lines):
        if index > 0:
            previous_end = Point(metric_lines[index - 1].coords[-1])
            current_start = Point(metric_lines[index].coords[0])
            if previous_end.distance(current_start) > CONNECTED_SEGMENT_TOLERANCE_M:
                raise ValueError("survey line segments must be end-to-end connected")
        coordinates.extend((float(x), float(y)) for x, y in line.coords)

    if downstream_end == "last":
        coordinates.reverse()
    return LineString(coordinates)


def _as_wgs84(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if frame.crs is None:
        raise ValueError("Vector data must have a CRS before export")
    if CRS.from_user_input(frame.crs).equals(WGS84, ignore_axis_order=True):
        return frame
    return frame.to_crs(WGS84_CRS)


def _description(properties: dict[str, Any]) -> str:
    filtered = {key: value for key, value in properties.items() if key != "geometry"}
    return json.dumps(filtered, ensure_ascii=False, default=str)


def _parse_kml_coordinates(coordinates: str) -> list[tuple[float, float]]:
    parsed: list[tuple[float, float]] = []
    for coordinate in coordinates.split():
        lon, lat, *_ = [float(value) for value in coordinate.split(",")]
        parsed.append((lon, lat))
    return parsed


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _iter_local(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element.iter() if _local_name(child.tag) == name]


def _local_text(element: ET.Element, name: str) -> str | None:
    for child in element.iter():
        if _local_name(child.tag) == name and child.text:
            return child.text.strip()
    return None


def _first_coordinates_text(element: ET.Element) -> str | None:
    for child in element.iter():
        if _local_name(child.tag) == "coordinates" and child.text:
            return child.text
    return None


def _kml_element_geometry(element: ET.Element) -> Any:
    """Build a shapely geometry from a Point/LineString/Polygon KML element."""
    geometry_type = _local_name(element.tag)
    if geometry_type not in {"Point", "LineString", "Polygon"}:
        return None
    coordinates_text = _first_coordinates_text(element)
    if not coordinates_text:
        return None
    coordinates = _parse_kml_coordinates(coordinates_text)
    if geometry_type == "Point":
        return Point(coordinates[0]) if coordinates else None
    if geometry_type == "LineString":
        return LineString(coordinates) if len(coordinates) >= 2 else None
    return Polygon(coordinates) if len(coordinates) >= 3 else None


def _metric_lines(gdf: gpd.GeoDataFrame) -> list[LineString]:
    metric_crs = gdf.crs
    if CRS.from_user_input(metric_crs).is_geographic:
        metric_crs = gdf.estimate_utm_crs()
    projected = gdf.to_crs(metric_crs)
    return [ops.transform(lambda x, y, z=None: (x, y), geometry) for geometry in projected.geometry]


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
