"""Tests for marker management functions."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

from karstlab.business.marker_manager import (
    ManualMarker,
    export_markers_to_gpx,
    export_markers_to_kml,
    manual_marker_to_geodataframe,
    merge_marker_frames,
    parse_coordinate,
    poi_records_to_geodataframe,
)
from karstlab.data.vector_io import read_gpx_waypoints, read_kml_points


class TestParseCoordinate:
    """Tests for parse_coordinate function."""

    def test_parse_decimal_comma_separated(self) -> None:
        """Parse decimal coordinates with comma separator."""
        lat, lon = parse_coordinate("44.1234, 1.5678")
        assert abs(lat - 44.1234) < 1e-6
        assert abs(lon - 1.5678) < 1e-6

    def test_parse_decimal_space_separated(self) -> None:
        """Parse decimal coordinates with space separator."""
        lat, lon = parse_coordinate("44.1234 1.5678")
        assert abs(lat - 44.1234) < 1e-6
        assert abs(lon - 1.5678) < 1e-6

    def test_parse_dms_format_with_symbols(self) -> None:
        """Parse degrees/minutes/seconds with symbols."""
        lat, lon = parse_coordinate('44°07\'24"N 1°34\'04"E')
        assert abs(lat - 44.1233) < 0.01
        assert abs(lon - 1.5678) < 0.01

    def test_parse_dms_format_with_quote_symbol(self) -> None:
        """Parse DMS with quote symbol instead of apostrophe."""
        lat, lon = parse_coordinate('44°07"24"N 1°34"04"E')
        assert abs(lat - 44.1233) < 0.01
        assert abs(lon - 1.5678) < 0.01

    def test_parse_dms_format_south_west(self) -> None:
        """Parse DMS with S and W directions."""
        lat, lon = parse_coordinate('44°07\'24"S 1°34\'04"W')
        assert abs(lat - (-44.1233)) < 0.01
        assert abs(lon - (-1.5678)) < 0.01

    def test_parse_prefixed_format_ne(self) -> None:
        """Parse prefixed format with N and E."""
        lat, lon = parse_coordinate("N44.1234 E1.5678")
        assert abs(lat - 44.1234) < 1e-6
        assert abs(lon - 1.5678) < 1e-6

    def test_parse_prefixed_format_sw(self) -> None:
        """Parse prefixed format with S and W."""
        lat, lon = parse_coordinate("S44.1234 W1.5678")
        assert abs(lat - (-44.1234)) < 1e-6
        assert abs(lon - (-1.5678)) < 1e-6

    def test_parse_with_whitespace(self) -> None:
        """Parse coordinate with extra whitespace."""
        lat, lon = parse_coordinate("  44.1234 , 1.5678  ")
        assert abs(lat - 44.1234) < 1e-6
        assert abs(lon - 1.5678) < 1e-6

    def test_parse_invalid_format_raises_error(self) -> None:
        """Raise ValueError for invalid format."""
        with pytest.raises(ValueError, match="Could not parse coordinate"):
            parse_coordinate("invalid")

    def test_parse_out_of_range_latitude(self) -> None:
        """Raise ValueError for latitude out of range."""
        with pytest.raises(ValueError, match="Latitude out of range"):
            parse_coordinate("95.0, 1.0")

    def test_parse_out_of_range_longitude(self) -> None:
        """Raise ValueError for longitude out of range."""
        with pytest.raises(ValueError, match="Longitude out of range"):
            parse_coordinate("44.0, 200.0")

    def test_parse_negative_decimals(self) -> None:
        """Parse negative decimal coordinates."""
        lat, lon = parse_coordinate("-44.1234, -1.5678")
        assert abs(lat - (-44.1234)) < 1e-6
        assert abs(lon - (-1.5678)) < 1e-6


class TestManualMarkerToGeoDataFrame:
    """Tests for manual_marker_to_geodataframe function."""

    def test_creates_single_row_frame(self) -> None:
        """Create a GeoDataFrame with one row."""
        marker = ManualMarker(name="Cave", lat=44.1234, lon=1.5678, description="Entrance")

        frame = manual_marker_to_geodataframe(marker)

        assert len(frame) == 1
        assert frame.crs == "EPSG:4326"
        assert frame.loc[0, "name"] == "Cave"
        assert frame.loc[0, "description"] == "Entrance"

    def test_correct_geometry_type(self) -> None:
        """Geometry is a Point with correct coordinates."""
        marker = ManualMarker(name="Point", lat=43.0, lon=5.0)

        frame = manual_marker_to_geodataframe(marker)

        geometry = frame.geometry.iloc[0]
        assert isinstance(geometry, Point)
        assert geometry.x == 5.0
        assert geometry.y == 43.0

    def test_columns_present(self) -> None:
        """Frame has expected columns."""
        marker = ManualMarker(name="Test", lat=44.0, lon=1.0)

        frame = manual_marker_to_geodataframe(marker)

        assert "name" in frame.columns
        assert "description" in frame.columns
        assert "geometry" in frame.columns

    def test_default_description_is_empty_string(self) -> None:
        """Default description is empty string."""
        marker = ManualMarker(name="Test", lat=44.0, lon=1.0)

        frame = manual_marker_to_geodataframe(marker)

        assert frame.loc[0, "description"] == ""


class TestMergeMarkerFrames:
    """Tests for merge_marker_frames function."""

    def test_merge_two_non_empty_frames(self) -> None:
        """Merge two GeoDataFrames into one."""
        frame1 = gpd.GeoDataFrame(
            [{"name": "Marker 1", "geometry": Point(1.0, 44.0)}],
            geometry="geometry",
            crs="EPSG:4326",
        )
        frame2 = gpd.GeoDataFrame(
            [{"name": "Marker 2", "geometry": Point(2.0, 45.0)}],
            geometry="geometry",
            crs="EPSG:4326",
        )

        result = merge_marker_frames(frame1, frame2)

        assert len(result) == 2
        assert result.loc[0, "name"] == "Marker 1"
        assert result.loc[1, "name"] == "Marker 2"

    def test_merge_handles_empty_frames(self) -> None:
        """Merge skips empty frames."""
        frame1 = gpd.GeoDataFrame(
            [{"name": "Marker 1", "geometry": Point(1.0, 44.0)}],
            geometry="geometry",
            crs="EPSG:4326",
        )
        empty_frame = gpd.GeoDataFrame(
            {"name": [], "geometry": []},
            geometry="geometry",
            crs="EPSG:4326",
        )
        frame2 = gpd.GeoDataFrame(
            [{"name": "Marker 2", "geometry": Point(2.0, 45.0)}],
            geometry="geometry",
            crs="EPSG:4326",
        )

        result = merge_marker_frames(frame1, empty_frame, frame2)

        assert len(result) == 2

    def test_merge_all_empty_returns_empty_frame(self) -> None:
        """Merge of all empty frames returns empty GeoDataFrame."""
        empty1 = gpd.GeoDataFrame(
            {"name": [], "geometry": []},
            geometry="geometry",
            crs="EPSG:4326",
        )
        empty2 = gpd.GeoDataFrame(
            {"name": [], "geometry": []},
            geometry="geometry",
            crs="EPSG:4326",
        )

        result = merge_marker_frames(empty1, empty2)

        assert len(result) == 0
        assert result.crs == "EPSG:4326"

    def test_merge_resets_index(self) -> None:
        """Merge resets index to sequential."""
        frame1 = gpd.GeoDataFrame(
            [
                {"name": "A", "geometry": Point(1.0, 44.0)},
                {"name": "B", "geometry": Point(2.0, 45.0)},
            ],
            geometry="geometry",
            crs="EPSG:4326",
        )
        frame2 = gpd.GeoDataFrame(
            [{"name": "C", "geometry": Point(3.0, 46.0)}],
            geometry="geometry",
            crs="EPSG:4326",
            index=[10],
        )

        result = merge_marker_frames(frame1, frame2)

        assert list(result.index) == [0, 1, 2]

    def test_merge_no_args_returns_empty_frame(self) -> None:
        """Merge with no arguments returns empty GeoDataFrame."""
        result = merge_marker_frames()

        assert len(result) == 0
        assert result.crs == "EPSG:4326"


class TestExportMarkersToGpx:
    """Tests for export_markers_to_gpx function."""

    def test_export_writes_gpx_file(self, tmp_path: Path) -> None:
        """Export writes a GPX file."""
        frame = gpd.GeoDataFrame(
            [{"name": "Marker 1", "geometry": Point(1.0, 44.0)}],
            geometry="geometry",
            crs="EPSG:4326",
        )
        output_path = tmp_path / "markers.gpx"

        result = export_markers_to_gpx(frame, output_path)

        assert result == output_path
        assert output_path.exists()

    def test_export_file_can_be_read_back(self, tmp_path: Path) -> None:
        """Exported GPX file can be read back with read_gpx_waypoints."""
        frame = gpd.GeoDataFrame(
            [
                {"name": "Doline 1", "geometry": Point(5.1, 43.2)},
                {"name": "Doline 2", "geometry": Point(5.2, 43.3)},
            ],
            geometry="geometry",
            crs="EPSG:4326",
        )
        output_path = tmp_path / "test.gpx"

        export_markers_to_gpx(frame, output_path)
        loaded = read_gpx_waypoints(output_path)

        assert loaded.crs == "EPSG:4326"
        assert loaded["name"].to_list() == ["Doline 1", "Doline 2"]
        assert abs(loaded.geometry.iloc[0].x - 5.1) < 1e-6
        assert abs(loaded.geometry.iloc[0].y - 43.2) < 1e-6

    def test_export_creates_parent_directory(self, tmp_path: Path) -> None:
        """Export creates parent directories as needed."""
        frame = gpd.GeoDataFrame(
            [{"name": "Test", "geometry": Point(1.0, 44.0)}],
            geometry="geometry",
            crs="EPSG:4326",
        )
        output_path = tmp_path / "deep" / "nested" / "markers.gpx"

        export_markers_to_gpx(frame, output_path)

        assert output_path.exists()
        assert output_path.parent.exists()


class TestExportMarkersToKml:
    """Tests for export_markers_to_kml function."""

    def test_export_writes_kml_file(self, tmp_path: Path) -> None:
        """Export writes a KML file."""
        frame = gpd.GeoDataFrame(
            [{"name": "Marker 1", "geometry": Point(1.0, 44.0)}],
            geometry="geometry",
            crs="EPSG:4326",
        )
        output_path = tmp_path / "markers.kml"

        result = export_markers_to_kml(frame, output_path)

        assert result == output_path
        assert output_path.exists()

    def test_export_file_can_be_read_back(self, tmp_path: Path) -> None:
        """Exported KML file can be read back with read_kml_points."""
        frame = gpd.GeoDataFrame(
            [
                {"name": "Cave 1", "geometry": Point(5.1, 43.2)},
                {"name": "Cave 2", "geometry": Point(5.2, 43.3)},
            ],
            geometry="geometry",
            crs="EPSG:4326",
        )
        output_path = tmp_path / "test.kml"

        export_markers_to_kml(frame, output_path)
        loaded = read_kml_points(output_path)

        assert loaded.crs == "EPSG:4326"
        assert loaded["name"].to_list() == ["Cave 1", "Cave 2"]
        assert abs(loaded.geometry.iloc[0].x - 5.1) < 1e-6
        assert abs(loaded.geometry.iloc[0].y - 43.2) < 1e-6

    def test_export_creates_parent_directory(self, tmp_path: Path) -> None:
        """Export creates parent directories as needed."""
        frame = gpd.GeoDataFrame(
            [{"name": "Test", "geometry": Point(1.0, 44.0)}],
            geometry="geometry",
            crs="EPSG:4326",
        )
        output_path = tmp_path / "deep" / "nested" / "markers.kml"

        export_markers_to_kml(frame, output_path)

        assert output_path.exists()
        assert output_path.parent.exists()


class TestPoiRecordsToGeoDataFrame:
    """Tests for poi_records_to_geodataframe function."""

    def test_converts_records_to_frame(self) -> None:
        """Convert a list of POI records to GeoDataFrame."""

        class PoiRecord:
            def __init__(
                self,
                name: str,
                lat: float,
                lon: float,
                description: str,
                source: str,
            ) -> None:
                self.name = name
                self.lat = lat
                self.lon = lon
                self.description = description
                self.source = source

        records = [
            PoiRecord("Cave 1", 44.1, 1.2, "Entrance", "manual"),
            PoiRecord("Cave 2", 44.2, 1.3, "Chamber", "brgm_cavites"),
        ]

        frame = poi_records_to_geodataframe(records)

        assert len(frame) == 2
        assert frame.crs == "EPSG:4326"
        assert frame.loc[0, "name"] == "Cave 1"
        assert frame.loc[0, "source"] == "manual"
        assert frame.loc[1, "name"] == "Cave 2"
        assert frame.loc[1, "source"] == "brgm_cavites"

    def test_correct_geometry(self) -> None:
        """Geometry is correct Point coordinates."""

        class PoiRecord:
            def __init__(
                self,
                name: str,
                lat: float,
                lon: float,
                description: str,
                source: str,
            ) -> None:
                self.name = name
                self.lat = lat
                self.lon = lon
                self.description = description
                self.source = source

        records = [PoiRecord("Test", 43.5, 5.2, "Test POI", "manual")]

        frame = poi_records_to_geodataframe(records)

        geometry = frame.geometry.iloc[0]
        assert isinstance(geometry, Point)
        assert abs(geometry.x - 5.2) < 1e-6
        assert abs(geometry.y - 43.5) < 1e-6

    def test_all_required_columns_present(self) -> None:
        """Frame has name, description, source columns."""

        class PoiRecord:
            def __init__(
                self,
                name: str,
                lat: float,
                lon: float,
                description: str,
                source: str,
            ) -> None:
                self.name = name
                self.lat = lat
                self.lon = lon
                self.description = description
                self.source = source

        records = [PoiRecord("Test", 44.0, 1.0, "Test", "manual")]

        frame = poi_records_to_geodataframe(records)

        assert "name" in frame.columns
        assert "description" in frame.columns
        assert "source" in frame.columns
        assert "geometry" in frame.columns

    def test_empty_record_list(self) -> None:
        """Empty record list returns empty GeoDataFrame."""
        frame = poi_records_to_geodataframe([])

        assert len(frame) == 0
        assert frame.crs == "EPSG:4326"


class TestManualMarkerDataclass:
    """Tests for ManualMarker dataclass."""

    def test_marker_is_frozen(self) -> None:
        """ManualMarker is immutable (frozen)."""
        marker = ManualMarker(name="Test", lat=44.0, lon=1.0)

        with pytest.raises(AttributeError):
            marker.name = "Changed"  # type: ignore[misc]

    def test_marker_equality(self) -> None:
        """Two identical markers are equal."""
        marker1 = ManualMarker(name="Test", lat=44.0, lon=1.0)
        marker2 = ManualMarker(name="Test", lat=44.0, lon=1.0)

        assert marker1 == marker2

    def test_marker_inequality(self) -> None:
        """Different markers are not equal."""
        marker1 = ManualMarker(name="Test1", lat=44.0, lon=1.0)
        marker2 = ManualMarker(name="Test2", lat=44.0, lon=1.0)

        assert marker1 != marker2
