"""Fault-line loading and distance-to-fault analysis for depressions.

Karst conduits commonly develop along faults/fractures, so ranking and filtering
detected depressions by their distance to the nearest mapped fault is a primary
analysis goal. Faults come from the BRGM **BDCharm50** harmonised 1:50 000
geology as the ``*_L_STRUCT_*`` structural-line shapefile (no live WFS — a local
download per department); see ``download_bdcharm_faults``.

Distances are computed in a projected metric CRS (EPSG:2154 by default) so the
result is in metres. Loading never raises (returns ``None`` on any failure) so a
missing/broken fault file can never block the analysis.
"""

from __future__ import annotations

import logging
import math
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
from numpy.typing import NDArray
from shapely.geometry.base import BaseGeometry

from karstlab.data.crs import fold_bearing
from karstlab.data.schemas import DepressionResult

logger = logging.getLogger(__name__)

# Metric CRS for distance computation (Lambert-93; BDCharm50 is native 2154).
_METRIC_CRS = "EPSG:2154"
# BDCharm50 structural-line layer (faults) marker and the per-feature type field.
_FAULT_LAYER_HINT = "L_STRUCT"
_FAULT_TYPE_FIELD = "DESCR"
_BDCHARM_BASE = "http://data.cquest.org/brgm/bd_charm_50/2019"

# Distance-to-fault classes (metres) for map styling / interpretation.
FAULT_DISTANCE_CLASSES: tuple[tuple[str, float], ...] = (
    ("<=50m", 50.0),
    ("<=100m", 100.0),
    ("<=250m", 250.0),
)
# Angular tolerance (degrees) classifying a fault relative to the cave line.
_PARALLEL_MAX_DEG = 30.0
_TRANSVERSE_MIN_DEG = 60.0


def fault_distance_class(distance_m: float | None) -> str:
    """Bucket a distance-to-fault into a coarse class label for styling."""
    if distance_m is None:
        return "none"
    for label, threshold in FAULT_DISTANCE_CLASSES:
        if distance_m <= threshold:
            return label
    return ">250m"


def line_bearing_deg(geometry: BaseGeometry) -> float | None:
    """Folded (0-180°) bearing of a line from its first to last vertex (planar CRS)."""
    coords = _endpoints(geometry)
    if coords is None:
        return None
    (x0, y0), (x1, y1) = coords
    dx, dy = x1 - x0, y1 - y0
    if dx == 0 and dy == 0:
        return None
    bearing = math.degrees(math.atan2(dx, dy))  # 0 = north, clockwise
    return fold_bearing(bearing)


def _endpoints(geometry: BaseGeometry) -> tuple[tuple[float, float], tuple[float, float]] | None:
    geom = geometry
    if geom.geom_type == "MultiLineString":
        geom = max(geom.geoms, key=lambda g: g.length)
    if geom.geom_type != "LineString" or len(geom.coords) < 2:
        return None
    return (geom.coords[0][0], geom.coords[0][1]), (geom.coords[-1][0], geom.coords[-1][1])


def caveline_bearing(lines: gpd.GeoDataFrame) -> float | None:
    """Folded mean bearing of the imported cave line(s), in EPSG:2154."""
    if lines is None or lines.empty:
        return None
    metric = lines.to_crs(_METRIC_CRS)
    bearings = [
        b for geom in metric.geometry if (b := line_bearing_deg(geom)) is not None
    ]
    if not bearings:
        return None
    # Average folded bearings via doubled-angle vectors (handles the 0/180 wrap).
    xs = sum(math.cos(math.radians(2 * b)) for b in bearings)
    ys = sum(math.sin(math.radians(2 * b)) for b in bearings)
    return fold_bearing(math.degrees(math.atan2(ys, xs)) / 2.0)


def fault_orientation_label(fault_bearing: float | None, cave_bearing: float | None) -> str | None:
    """Classify a fault as parallel/oblique/transverse to the cave line."""
    if fault_bearing is None or cave_bearing is None:
        return None
    diff = abs(fold_bearing(fault_bearing) - fold_bearing(cave_bearing))
    diff = min(diff, 180.0 - diff)  # 0-90°
    if diff <= _PARALLEL_MAX_DEG:
        return "parallel"
    if diff >= _TRANSVERSE_MIN_DEG:
        return "transverse"
    return "oblique"


def load_fault_lines(path: Path) -> gpd.GeoDataFrame | None:
    """Load fault lines from a shapefile, a directory, or a BDCharm50 ``.zip``.

    Returns a GeoDataFrame of line geometries in EPSG:2154, or ``None`` if no
    readable fault layer is found. Never raises.
    """
    try:
        source = _resolve_fault_source(path)
        if source is None:
            return None
        frame = gpd.read_file(source)
    except Exception as exc:  # noqa: BLE001 - unreadable source → treat as absent
        logger.warning("Could not read fault lines from %s: %s", path, exc)
        return None

    if frame.empty:
        return None
    lines = frame[frame.geom_type.isin(["LineString", "MultiLineString"])]
    if lines.empty:
        return None
    if lines.crs is None:
        lines = lines.set_crs(_METRIC_CRS, allow_override=True)
    return lines.to_crs(_METRIC_CRS)


def _resolve_fault_source(path: Path) -> str | None:
    """Resolve a user path to a readable OGR source string for the fault layer."""
    path = Path(path)
    if path.suffix.lower() == ".shp":
        return str(path)
    if path.suffix.lower() == ".zip":
        member = _zip_layer_member(path, _FAULT_LAYER_HINT) or _zip_layer_member(path, ".shp")
        return f"zip://{path}!{member}" if member else None
    if path.is_dir():
        matches = sorted(p for p in path.rglob("*.shp") if _FAULT_LAYER_HINT in p.name.upper())
        if not matches:
            matches = sorted(path.rglob("*.shp"))
        return str(matches[0]) if matches else None
    return None


