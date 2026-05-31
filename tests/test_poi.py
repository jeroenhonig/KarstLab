"""Tests for POI data fetching from BRGM Cavités and Spélébase."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from karstlab.data.poi import (
    FRENCH_DEPARTMENTS,
    PoiRecord,
    fetch_brgm_cavites,
    fetch_poi,
    fetch_spelebase,
)
from karstlab.data.schemas import PoiType


class TestPoiRecord:
    """Test PoiRecord immutability and structure."""

    def test_poi_record_is_frozen(self) -> None:
        record = PoiRecord(name="Test", lat=45.0, lon=2.0, source="brgm_cavites")
        with pytest.raises(AttributeError):
            record.name = "Changed"  # type: ignore

    def test_poi_record_with_description(self) -> None:
        record = PoiRecord(
            name="Grotte",
            lat=45.0,
            lon=2.0,
            source="brgm_cavites",
            description="Karst cave",
            external_id="12345",
        )
        assert record.description == "Karst cave"
        assert record.external_id == "12345"

    def test_poi_record_defaults(self) -> None:
        record = PoiRecord(name="Test", lat=45.0, lon=2.0, source="spelebase")
        assert record.description == ""
        assert record.external_id == ""
        assert record.poi_type == PoiType.UNKNOWN


class TestFrenchDepartments:
    """Test French department codes."""

    def test_has_common_departments(self) -> None:
        assert "06" in FRENCH_DEPARTMENTS
        assert "34" in FRENCH_DEPARTMENTS
        assert "75" in FRENCH_DEPARTMENTS

    def test_has_corsica_departments(self) -> None:
        assert "2A" in FRENCH_DEPARTMENTS
        assert "2B" in FRENCH_DEPARTMENTS

    def test_has_overseas_departments(self) -> None:
        assert "971" in FRENCH_DEPARTMENTS
        assert "974" in FRENCH_DEPARTMENTS


class TestFetchBrgmCavitesNetworkFailure:
    """Test BRGM Cavités network failure behavior."""

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_returns_empty_list_on_network_error(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = Exception("Connection refused")
        result = fetch_brgm_cavites("06")
        assert result == []

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_returns_empty_list_on_timeout(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = TimeoutError("Timeout")
        result = fetch_brgm_cavites("06", timeout=5.0)
        assert result == []

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_returns_empty_list_on_invalid_json(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = b"not json"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        result = fetch_brgm_cavites("06")
        assert result == []

    def test_invalid_department_returns_empty_list(self) -> None:
        result = fetch_brgm_cavites("99")
        assert result == []

    def test_returns_empty_list_on_network_error_no_cache(self, tmp_path: Path) -> None:
        with patch("karstlab.data.poi.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("Connection refused")
            result = fetch_brgm_cavites("06", cache_dir=tmp_path)
            assert result == []


class TestFetchBrgmCavitesCache:
    """Test BRGM Cavités cache behavior."""

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_writes_cache_after_successful_fetch(
        self, mock_urlopen: MagicMock, tmp_path: Path
    ) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "data": [
                    {
                        "nom_cavite": "Grotte 1",
                        "wgs84_latitude": 45.0,
                        "wgs84_longitude": 2.0,
                        "id_cavite": 123,
                        "type_cavite": "Natural",
                        "commune": "Test",
                    }
                ]
            }
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = fetch_brgm_cavites("06", cache_dir=tmp_path)

        assert len(result) == 1
        assert result[0].name == "Grotte 1"

        # Verify cache was written
        cache_file = tmp_path / "poi" / "brgm_cavites_06.json"
        assert cache_file.exists()
        cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
        assert cached_data["department"] == "06"
        assert len(cached_data["records"]) == 1

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_returns_cached_data_on_network_failure(
        self, mock_urlopen: MagicMock, tmp_path: Path
    ) -> None:
        # First successful fetch to populate cache
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "data": [
                    {
                        "nom_cavite": "Cached Grotte",
                        "wgs84_latitude": 43.0,
                        "wgs84_longitude": 3.0,
                        "id_cavite": 456,
                        "type_cavite": "Karst",
                        "commune": "Cached",
                    }
                ]
            }
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        # First call: successful
        result1 = fetch_brgm_cavites("34", cache_dir=tmp_path)
        assert len(result1) == 1

        # Second call: network fails, but cache should be returned
        mock_urlopen.side_effect = Exception("Connection refused")
        result2 = fetch_brgm_cavites("34", cache_dir=tmp_path)
        assert len(result2) == 1
        assert result2[0].name == "Cached Grotte"

    def test_invalid_cache_file_returns_empty_list(self, tmp_path: Path) -> None:
        cache_file = tmp_path / "poi" / "brgm_cavites_06.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text("not json", encoding="utf-8")

        with patch("karstlab.data.poi.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("Network error")
            result = fetch_brgm_cavites("06", cache_dir=tmp_path)
            assert result == []

    def test_corrupted_cache_records_field_returns_empty_list(self, tmp_path: Path) -> None:
        cache_file = tmp_path / "poi" / "brgm_cavites_06.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(json.dumps({"records": "not a list"}), encoding="utf-8")

        with patch("karstlab.data.poi.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("Network error")
            result = fetch_brgm_cavites("06", cache_dir=tmp_path)
            assert result == []


class TestFetchBrgmCavitesDataParsing:
    """Test BRGM Cavités data parsing."""

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_parses_valid_brgm_response(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "data": [
                    {
                        "nom_cavite": "Grotte du Test",
                        "wgs84_latitude": 45.123,
                        "wgs84_longitude": 2.456,
                        "id_cavite": 789,
                        "type_cavite": "Natural Cave",
                        "commune": "Test City",
                    }
                ]
            }
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = fetch_brgm_cavites("06")

        assert len(result) == 1
        assert result[0].name == "Grotte du Test"
        assert result[0].lat == 45.123
        assert result[0].lon == 2.456
        assert result[0].source == "brgm_cavites"
        assert result[0].external_id == "789"
        assert "Natural Cave" in result[0].description
        assert "Test City" in result[0].description

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_skips_records_missing_coordinates(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "data": [
                    {
                        "nom_cavite": "Good Cave",
                        "wgs84_latitude": 45.0,
                        "wgs84_longitude": 2.0,
                        "id_cavite": 1,
                    },
                    {
                        "nom_cavite": "Bad Cave",
                        "wgs84_latitude": None,
                        "wgs84_longitude": 2.0,
                        "id_cavite": 2,
                    },
                ]
            }
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = fetch_brgm_cavites("06")

        assert len(result) == 1
        assert result[0].name == "Good Cave"

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_skips_records_missing_name(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "data": [
                    {
                        "nom_cavite": "Good Cave",
                        "wgs84_latitude": 45.0,
                        "wgs84_longitude": 2.0,
                        "id_cavite": 1,
                    },
                    {
                        "nom_cavite": "",
                        "wgs84_latitude": 45.0,
                        "wgs84_longitude": 2.0,
                        "id_cavite": 2,
                    },
                ]
            }
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = fetch_brgm_cavites("06")

        assert len(result) == 1
        assert result[0].name == "Good Cave"

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_handles_malformed_records_gracefully(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "data": [
                    {
                        "nom_cavite": "Good Cave",
                        "wgs84_latitude": 45.0,
                        "wgs84_longitude": 2.0,
                        "id_cavite": 1,
                    },
                    {
                        "nom_cavite": "Bad Cave",
                        "wgs84_latitude": "not a number",
                        "wgs84_longitude": 2.0,
                        "id_cavite": 2,
                    },
                ]
            }
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = fetch_brgm_cavites("06")

        assert len(result) == 1
        assert result[0].name == "Good Cave"

    @pytest.mark.parametrize(
        ("type_cavite", "expected"),
        [
            ("Perte", PoiType.PERTE),
            ("Résurgence", PoiType.RESURGENCE),
            ("not observed", PoiType.UNKNOWN),
        ],
    )
    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_maps_brgm_type_cavite_to_poi_type(
        self,
        mock_urlopen: MagicMock,
        type_cavite: str,
        expected: PoiType,
    ) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "data": [
                    {
                        "nom_cavite": "Typed Cave",
                        "wgs84_latitude": 45.0,
                        "wgs84_longitude": 2.0,
                        "id_cavite": 1,
                        "type_cavite": type_cavite,
                    }
                ]
            }
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = fetch_brgm_cavites("06")

        assert result[0].poi_type == expected


class TestFetchSpelebase:
    """Test Spélébase stub implementation."""

    def test_returns_empty_list(self) -> None:
        result = fetch_spelebase("06")
        assert result == []

    def test_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("WARNING"):
            fetch_spelebase("34")
        assert "Spélébase integration not yet available" in caplog.text
        assert "34" in caplog.text

    def test_invalid_department_returns_empty_list(self) -> None:
        result = fetch_spelebase("99")
        assert result == []

    def test_respects_timeout_parameter(self) -> None:
        # Stub doesn't use timeout, but parameter should be accepted
        result = fetch_spelebase("06", timeout=5.0)
        assert result == []

    def test_respects_cache_dir_parameter(self, tmp_path: Path) -> None:
        # Stub doesn't use cache, but parameter should be accepted
        result = fetch_spelebase("06", cache_dir=tmp_path)
        assert result == []


class TestFetchPoi:
    """Test fetch_poi multi-source integration."""

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_combines_multiple_sources(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "data": [
                    {
                        "nom_cavite": "BRGM Cave",
                        "wgs84_latitude": 45.0,
                        "wgs84_longitude": 2.0,
                        "id_cavite": 1,
                    }
                ]
            }
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = fetch_poi("06", ["brgm_cavites", "spelebase"])

        # Should have BRGM result only (Spélébase is stub)
        assert len(result) == 1
        assert result[0].source == "brgm_cavites"

    def test_invalid_department_returns_empty_list(self) -> None:
        result = fetch_poi("99", ["brgm_cavites", "spelebase"])
        assert result == []

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_skips_unknown_sources(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "data": [
                    {
                        "nom_cavite": "Cave",
                        "wgs84_latitude": 45.0,
                        "wgs84_longitude": 2.0,
                        "id_cavite": 1,
                    }
                ]
            }
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = fetch_poi("06", ["brgm_cavites", "unknown_source"])

        # Should fetch from brgm_cavites, skip unknown_source
        assert len(result) == 1

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_empty_sources_list_returns_empty_result(self, mock_urlopen: MagicMock) -> None:
        result = fetch_poi("06", [])
        assert result == []
        # urlopen should not be called
        mock_urlopen.assert_not_called()

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_respects_timeout_for_all_sources(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"data": []}).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        fetch_poi("06", ["brgm_cavites"], timeout=7.5)

        # Verify timeout was passed
        call_args = mock_urlopen.call_args
        assert call_args is not None
        assert call_args[1]["timeout"] == 7.5


class TestCachePersistence:
    """Test cache file format and persistence."""

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_cache_has_correct_structure(self, mock_urlopen: MagicMock, tmp_path: Path) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "data": [
                    {
                        "nom_cavite": "Test Cave",
                        "wgs84_latitude": 45.0,
                        "wgs84_longitude": 2.0,
                        "id_cavite": 123,
                        "type_cavite": "Test Type",
                        "commune": "Test Commune",
                    }
                ]
            }
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        fetch_brgm_cavites("06", cache_dir=tmp_path)

        cache_file = tmp_path / "poi" / "brgm_cavites_06.json"
        cache_data = json.loads(cache_file.read_text(encoding="utf-8"))

        assert "fetched_at" in cache_data
        assert "department" in cache_data
        assert cache_data["department"] == "06"
        assert "records" in cache_data
        assert isinstance(cache_data["records"], list)
        assert cache_data["records"][0]["name"] == "Test Cave"

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_cache_atomic_write(self, mock_urlopen: MagicMock, tmp_path: Path) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "data": [
                    {
                        "nom_cavite": "Cave",
                        "wgs84_latitude": 45.0,
                        "wgs84_longitude": 2.0,
                        "id_cavite": 1,
                    }
                ]
            }
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        fetch_brgm_cavites("06", cache_dir=tmp_path)

        cache_file = tmp_path / "poi" / "brgm_cavites_06.json"
        tmp_file = cache_file.with_suffix(".json.tmp")

        # Final cache file should exist
        assert cache_file.exists()
        # Temporary file should not exist
        assert not tmp_file.exists()

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_cache_round_trip_preserves_poi_type(
        self, mock_urlopen: MagicMock, tmp_path: Path
    ) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "data": [
                    {
                        "nom_cavite": "Perte Cache",
                        "wgs84_latitude": 45.0,
                        "wgs84_longitude": 2.0,
                        "id_cavite": 1,
                        "type_cavite": "Perte",
                    }
                ]
            }
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        fetch_brgm_cavites("06", cache_dir=tmp_path)

        mock_urlopen.side_effect = Exception("Network error")
        result = fetch_brgm_cavites("06", cache_dir=tmp_path)

        assert result[0].poi_type == PoiType.PERTE

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_cache_without_poi_type_loads_as_unknown(
        self, mock_urlopen: MagicMock, tmp_path: Path
    ) -> None:
        cache_file = tmp_path / "poi" / "brgm_cavites_06.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(
            json.dumps(
                {
                    "records": [
                        {
                            "name": "Old Cache",
                            "lat": 45.0,
                            "lon": 2.0,
                            "source": "brgm_cavites",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        mock_urlopen.side_effect = Exception("Network error")

        result = fetch_brgm_cavites("06", cache_dir=tmp_path)

        assert result[0].poi_type == PoiType.UNKNOWN


class TestNetworkTimeout:
    """Test network timeout behavior."""

    @patch("karstlab.data.poi.urllib.request.urlopen")
    def test_custom_timeout_is_used(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"data": []}).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        fetch_brgm_cavites("06", timeout=3.5)

        # Verify timeout was passed to urlopen
        call_args = mock_urlopen.call_args
        assert call_args is not None
        assert call_args[1]["timeout"] == 3.5
