from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import pytest
from pydantic import BaseModel

from karstlab.data.land_profiles import (
    GENERIC_PROFILE_ID,
    LandProfileError,
    list_land_profile_ids,
    load_all_land_profiles,
    load_land_profile,
    load_land_profile_from_path,
)
from karstlab.data.schemas import LandProfile, ProjectFile, UserSettings


def test_bundled_land_profile_ids_are_available() -> None:
    assert list_land_profile_ids() == ["be", "fr", "generic", "nl"]


def test_all_bundled_land_profiles_validate() -> None:
    profiles = load_all_land_profiles()

    assert set(profiles) == {"be", "fr", "generic", "nl"}
    for profile_id, profile in profiles.items():
        assert profile.id == profile_id
        assert profile.default_crs in profile.common_crs
        assert profile.map_layers.base


def test_french_profile_preserves_aris_compatible_defaults() -> None:
    profile = load_land_profile("fr")

    assert profile.default_crs == "EPSG:2154"
    assert profile.analysis_defaults.contour_interval_m == 5.0
    assert profile.analysis_defaults.doline_min_depth_m == 0.25
    assert profile.analysis_defaults.doline_max_depth_m == 40.0
    assert profile.analysis_defaults.doline_min_area_m2 == 1.0
    assert profile.analysis_defaults.doline_max_area_m2 == 60000.0
    assert {source.type for source in profile.poi_sources} == {
        "brgm_cavites",
        "spelebase",
        "geojson",
    }


def test_missing_profile_falls_back_to_generic() -> None:
    profile = load_land_profile("missing-profile")

    assert profile.id == GENERIC_PROFILE_ID


def test_missing_profile_can_raise_without_fallback() -> None:
    with pytest.raises(LandProfileError):
        load_land_profile("missing-profile", fallback=False)


def test_external_invalid_profile_falls_back_to_generic(tmp_path: Path) -> None:
    invalid_profile = tmp_path / "invalid.json"
    invalid_profile.write_text('{"id": "broken"}', encoding="utf-8")

    profile = load_land_profile_from_path(invalid_profile)

    assert profile.id == GENERIC_PROFILE_ID


def test_external_invalid_profile_can_raise_without_fallback(tmp_path: Path) -> None:
    invalid_profile = tmp_path / "invalid.json"
    invalid_profile.write_text("{not-json", encoding="utf-8")

    with pytest.raises(LandProfileError):
        load_land_profile_from_path(invalid_profile, fallback=False)


def test_json_schema_resources_are_generated() -> None:
    schema_dir = files("karstlab.resources.schemas")

    expected: dict[str, type[BaseModel]] = {
        "land_profile.schema.json": LandProfile,
        "project.schema.json": ProjectFile,
        "user_settings.schema.json": UserSettings,
    }

    for filename, model in expected.items():
        schema = schema_dir.joinpath(filename)
        assert schema.is_file()
        assert model.model_json_schema()["title"] in schema.read_text(encoding="utf-8")
