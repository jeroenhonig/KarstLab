"""POI (Point of Interest) data fetching from BRGM Cavités and Spélébase sources."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# French department codes to names
FRENCH_DEPARTMENTS: dict[str, str] = {
    "01": "Ain",
    "02": "Aisne",
    "03": "Allier",
    "04": "Alpes-de-Haute-Provence",
    "05": "Hautes-Alpes",
    "06": "Alpes-Maritimes",
    "07": "Ardèche",
    "08": "Ardennes",
    "09": "Ariège",
    "10": "Aube",
    "11": "Aude",
    "12": "Aveyron",
    "13": "Bouches-du-Rhône",
    "14": "Calvados",
    "15": "Cantal",
    "16": "Charente",
    "17": "Charente-Maritime",
    "18": "Cher",
    "19": "Corrèze",
    "21": "Côte-d'Or",
    "22": "Côtes-d'Armor",
    "23": "Creuse",
    "24": "Dordogne",
    "25": "Doubs",
    "26": "Drôme",
    "27": "Eure",
    "28": "Eure-et-Loir",
    "29": "Finistère",
    "2A": "Corse-du-Sud",
    "2B": "Haute-Corse",
    "30": "Gard",
    "31": "Haute-Garonne",
    "32": "Gers",
    "33": "Gironde",
    "34": "Hérault",
    "35": "Ille-et-Vilaine",
    "36": "Indre",
    "37": "Indre-et-Loire",
    "38": "Isère",
    "39": "Jura",
    "40": "Landes",
    "41": "Loir-et-Cher",
    "42": "Loire",
    "43": "Haute-Loire",
    "44": "Loire-Atlantique",
    "45": "Loiret",
    "46": "Lot",
    "47": "Lot-et-Garonne",
    "48": "Lozère",
    "49": "Maine-et-Loire",
    "50": "Manche",
    "51": "Marne",
    "52": "Haute-Marne",
    "53": "Mayenne",
    "54": "Meurthe-et-Moselle",
    "55": "Meuse",
    "56": "Morbihan",
    "57": "Moselle",
    "58": "Nièvre",
    "59": "Nord",
    "60": "Oise",
    "61": "Orne",
    "62": "Pas-de-Calais",
    "63": "Puy-de-Dôme",
    "64": "Pyrénées-Atlantiques",
    "65": "Hautes-Pyrénées",
    "66": "Pyrénées-Orientales",
    "67": "Bas-Rhin",
    "68": "Haut-Rhin",
    "69": "Rhône",
    "70": "Haute-Saône",
    "71": "Saône-et-Loire",
    "72": "Sarthe",
    "73": "Savoie",
    "74": "Haute-Savoie",
    "75": "Paris",
    "76": "Seine-Maritime",
    "77": "Seine-et-Marne",
    "78": "Yvelines",
    "79": "Deux-Sèvres",
    "80": "Somme",
    "81": "Tarn",
    "82": "Tarn-et-Garonne",
    "83": "Var",
    "84": "Vaucluse",
    "85": "Vendée",
    "86": "Vienne",
    "87": "Haute-Vienne",
    "88": "Vosges",
    "89": "Yonne",
    "90": "Territoire de Belfort",
    "91": "Essonne",
    "92": "Hauts-de-Seine",
    "93": "Seine-Saint-Denis",
    "94": "Val-de-Marne",
    "95": "Val-d'Oise",
    "971": "Guadeloupe",
    "972": "Martinique",
    "973": "Guyane",
    "974": "Réunion",
    "976": "Mayotte",
}


@dataclass(frozen=True)
class PoiRecord:
    """Immutable POI record with standardized fields."""

    name: str
    lat: float
    lon: float
    source: str
    description: str = ""
    external_id: str = ""


def _validate_department(department: str) -> bool:
    """Check if department code is valid."""
    return department in FRENCH_DEPARTMENTS


def _get_cache_path(cache_dir: Path, source: str, department: str) -> Path:
    """Build cache file path for (source, department) tuple."""
    poi_cache_dir = cache_dir / "poi"
    poi_cache_dir.mkdir(parents=True, exist_ok=True)
    return poi_cache_dir / f"{source}_{department}.json"


def _read_cache(cache_path: Path) -> list[PoiRecord] | None:
    """Load cached POI records from file. Returns None if not found or invalid."""
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        records = data.get("records", [])
        return [PoiRecord(**rec) for rec in records]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _write_cache(cache_path: Path, records: list[PoiRecord], department: str) -> None:
    """Write POI records to cache file with timestamp."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "department": department,
        "records": [
            {
                "name": rec.name,
                "lat": rec.lat,
                "lon": rec.lon,
                "source": rec.source,
                "description": rec.description,
                "external_id": rec.external_id,
            }
            for rec in records
        ],
    }
    tmp = cache_path.with_suffix(f"{cache_path.suffix}.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(cache_path)


def _fetch_brgm_cavites_raw(
    department: str,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    """Fetch BRGM Cavités data from API. Returns empty list on any network error."""
    url = f"https://georisques.gouv.fr/api/v1/cavites?dep={department}&page=1&page_size=100"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            result = data.get("data", [])
            if isinstance(result, list):
                return result
            return []
    except Exception:  # Catch all network-related errors
        return []


def fetch_brgm_cavites(
    department: str,
    *,
    timeout: float = 10.0,
    cache_dir: Path | None = None,
) -> list[PoiRecord]:
    """
    Fetch BRGM Cavités (cave) data for a French department.

    Returns cached data if network fails and cache exists.
    Returns empty list on network failure with no cache.
    Never raises on network errors.

    Args:
        department: French department code (e.g. "06", "34")
        timeout: Network timeout in seconds (default 10.0)
        cache_dir: Cache directory. If None, no caching is performed.

    Returns:
        List of POI records, possibly empty.
    """
    if not _validate_department(department):
        return []

    cache_path = _get_cache_path(cache_dir, "brgm_cavites", department) if cache_dir else None

    # Try to fetch from network
    raw_records = _fetch_brgm_cavites_raw(department, timeout=timeout)
    if raw_records:
        records = []
        for item in raw_records:
            try:
                lat = item.get("wgs84_latitude")
                lon = item.get("wgs84_longitude")
                if lat is None or lon is None:
                    continue
                name = item.get("nom_cavite", "")
                if not name:
                    continue

                # Build description from type and commune
                desc_parts = []
                if item.get("type_cavite"):
                    desc_parts.append(item["type_cavite"])
                if item.get("commune"):
                    desc_parts.append(item["commune"])
                description = ", ".join(desc_parts)

                record = PoiRecord(
                    name=name,
                    lat=float(lat),
                    lon=float(lon),
                    source="brgm_cavites",
                    description=description,
                    external_id=str(item.get("id_cavite", "")),
                )
                records.append(record)
            except (KeyError, TypeError, ValueError):
                continue

        # Write to cache if available
        if cache_path:
            _write_cache(cache_path, records, department)
        return records

    # Network fetch failed; try cache fallback
    if cache_path:
        cached = _read_cache(cache_path)
        if cached is not None:
            return cached

    return []


def fetch_spelebase(
    department: str,
    *,
    timeout: float = 10.0,
    cache_dir: Path | None = None,
) -> list[PoiRecord]:
    """
    Fetch Spélébase (cave survey) data for a French department.

    Currently a stub: Spélébase does not have a public REST API.
    Returns empty list and logs a warning.
    Architecture is in place for future implementation.

    Args:
        department: French department code (e.g. "06", "34")
        timeout: Network timeout in seconds (default 10.0)
        cache_dir: Cache directory (unused for now)

    Returns:
        Empty list (future: Spélébase records when API is available)
    """
    if not _validate_department(department):
        return []

    logger.warning(
        "Spélébase integration not yet available (no public API). "
        "Department: %s",
        department,
    )
    return []


def fetch_poi(
    department: str,
    sources: list[str],
    *,
    timeout: float = 10.0,
    cache_dir: Path | None = None,
) -> list[PoiRecord]:
    """
    Fetch POI from multiple sources and combine results.

    Args:
        department: French department code (e.g. "06", "34")
        sources: List of source names ("brgm_cavites", "spelebase")
        timeout: Network timeout in seconds (default 10.0)
        cache_dir: Cache directory

    Returns:
        Combined list of POI records from all sources
    """
    if not _validate_department(department):
        return []

    records: list[PoiRecord] = []
    for source in sources:
        if source == "brgm_cavites":
            records.extend(
                fetch_brgm_cavites(
                    department,
                    timeout=timeout,
                    cache_dir=cache_dir,
                )
            )
        elif source == "spelebase":
            records.extend(
                fetch_spelebase(
                    department,
                    timeout=timeout,
                    cache_dir=cache_dir,
                )
            )

    return records


__all__ = [
    "PoiRecord",
    "FRENCH_DEPARTMENTS",
    "fetch_brgm_cavites",
    "fetch_spelebase",
    "fetch_poi",
]
