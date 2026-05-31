"""Load and validate bundled or external KarstLab land profiles."""

from __future__ import annotations

import json
from collections.abc import Sequence
from importlib.resources import files
from pathlib import Path

import rasterio
from pydantic import ValidationError
from pyproj import CRS, Transformer

from karstlab.data.schemas import LandProfile

REGIONS_PACKAGE = "karstlab.resources.regions"
GENERIC_PROFILE_ID = "generic"

# Filename CRS hints for tiles that ship without an embedded CRS (e.g. RGE ALTI
# ASC has no .prj). Substring match on the upper-cased filename.
_FILENAME_CRS_HINTS: dict[str, int] = {
    "LAMB93": 2154,
    "LAMBERT93": 2154,
    "RGF93": 2154,
    "LAMBERT72": 31370,
    "LAMB72": 31370,
    "BD72": 31370,
    "AMERSFOORT": 28992,
    "RIJKSDRIEHOEK": 28992,
    "RDNEW": 28992,
    "UTM31": 32631,
    "UTM32": 32632,
}


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


def detect_land_profile(dem_paths: Sequence[Path]) -> str | None:
    """Best-effort region detection from DEM tiles.

    1. Match the tile CRS (embedded, else inferred from the filename) against a
       region's national ``default_crs`` (EPSG:2154→fr, 31370→be, 28992→nl).
    2. Otherwise reproject the tile centroid to WGS84 and pick the smallest
       region ``bbox_wgs84`` that contains it (handles shared UTM CRS).

    Returns the region id, or None when nothing matches (caller keeps the
    current selection).
    """
    if not dem_paths:
        return None
    tile = Path(dem_paths[0])
    crs = _tile_crs(tile)
    profiles = load_all_land_profiles()

    if crs is not None:
        epsg = CRS.from_user_input(crs).to_epsg()
        if epsg is not None:
            for profile_id, profile in profiles.items():
                if profile.default_crs == f"EPSG:{epsg}":
                    return profile_id

    centroid = _tile_centroid_wgs84(tile, crs)
    if centroid is not None:
        lon, lat = centroid
        matches = [
            (profile_id, profile.bbox_wgs84)
            for profile_id, profile in profiles.items()
            if profile.bbox_wgs84 is not None and _inside_bbox(lon, lat, profile.bbox_wgs84)
        ]
        if matches:
            matches.sort(key=lambda item: _bbox_area(item[1]))
            return matches[0][0]
    return None


def _tile_crs(path: Path) -> str | None:
    try:
        with rasterio.open(path) as dataset:
            if dataset.crs is not None:
                return str(dataset.crs.to_string())
    except Exception:  # noqa: BLE001 - fall back to filename inference
        pass
    return _filename_crs_hint(path.name)


def _filename_crs_hint(name: str) -> str | None:
    upper = name.upper()
    for token, epsg in _FILENAME_CRS_HINTS.items():
        if token in upper:
            return f"EPSG:{epsg}"
    return None


def _tile_centroid_wgs84(path: Path, crs: str | None) -> tuple[float, float] | None:
    if crs is None:
        return None
    try:
        with rasterio.open(path) as dataset:
            bounds = dataset.bounds
        center_x = (bounds.left + bounds.right) / 2.0
        center_y = (bounds.bottom + bounds.top) / 2.0
        transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(center_x, center_y)
        return float(lon), float(lat)
    except Exception:  # noqa: BLE001 - detection is best-effort
        return None


def _inside_bbox(lon: float, lat: float, bbox: tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    min_lon, min_lat, max_lon, max_lat = bbox
    return abs(max_lon - min_lon) * abs(max_lat - min_lat)