def _zip_layer_member(zip_path: Path, needle: str) -> str | None:
    with zipfile.ZipFile(zip_path) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".shp")]
    upper = needle.upper()
    for name in names:
        if upper in name.upper():
            return name
    return names[0] if names and needle == ".shp" else None


def annotate_fault_distances(
    depressions: list[DepressionResult],
    faults: gpd.GeoDataFrame,
    *,
    cave_bearing: float | None = None,
) -> list[DepressionResult]:
    """Return copies of ``depressions`` with nearest-fault distance/type/orientation.

    Distances are in metres (EPSG:2154). The nearest fault's type (``DESCR``) and
    folded bearing are recorded; when ``cave_bearing`` is given, each depression
    also gets ``fault_orientation`` (parallel/oblique/transverse vs the cave line).
    Depressions are unchanged if there are no faults.
    """
    if not depressions or faults.empty:
        return depressions

    centroids = gpd.GeoSeries(
        gpd.points_from_xy(
            [d.centroid.lon for d in depressions],
            [d.centroid.lat for d in depressions],
        ),
        crs="EPSG:4326",
    ).to_crs(_METRIC_CRS)
    points = gpd.GeoDataFrame(geometry=centroids)

    right = faults[[faults.geometry.name]].copy()
    has_type = _FAULT_TYPE_FIELD in faults.columns
    if has_type:
        right[_FAULT_TYPE_FIELD] = faults[_FAULT_TYPE_FIELD].to_numpy()
    right["_bearing"] = [line_bearing_deg(g) for g in faults.geometry]
    joined = gpd.sjoin_nearest(points, right, how="left", distance_col="_dist_m")
    # sjoin_nearest can emit >1 row per input on ties; keep the first per index.
    joined = joined[~joined.index.duplicated(keep="first")].sort_index()

    distances: NDArray[np.float64] = joined["_dist_m"].to_numpy()
    types = joined[_FAULT_TYPE_FIELD].tolist() if has_type else [None] * len(depressions)
    bearings = joined["_bearing"].tolist()

    annotated: list[DepressionResult] = []
    for depression, distance, fault_type, bearing in zip(
        depressions, distances, types, bearings, strict=True
    ):
        update: dict[str, object] = {"distance_to_fault_m": round(float(distance), 1)}
        if isinstance(fault_type, str) and fault_type:
            update["nearest_fault_type"] = fault_type
        if bearing is not None and not _is_nan(bearing):
            update["nearest_fault_bearing_deg"] = round(float(bearing), 1)
            orientation = fault_orientation_label(float(bearing), cave_bearing)
            if orientation is not None:
                update["fault_orientation"] = orientation
        annotated.append(depression.model_copy(update=update))
    return annotated


def _is_nan(value: object) -> bool:
    return isinstance(value, float) and math.isnan(value)


def faults_to_geojson(faults: gpd.GeoDataFrame) -> dict[str, Any]:
    """Reproject faults to WGS84 GeoJSON with a simplified observed/supposed type.

    Each feature carries ``fault_class`` ("observed"/"supposed"/"other"), the raw
    ``DESCR`` and the folded ``bearing_deg`` for map styling and popups.
    """
    if faults is None or faults.empty:
        return {"type": "FeatureCollection", "features": []}
    wgs84 = faults.to_crs("EPSG:4326")
    features: list[dict[str, object]] = []
    for (_idx, row), geom_metric in zip(wgs84.iterrows(), faults.geometry, strict=True):
        descr = row.get(_FAULT_TYPE_FIELD) if _FAULT_TYPE_FIELD in wgs84.columns else None
        bearing = line_bearing_deg(geom_metric)
        features.append(
            {
                "type": "Feature",
                "geometry": row.geometry.__geo_interface__,
                "properties": {
                    "fault_class": _fault_class(descr),
                    "descr": descr if isinstance(descr, str) else None,
                    "bearing_deg": round(bearing, 1) if bearing is not None else None,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _fault_class(descr: object) -> str:
    text = descr.lower() if isinstance(descr, str) else ""
    if "observ" in text:
        return "observed"
    if "suppos" in text:
        return "supposed"
    return "other"


def download_bdcharm_faults(
    department: str, *, cache_dir: Path, timeout: float = 60.0
) -> Path | None:
    """Download the BDCharm50 package for a French department to ``cache_dir``.

    Returns the path to the downloaded ``.zip`` (which ``load_fault_lines`` reads),
    or ``None`` on failure. Cached: an already-downloaded package is reused.
    """
    code = department.zfill(3)
    target = cache_dir / f"GEO050K_HARM_{code}.zip"
    if target.exists() and target.stat().st_size > 0:
        return target
    url = f"{_BDCHARM_BASE}/GEO050K_HARM_{code}.zip"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "KarstLab"})
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed BRGM mirror
            target.write_bytes(response.read())
        return target
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("BDCharm50 download failed for dept %s: %s", department, exc)
        return None


__all__ = [
    "FAULT_DISTANCE_CLASSES",
    "annotate_fault_distances",
    "caveline_bearing",
    "download_bdcharm_faults",
    "fault_distance_class",
    "fault_orientation_label",
    "faults_to_geojson",
    "line_bearing_deg",
    "load_fault_lines",
]
