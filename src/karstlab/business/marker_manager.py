"""Marker management functions for GPS waypoints, manual entries, and POI records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import Point

from karstlab.data.vector_io import to_gpx, to_kml

WGS84_CRS = "EPSG:4326"


@dataclass(frozen=True)
class ManualMarker:
    """A manually-entered marker with coordinate and metadata."""

    name: str
    lat: float
    lon: float
    description: str = ""


def parse_coordinate(text: str) -> tuple[float, float]:
    """Parse a lat/lon string into (lat, lon) floats.

    Accepts formats:
    - "44.1234, 1.5678"
    - "44.1234 1.5678"
    - "44d07m24sN 1d34m04sE"  (DMS with N/E/S/W)
    - "N44.1234 E1.5678"

    Returns:
        A tuple of (latitude, longitude).

    Raises:
        ValueError: If the input format is invalid or coordinates out of range.
    """
    text = text.strip()

    # Try comma-separated decimals
    if "," in text:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) == 2:
            try:
                lat = float(parts[0])
                lon = float(parts[1])
                _validate_coordinates(lat, lon)
                return (lat, lon)
            except ValueError as e:
                if "out of range" in str(e):
                    raise e
                pass

    # Try space-separated decimals
    parts = text.split()
    if len(parts) == 2:
        try:
            lat = float(parts[0])
            lon = float(parts[1])
            _validate_coordinates(lat, lon)
            return (lat, lon)
        except ValueError as e:
            if "out of range" in str(e):
                raise e
            pass

    # Try DMS format: degree symbol followed by minutes/seconds
    # Matches patterns like: 44°07’24"N or 44°0724N or variations
    dms_pattern = (
        r"(\d+)[^\d]+(\d+)[^\d]*(\d+)?[^\d]*([NSEWnsew])"
        r"\s+(\d+)[^\d]+(\d+)[^\d]*(\d+)?[^\d]*([NSEWnsew])"
    )
    match = re.match(dms_pattern, text)
    if match:
        groups = match.groups()
        deg1, min1, sec1, dir1, deg2, min2, sec2, dir2 = groups
        try:
            lat = _dms_to_decimal(int(deg1), int(min1), float(sec1 or 0), str(dir1))
            lon = _dms_to_decimal(int(deg2), int(min2), float(sec2 or 0), str(dir2))
            _validate_coordinates(lat, lon)
            return (lat, lon)
        except (ValueError, IndexError) as e:
            raise ValueError(f"Invalid DMS format: {text}") from e

    # Try prefixed format: "N44.1234 E1.5678"
    prefixed_pattern = r"([NSEWnsew])([\d.]+)\s+([NSEWnsew])([\d.]+)"
    match = re.match(prefixed_pattern, text)
    if match:
        try:
            dir1, val1, dir2, val2 = match.groups()
            coord1 = float(val1)
            coord2 = float(val2)
            lat, lon = _apply_direction(dir1, coord1, dir2, coord2)
            _validate_coordinates(lat, lon)
            return (lat, lon)
        except (ValueError, IndexError) as e:
            raise ValueError(f"Invalid prefixed format: {text}") from e

    raise ValueError(
        f"Could not parse coordinate: {text!r}. "
        "Accepted formats: decimal comma/space separated, "
        "DMS with degree/minute/second separators, or prefixed N/S/E/W"
    )


def manual_marker_to_geodataframe(marker: ManualMarker) -> gpd.GeoDataFrame:
    """Return a single-row GeoDataFrame for a manual marker in WGS84.

    Args:
        marker: A ManualMarker instance.

    Returns:
        A GeoDataFrame with a single Point row, WGS84 CRS.
    """
    return gpd.GeoDataFrame(
        [
            {
                "name": marker.name,
                "description": marker.description,
                "geometry": Point(marker.lon, marker.lat),
            }
        ],
        geometry="geometry",
        crs=WGS84_CRS,
    )


def merge_marker_frames(*frames: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Concatenate marker GeoDataFrames, reset index, and drop empty frames.

    Args:
        *frames: Variable number of GeoDataFrames to merge.

    Returns:
        A merged GeoDataFrame with reset index. Returns an empty GeoDataFrame
        with WGS84 CRS if all inputs are empty.
    """
    non_empty = [f for f in frames if not f.empty]

    if not non_empty:
        # Create empty GeoDataFrame with proper structure
        return gpd.GeoDataFrame(
            {"name": [], "geometry": []},
            geometry="geometry",
            crs=WGS84_CRS,
        )

    merged = gpd.pd.concat(non_empty, ignore_index=True)
    return merged.reset_index(drop=True)


