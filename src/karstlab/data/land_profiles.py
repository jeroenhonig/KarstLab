"""Load and validate bundled or external KarstLab land profiles."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from pydantic import ValidationError

from karstlab.data.schemas import LandProfile

REGIONS_PACKAGE = "karstlab.resources.regions"
GENERIC_PROFILE_ID = "generic"


class LandProfileError(ValueError):
    """Raised when a land profile cannot be loaded or validated."""


def list_land_profile_ids() -> list[str]:
    region_files = files(REGIONS_PACKAGE).iterdir()
    return sorted(
        path.name.removesuffix(".json") for path in region_files if path.name.endswith(".json")
    )


def load_land_profile(profile_id: str, *, fallback: bool = True) -> LandProfile:
    try:
        resource = files(REGIONS_PACKAGE).joinpath(f"{profile_id}.json")
        if not resource.is_file():
            raise FileNotFoundError(profile_id)
        payload = json.loads(resource.read_text(encoding="utf-8"))
        return LandProfile.model_validate(payload)
    except (FileNotFoundError, json.JSONDecodeError, ValidationError) as exc:
        if fallback and profile_id != GENERIC_PROFILE_ID:
            return load_land_profile(GENERIC_PROFILE_ID, fallback=False)
        raise LandProfileError(f"Could not load land profile '{profile_id}'") from exc


def load_land_profile_from_path(path: Path, *, fallback: bool = True) -> LandProfile:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return LandProfile.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        if fallback:
            return load_land_profile(GENERIC_PROFILE_ID, fallback=False)
        raise LandProfileError(f"Could not load land profile from {path}") from exc


def load_all_land_profiles() -> dict[str, LandProfile]:
    return {
        profile_id: load_land_profile(profile_id, fallback=False)
        for profile_id in list_land_profile_ids()
    }
