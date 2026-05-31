"""Doline alignment and rosette analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from rasterio.crs import CRS
from scipy.spatial import cKDTree

from karstlab.data.crs import fold_bearing as _fold_bearing
from karstlab.data.crs import project_centroids
from karstlab.data.schemas import DepressionResult


@dataclass(frozen=True)
class AlignmentMode:
    azimuth_deg: float
    confidence: float
    bin_index: int
    pair_count: int


@dataclass(frozen=True)
class RosetteResult:
    modes: list[AlignmentMode]
    bin_edges_deg: tuple[float, ...]
    bin_counts: tuple[int, ...]
    neighbor_count: int
    cluster_id: int | None
    mean_pair_distance_m: float
    std_pair_distance_m: float


@dataclass(frozen=True)
class AlignmentParams:
    n_bins: int = 18
    k_neighbors: int = 6
    max_neighbor_distance_m: float = 2000.0
    min_peak_ratio: float = 1.5
    use_dbscan: bool = False
    dbscan_eps_m: float = 1000.0
    dbscan_min_samples: int = 4


def detect_doline_alignment(
    depressions: list[DepressionResult],
    *,
    crs: CRS | str,
    params: AlignmentParams | None = None,
    rosette_dir: Path | None = None,
) -> list[RosetteResult]:
    """Compute doline alignment rosette(s).

    DBSCAN clustering requires the optional ``conduit`` extra, which installs
    scikit-learn. The import is lazy and only used when ``use_dbscan=True``.
    """
    resolved = params or AlignmentParams()
    if len(depressions) < resolved.k_neighbors + 1:
        return []

    coords = np.asarray(project_centroids(depressions, crs=crs), dtype=np.float64)
    clusters = _clusters(coords, resolved)
    results = [
        _rosette_for_cluster(cluster_coords, params=resolved, cluster_id=cluster_id)
        for cluster_id, cluster_coords in clusters
        if len(cluster_coords) >= resolved.k_neighbors + 1
    ]
    if rosette_dir is not None:
        for result in results:
            name = (
                "rosette_global.png"
                if result.cluster_id is None
                else f"rosette_cluster_{result.cluster_id}.png"
            )
            plot_rosette(result, rosette_dir / name)
    return results


def plot_rosette(result: RosetteResult, output_path: Path) -> Path:
    """Write a polar rose diagram PNG to output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    edges = np.asarray(result.bin_edges_deg, dtype=np.float64)
    counts = np.asarray(result.bin_counts, dtype=np.float64)
    widths = np.deg2rad(np.diff(edges))
    centers = np.deg2rad(edges[:-1] + np.diff(edges) / 2.0)

    figure = Figure(figsize=(4, 4))
    FigureCanvasAgg(figure)
    # PolarAxes exposes set_theta_*/set_thetamin; mypy only sees the base Axes.
    axis = cast(Any, figure.add_subplot(111, projection="polar"))
    axis.bar(centers, counts, width=widths, bottom=0.0, align="center")
    axis.set_theta_zero_location("N")
    axis.set_theta_direction(-1)
    axis.set_thetamin(0)
    axis.set_thetamax(180)
    figure.tight_layout()
    figure.savefig(output_path)
    return output_path


def _clusters(coords: np.ndarray, params: AlignmentParams) -> list[tuple[int | None, np.ndarray]]:
    if not params.use_dbscan:
        return [(None, coords)]

    from sklearn.cluster import DBSCAN  # type: ignore[import-untyped]  # noqa: PLC0415

    labels = DBSCAN(eps=params.dbscan_eps_m, min_samples=params.dbscan_min_samples).fit_predict(
        coords
    )
    return [
        (int(label), coords[labels == label])
        for label in sorted(set(labels))
        if label != -1 and np.count_nonzero(labels == label) >= params.dbscan_min_samples
    ]


def _rosette_for_cluster(
    coords: np.ndarray,
    *,
    params: AlignmentParams,
    cluster_id: int | None,
) -> RosetteResult:
    bearings, distances = _pairwise_bearings_and_distances(
        coords,
        k=params.k_neighbors,
        max_distance_m=params.max_neighbor_distance_m,
    )
    counts, edges = np.histogram(bearings, bins=params.n_bins, range=(0.0, 180.0))
    mean_background = float(np.mean(counts)) if len(counts) else 0.0
    modes = _modes(counts, edges, mean_background=mean_background, params=params)
    return RosetteResult(
        modes=modes,
        bin_edges_deg=tuple(float(value) for value in edges),
        bin_counts=tuple(int(value) for value in counts),
        neighbor_count=int(len(bearings)),
        cluster_id=cluster_id,
        mean_pair_distance_m=float(np.mean(distances)) if len(distances) else 0.0,
        std_pair_distance_m=float(np.std(distances)) if len(distances) else 0.0,
    )


def _modes(
    counts: np.ndarray,
    edges: np.ndarray,
    *,
    mean_background: float,
    params: AlignmentParams,
) -> list[AlignmentMode]:
    if mean_background <= 0:
        return []
    modes: list[AlignmentMode] = []
    for index, count in enumerate(counts):
        previous_count = counts[index - 1]
        next_count = counts[(index + 1) % len(counts)]
        confidence = float(count / mean_background)
        if (
            count > 0
            and count >= previous_count
            and count >= next_count
            and confidence >= params.min_peak_ratio
        ):
            modes.append(
                AlignmentMode(
                    azimuth_deg=float((edges[index] + edges[index + 1]) / 2.0),
                    confidence=confidence,
                    bin_index=index,
                    pair_count=int(count),
                )
            )
    return modes


def _pairwise_bearings(
    coords: np.ndarray,
    k: int,
    max_distance_m: float,
) -> np.ndarray:
    bearings, _distances = _pairwise_bearings_and_distances(
        coords,
        k=k,
        max_distance_m=max_distance_m,
    )
    return bearings


def _pairwise_bearings_and_distances(
    coords: np.ndarray,
    *,
    k: int,
    max_distance_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    if len(coords) < 2 or k <= 0:
        return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64)

    tree = cKDTree(coords)
    neighbor_count = min(k + 1, len(coords))
    distances, indexes = tree.query(coords, k=neighbor_count)
    distances = np.atleast_2d(distances)
    indexes = np.atleast_2d(indexes)
    bearings: list[float] = []
    used_distances: list[float] = []
    for source_index, (point_distances, point_indexes) in enumerate(
        zip(distances, indexes, strict=True)
    ):
        for distance, target_index in zip(point_distances, point_indexes, strict=True):
            if target_index == source_index or not np.isfinite(distance):
                continue
            if float(distance) > max_distance_m:
                continue
            dx = coords[int(target_index), 0] - coords[source_index, 0]
            dy = coords[int(target_index), 1] - coords[source_index, 1]
            bearing = (np.degrees(np.arctan2(dx, dy)) + 360.0) % 360.0
            bearings.append(_fold_bearing(float(bearing)))
            used_distances.append(float(distance))
    return np.asarray(bearings, dtype=np.float64), np.asarray(used_distances, dtype=np.float64)


__all__ = [
    "AlignmentMode",
    "AlignmentParams",
    "RosetteResult",
    "detect_doline_alignment",
    "plot_rosette",
]