def export_markers_to_gpx(frame: gpd.GeoDataFrame, path: Path) -> Path:
    """Write markers as GPX waypoints.

    Args:
        frame: A GeoDataFrame with Point geometries.
        path: Output file path.

    Returns:
        The path where the GPX was written.
    """
    return to_gpx(frame, path, name_field="name")


def export_markers_to_kml(frame: gpd.GeoDataFrame, path: Path) -> Path:
    """Write markers as KML placemarks.

    Args:
        frame: A GeoDataFrame with Point geometries.
        path: Output file path.

    Returns:
        The path where the KML was written.
    """
    return to_kml(frame, path, name_field="name")


def poi_records_to_geodataframe(records: list[Any]) -> gpd.GeoDataFrame:
    """Convert a list of PoiRecord-like objects to a GeoDataFrame.

    Each record is expected to have attributes: lat, lon, name, description, source.

    Args:
        records: A list of objects with lat, lon, name, description, source attributes.

    Returns:
        A GeoDataFrame with Point geometry, WGS84 CRS.
    """
    if not records:
        # Create empty GeoDataFrame with proper structure
        return gpd.GeoDataFrame(
            {"name": [], "description": [], "source": [], "geometry": []},
            geometry="geometry",
            crs=WGS84_CRS,
        )

    data = []
    for record in records:
        data.append(
            {
                "name": str(record.name),
                "description": str(record.description),
                "source": str(record.source),
                "geometry": Point(record.lon, record.lat),
            }
        )

    return gpd.GeoDataFrame(data, geometry="geometry", crs=WGS84_CRS)


def _validate_coordinates(lat: float, lon: float) -> None:
    """Validate latitude and longitude ranges.

    Raises:
        ValueError: If coordinates are out of valid range.
    """
    if not -90 <= lat <= 90:
        raise ValueError(f"Latitude out of range [-90, 90]: {lat}")
    if not -180 <= lon <= 180:
        raise ValueError(f"Longitude out of range [-180, 180]: {lon}")


def _dms_to_decimal(degrees: int, minutes: int, seconds: float, direction: str) -> float:
    """Convert degrees/minutes/seconds to decimal.

    Args:
        degrees: Degrees value.
        minutes: Minutes value.
        seconds: Seconds value.
        direction: Cardinal direction (N, S, E, W).

    Returns:
        Decimal coordinate value.

    Raises:
        ValueError: If direction is invalid.
    """
    value = degrees + minutes / 60.0 + seconds / 3600.0
    if direction.upper() in ("S", "W"):
        value = -value
    elif direction.upper() not in ("N", "E"):
        raise ValueError(f"Invalid direction: {direction}")
    return value


def _apply_direction(
    dir1: str, val1: float, dir2: str, val2: float
) -> tuple[float, float]:
    """Apply cardinal directions to two coordinate values.

    Args:
        dir1: Cardinal direction for first value (N/S/E/W).
        val1: First coordinate value.
        dir2: Cardinal direction for second value (N/S/E/W).
        val2: Second coordinate value.

    Returns:
        A tuple of (latitude, longitude).

    Raises:
        ValueError: If directions are invalid or mixed up.
    """
    dir1_upper = dir1.upper()
    dir2_upper = dir2.upper()

    # Determine which is lat and which is lon
    lat_val: float | None = None
    lon_val: float | None = None

    if dir1_upper in ("N", "S"):
        lat_val = val1 if dir1_upper == "N" else -val1
        lon_val = val2 if dir2_upper == "E" else -val2
    elif dir1_upper in ("E", "W"):
        lon_val = val1 if dir1_upper == "E" else -val1
        lat_val = val2 if dir2_upper == "N" else -val2
    else:
        raise ValueError(f"Invalid direction: {dir1}")

    if lat_val is None or lon_val is None:
        raise ValueError(f"Could not parse directions: {dir1}, {dir2}")

    return (lat_val, lon_val)
