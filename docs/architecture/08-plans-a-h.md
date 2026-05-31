# KarstLab — Unified Implementation Plan: Plans A–H

**For Codex. All design decisions are final. Do not deviate from signatures, paths, or
semantics without explicit override from the architect.**

---

## Current Status (update this section after each plan merges)

| Plan | Status | Branch | Notes |
|------|--------|--------|-------|
| G | reviewed — accepted for Plan H development | `codex/plan-g-scalability` | DEM scalability; review findings fixed; `make check` passed |
| C | reviewed — accepted for Plan H development | `codex/plan-g-scalability` | Survey line import; `make check` passed |
| D | reviewed — accepted for Plan H development | `codex/plan-g-scalability` | POI type discrimination; `make check` passed |
| A | reviewed — accepted for Plan H development | `codex/plan-g-scalability` | Multidirectional hillshade; `make check` passed |
| B | reviewed — accepted for Plan H development | `codex/plan-g-scalability` | Depression depth raster export; `make check` passed |
| E | reviewed — accepted for Plan H development | `codex/plan-g-scalability` | Doline alignment rosettes; `make check` passed |
| F | reviewed — accepted for Plan H development | `codex/plan-g-scalability` | Conduit prediction corridor; 20 tests; `make check` passed. See Plan F deviations below. |
| H | implemented — ready for review | `codex/plan-g-scalability` | Backtest validation; 8 tests; `make check` passed. See Plan H deviations below. |
| I | implemented — ready for review | `codex/plan-g-scalability` | Distance measurement; client-side Leaflet JS; 3 tests; `make check` passed |
| J | pending | — | BRGM Cavités overlay (M) |
| K | pending | — | Extra basemaps + WMS (M) |
| L | pending | — | Altimetric profile (M-L) |

---

## Codex Review — 2026-05-31

**Decision:** Plans G, C, D, A, B, E, and F are accepted as the foundation for
Plan H development. No blocking review findings remain for starting the backtest phase.

**Verified after cleanup:**

- `make check` — lint passed, typecheck passed, 444 tests passed, 2 warnings.
- `make test` now uses `.venv/bin/python` automatically when the project venv exists.
- Plan G review fixes are present: settings are injected into the large-DEM threshold path,
  CRS fallback comes from `project.crs_analysis`, and the remaining full-array read limitation
  is documented as outside the reconstructed Plan G scope.
- Plan C survey import functions and orientation handling are implemented with tests.
- Plan D `PoiType` mapping and old-cache compatibility are implemented with tests.
- Plans A and B export `hillshade_multi` and `depression_depth` through canonical paths and
  pipeline step outputs.
- Plan E alignment is isolated from conduit/backtest, uses metric CRS helpers, supports DBSCAN
  lazily, and writes rosette PNGs.
- Plan F conduit projection provides reusable analytical field evaluation, `LineBarrier`,
  heading provenance, canonical outputs, and WGS84 contour export.

**Accepted implementation note:**

- Plan F contour export writes GeoJSON `LineString` isolines. The original text mentioned
  converting contours to polygons, but LineString isolines match the `conduit_contours` naming,
  current tests, and Plan H's analytical-field reuse. Treat this as an accepted implementation
  deviation unless the architect explicitly requires filled contour polygons.

---

## Plan G Review Findings (resolved)

These findings were raised during review of `codex/plan-g-scalability` and have been
addressed in the branch unless explicitly noted as a known limitation.

**Resolved blocking findings:**

1. `pipeline.py:353` — `UserSettings()` creates a fresh instance with defaults, ignoring
   the user's actual `~/.karstlab/settings.json`. The VRT/GeoTIFF threshold decision is
   always made against the factory default (500 MB).
   **Resolved:** `run_headless_analysis()` accepts `user_settings: UserSettings | None = None`
   and passes the resolved instance to `_mosaic_exceeds_large_dem_threshold()`.

2. `pipeline.py:294-309` — `_infer_fallback_crs()` hardcodes `EPSG:2154` for LAMB93 ASC
   files. Violates the global invariant "No CRS hardcoded in business/ functions."
   **Resolved:** `_infer_fallback_crs()` was removed. `project.crs_analysis` is the fallback CRS
   when tiles lack an embedded CRS. Pass `fallback_crs=project.crs_analysis` to
   `assemble_vrt()` unconditionally for CRS-less tiles.

3. `raster_io.py` / `pipeline.py` — `read_dem(dem_path)` in `run_headless_analysis()` still
   loads the full array into RAM. The large-DEM guard only avoids writing a GeoTIFF copy;
   it does not prevent OOM for truly large DEMs. The windowed read support in `read_dem` is
   present but unused in the main pipeline path. The Plan G definition of done passes the
   test (512×512 px) but does not hold for production-scale inputs.
   **Known limitation:** The test now explicitly documents that it verifies VRT-mode
   selection, not full OOM prevention. Fixing complete full-array OOM prevention remains
   outside Plan G scope as reconstructed.

**Out-of-scope changes removed from this branch:**

4. `src/karstlab/business/dolines.py` — polygon refactor using `rasterio.features.shapes()`.
   Correct improvement but not Plan G scope. Remove; land in a separate fix.

5. `src/karstlab/presentation/main_window.py`, `map_view.py`, `tile_picker_dialog.py` —
   unrelated GUI bug fixes. Remove; land in a separate PR.

**Resolved non-blocking findings:**

6. `vrt_builder.py:68` — lazy `from rasterio.crs import CRS as _CRS` inside function body.
   Moved to module-level imports.

7. `tests/test_vrt_builder.py:99` — `open_spy` condition `not args and not kwargs` is
   fragile. Updated to `if Path(str(path)) == vrt.path`; added `assert len(source_reads) > 1`.

8. Added test for `assemble_vrt(fallback_crs=...)` code path.

---

## Execution Order and Dependency Map

```
G → C → D → A → B → E → F → H
         ↑           ↑   ↑
         └───────────┘   │
                         └─ C, E, D all feed F
```

Mandatory build order: G first (DEM scalability unblocks everything), C second (survey I/O
feeds F and H), D third (POI typing feeds F), then A and B (independent), then E → F → H.

---

## Plan G — DEM Scalability

**Status:** Reconstructed from audit summary. Verify exact signatures against source audit
before implementing.

**Files (modified):**
- `src/karstlab/data/raster_io.py`
- `src/karstlab/data/vrt_builder.py`
- `src/karstlab/business/pipeline.py`

**Scope:**
- `raster_io.py`: windowed read support so large DEMs are not fully loaded into RAM
- `vrt_builder.py`: allow the VRT itself to serve as the analysis DEM (skip GeoTIFF export
  when memory is tight)
- `pipeline.py`: a size guard that switches automatically to windowed/VRT mode when the DEM
  exceeds `UserSettings.large_dem_threshold_mb`

**canonical_output_paths:** No new keys.

**New dependencies:** None.

**Definition of done:**
- [ ] Full pipeline completes on a synthetic DEM exceeding `large_dem_threshold_mb` without OOM
- [ ] VRT-only analysis path produces identical doline results to GeoTIFF path on same data
- [ ] `make test` passes

---

## Plan C — Survey Line Import

**Files (modified):** `src/karstlab/data/vector_io.py`

**New functions:**

```python
def read_gpx_track(path: Path) -> gpd.GeoDataFrame:
    """
    Read GPX <trk>/<trkseg> as a GeoDataFrame in WGS84 (EPSG:4326).

    Returns GeoDataFrame with columns:
      geometry (LineString), name (str | None), time (datetime | None).
    Concatenates multiple track segments into a single LineString
    preserving vertex order.
    Raises ValueError if no track segments are found.
    """

def read_kml_lines(path: Path) -> gpd.GeoDataFrame:
    """
    Read KML LineString geometries as a GeoDataFrame in WGS84 (EPSG:4326).

    Returns GeoDataFrame with columns:
      geometry (LineString), name (str | None), description (str | None).
    Raises ValueError if no LineString geometries are found.
    """

def survey_line_geometry(
    gdf: gpd.GeoDataFrame,
    *,
    downstream_end: Literal["first", "last"] = "first",
) -> shapely.geometry.LineString:
    """
    Extract a single LineString from a GeoDataFrame, applying orientation convention.

    Convention: first vertex = downstream (resurgence end),
    last vertex = upstream (current terminus, prediction start).

    If downstream_end="last", the LineString is reversed so first vertex
    becomes downstream. The returned geometry always satisfies the convention.

    If the GeoDataFrame contains multiple geometries, merges them into one
    LineString in row order. Raises ValueError if segments are not
    end-to-end connected (gap > 1 m in projected space).
    """
```

**Orientation validation note:** `survey_line_geometry()` applies the orientation but cannot
verify it is geologically correct — that is the user's responsibility. Callers (GUI,
`run_conduit_analysis()`) must expose the `downstream_end` parameter explicitly and not
assume a default silently.

**canonical_output_paths:** No new keys (plan C is I/O only).

**New dependencies:** None (gpxpy and simplekml already in stack; re-use existing XML parsing).

**Tests (`tests/test_vector_io.py`, new cases):**
```
(a) GPX with single trkseg → LineString, WGS84, vertex count matches track points
(b) GPX with two connected trksegs → merged LineString, vertex count = sum
(c) KML LineString → LineString, WGS84, correct coordinate order
(d) downstream_end="last" → returned geometry has vertices reversed vs default
(e) Two non-connected segments → ValueError, not silent merge
(f) output CRS is EPSG:4326 in all cases
```

**Definition of done:**
- [ ] `read_gpx_track` and `read_kml_lines` pass all tests
- [ ] `survey_line_geometry` reverses on `downstream_end="last"` and rejects disconnected segments
- [ ] `make test` passes

---

## Plan D — POI Type Discrimination

**Files (modified):**
- `src/karstlab/data/schemas.py`
- `src/karstlab/data/poi.py`

**Schema change in `schemas.py`:**

```python
class PoiType(StrEnum):
    CAVE = "cave"
    PERTE = "perte"
    RESURGENCE = "resurgence"
    UNKNOWN = "unknown"
```

`PoiRecord` in `poi.py` is a plain frozen dataclass (not a StrictModel — do not migrate it).
Add field with default:

```python
@dataclass(frozen=True)
class PoiRecord:
    name: str
    lat: float
    lon: float
    source: str
    description: str = ""
    external_id: str = ""
    poi_type: PoiType = PoiType.UNKNOWN   # NEW
```

**`poi.py` change:** Add BRGM `type_cavite` → `PoiType` mapping in `fetch_brgm_cavites()`:

```python
_BRGM_TYPE_MAP: dict[str, PoiType] = {
    "Perte": PoiType.PERTE,
    "perte": PoiType.PERTE,
    "Résurgence": PoiType.RESURGENCE,
    "resurgence": PoiType.RESURGENCE,
    "résurgence": PoiType.RESURGENCE,
    "Grotte": PoiType.CAVE,
    "grotte": PoiType.CAVE,
    # extend as BRGM vocabulary is observed in practice
}
```

Unrecognised values → `PoiType.UNKNOWN`. The mapping is kept as a module-level constant so
it can be extended without touching function logic.

**Backward compatibility:** `_read_cache()` must handle records without `poi_type` key:
default to `PoiType.UNKNOWN` on `KeyError` so old cached JSON files don't crash.

**canonical_output_paths:** No new keys.

**New dependencies:** None.

**Tests (`tests/test_poi.py`, new cases):**
```
(a) BRGM record with type_cavite="Perte" → poi_type=PERTE
(b) BRGM record with type_cavite="Résurgence" → poi_type=RESURGENCE
(c) BRGM record with unknown type_cavite value → poi_type=UNKNOWN
(d) Cache round-trip with poi_type preserved
(e) Cache file without poi_type field → loads with poi_type=UNKNOWN (no crash)
```

**Definition of done:**
- [ ] PoiType enum added to schemas.py
- [ ] PoiRecord.poi_type populated from BRGM type_cavite
- [ ] Old cache files load without error
- [ ] `make test` passes

---

## Plan A — Multidirectional Hillshade

**Status:** Reconstructed from audit summary. Verify exportpath key name against source audit.

**Files (modified):**
- `src/karstlab/business/terrain.py`
- `src/karstlab/business/pipeline.py`
- `src/karstlab/data/project_io.py`

**New function in `terrain.py`:**

```python
def multidirectional_hillshade(
    dem: np.ndarray,
    *,
    cell_size: Affine,
    azimuths_deg: tuple[float, ...] = (0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0),
    altitude_deg: float = 45.0,
) -> np.ndarray:
    """
    Combine hillshades from multiple solar azimuths (mean across directions).
    Returns float32 array in same shape as dem. Each azimuth calls hillshade().
    """
```

**`project_io.py` additions:**
```python
HILLSHADE_MULTI_FILENAME = "hillshade_multi.tif"

# In CANONICAL_FILENAMES:
"hillshade_multi": HILLSHADE_MULTI_FILENAME,

# In canonical_output_paths():
"hillshade_multi": project.output_dir / "rasters" / HILLSHADE_MULTI_FILENAME,
```

**`pipeline.py`:** Export `hillshade_multi` as additional terrain derivative in
`_write_terrain_derivatives()`.

**New dependencies:** None.

**Tests (`tests/test_terrain.py`, new cases):**
```
(a) multidirectional_hillshade on flat DEM → uniform array, same shape as input
(b) result is mean of 8 individual hillshades → matches manual computation within 1e-5
(c) custom azimuths parameter respected
```

**Definition of done:**
- [ ] `multidirectional_hillshade` implemented and tested
- [ ] `paths["hillshade_multi"]` exported in pipeline
- [ ] `make test` passes

---

## Plan B — Depression Depth Raster Export

**Status:** Reconstructed from audit summary. Verify exportpath key name against source audit.

**Files (modified):**
- `src/karstlab/business/pipeline.py`
- `src/karstlab/data/project_io.py`

**No new functions.** The `depth` array (`filled - original`, clipped to ≥ 0) already exists
inside `run_headless_analysis()` during the doline detection step. Plan B writes it via the
existing `save_geotiff()`.

**`project_io.py` additions:**
```python
DEPRESSION_DEPTH_FILENAME = "depression_depth.tif"

# In CANONICAL_FILENAMES:
"depression_depth": DEPRESSION_DEPTH_FILENAME,

# In canonical_output_paths():
"depression_depth": project.output_dir / "rasters" / DEPRESSION_DEPTH_FILENAME,
```

**New dependencies:** None.

**Tests (`tests/test_pipeline.py`, new case):**
```
(a) After pipeline run, paths["depression_depth"] exists and is a valid GeoTIFF
    with non-negative values
```

**Definition of done:**
- [ ] `depression_depth.tif` written during `doline_detection` step
- [ ] Added to step output_paths in PipelineStepResult
- [ ] `make test` passes

---

## Plan E — Doline Alignment (Rosette)

**New file:** `src/karstlab/business/alignment.py`

**Modified files:**
- `src/karstlab/data/crs.py` (add vector reprojection helpers — see below)
- `src/karstlab/data/project_io.py` (add rosette_dir path)

### New dataclasses and functions

```python
# business/alignment.py

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rasterio.crs import CRS

from karstlab.data.crs import project_centroids
from karstlab.data.schemas import DepressionResult


@dataclass(frozen=True)
class AlignmentMode:
    azimuth_deg: float         # axial, 0–180°
    confidence: float          # peak_height / mean_background, ≥ 1.0
    bin_index: int             # index into RosetteResult.bin_counts
    pair_count: int            # direction pairs contributing to this peak


@dataclass(frozen=True)
class RosetteResult:
    modes: list[AlignmentMode]
    bin_edges_deg: tuple[float, ...]   # length n_bins + 1, range 0–180
    bin_counts: tuple[int, ...]        # length n_bins
    neighbor_count: int                # total direction pairs used
    cluster_id: int | None             # None = global; int = DBSCAN cluster label
    mean_pair_distance_m: float        # diagnostic: mean of used pairwise distances
    std_pair_distance_m: float         # diagnostic: std of used pairwise distances


@dataclass(frozen=True)
class AlignmentParams:
    n_bins: int = 18                         # 10° per bin, geological convention
    k_neighbors: int = 6                     # neighbors per doline
    max_neighbor_distance_m: float = 2000.0  # upper bound on pair distance (meters)
    min_peak_ratio: float = 1.5              # min confidence for a mode to count
    use_dbscan: bool = False                 # spatial clustering before rosette
    dbscan_eps_m: float = 1000.0             # DBSCAN neighborhood radius (meters)
    dbscan_min_samples: int = 4              # min dolines per DBSCAN cluster


def detect_doline_alignment(
    depressions: list[DepressionResult],
    *,
    crs: CRS | str,
    params: AlignmentParams | None = None,
    rosette_dir: Path | None = None,
) -> list[RosetteResult]:
    """
    Compute rose diagram(s) of doline structural alignment.

    Steps:
    1. Reproject WGS84 centroids to metric CRS via project_centroids().
    2. If use_dbscan=True: DBSCAN cluster the projected centroids (lazy import
       sklearn.cluster.DBSCAN). Noise points (label=-1) are discarded.
       Pairs are computed WITHIN each cluster only.
    3. For each cluster (or globally if use_dbscan=False):
       - Build k-nearest-neighbor pairs within max_neighbor_distance_m.
       - Compute axial bearing (0–180°) for each pair via _fold_bearing().
       - Bin into n_bins circular histogram over [0, 180).
       - Detect peaks: bins with count / mean_background >= min_peak_ratio.
       - Build RosetteResult.
    4. If rosette_dir is not None, write PNG figure(s) via plot_rosette().

    Returns list of RosetteResult, one per cluster (or list of one if use_dbscan=False).
    Returns empty list if fewer than k_neighbors+1 depressions provided.

    CRS must be metric (validated via is_metric_crs()). Raises ValueError if not.

    Parameters with scale dependency: max_neighbor_distance_m and dbscan_eps_m
    are tuned for ~1–10 km² karst fields. Adjust per study area density.
    """


def plot_rosette(
    result: RosetteResult,
    output_path: Path,
) -> Path:
    """
    Write a polar rose diagram (matplotlib) to output_path (PNG).
    Filename convention:
      rosette_global.png           (cluster_id is None)
      rosette_cluster_{id}.png     (cluster_id is int)
    Returns the written path.
    """
```

### Internal helpers (private, in `alignment.py`)

```python
def _fold_bearing(bearing_deg: float) -> float:
    """Fold a 0–360° directional bearing to 0–180° axial direction.
    All folding logic lives here; no folding anywhere else in the module."""

def _pairwise_bearings(
    coords: np.ndarray,          # shape (n, 2), projected meters
    k: int,
    max_distance_m: float,
) -> np.ndarray:
    """
    For each point, compute axial bearings to its k nearest neighbors
    within max_distance_m. Returns 1D array of folded bearings (0–180°).
    Uses scipy.spatial.cKDTree for efficiency.
    """
```

### `data/crs.py` additions

Add these two functions. Both use
`Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)`. Transformer
constructed per call (not cached as module state) to remain stateless.

```python
from pyproj import Transformer
import shapely.geometry

def project_centroids(
    depressions: list[DepressionResult],
    *,
    crs: CRS | str,
) -> list[tuple[float, float]]:
    """
    Reproject WGS84 centroids to target CRS.
    Returns (x, y) tuples in target CRS meters, same order as input.
    Raises ValueError if target CRS is not metric.
    """

def project_geometry(
    geometry: shapely.geometry.base.BaseGeometry,
    *,
    crs: CRS | str,
) -> shapely.geometry.base.BaseGeometry:
    """
    Reproject a shapely geometry from WGS84 to target CRS.
    Works for Point, LineString, Polygon, and their Multi* variants.
    Raises ValueError if target CRS is not metric.
    Uses the same Transformer construction as project_centroids —
    guaranteed identical transform.
    """
```

### `project_io.py` additions

```python
# In PROJECT_DIRECTORIES add:
"output/rosettes",

# In canonical_output_paths():
"rosette_dir": project.output_dir / "rosettes",
```

### New dependency

`scikit-learn` — required only when `use_dbscan=True`. Lazy import inside DBSCAN branch:
```python
if params.use_dbscan:
    from sklearn.cluster import DBSCAN  # noqa: PLC0415
```
Add `scikit-learn` to `pyproject.toml` optional dependencies:
`[project.optional-dependencies] conduit = ["scikit-learn"]`
Document in function docstring.

### Tests (`tests/test_alignment.py`, new file)

```
(a) Linear arrangement: 10 dolines on a N45E line → single mode at 45° ± 5°, confidence > 1.5
(b) Two crossed sets (N45E + N135E grid): two modes, azimuths ± 5° of 45° and 135°.
    Critical: NOT a single average mode around 90°.
(c) Random/uniform arrangement: zero modes returned (all confidences < min_peak_ratio=1.5).
(d) Bearing folding: pair at 350° and same pair from opposite direction (170°) land in the
    same bin. Prove bin_counts[that bin] == 2.
(e) use_dbscan=False → list of one RosetteResult with cluster_id=None, rosette_global.png written.
(f) use_dbscan=True on two spatially separated groups → two RosetteResult objects, two PNG
    files with correct cluster_id in names.
(g) Pair spanning two DBSCAN clusters does NOT contribute to either cluster's bin_counts.
(h) Cluster with fewer than dbscan_min_samples dolines → no RosetteResult for that cluster.
(i) mean_pair_distance_m and std_pair_distance_m computed correctly on known fixture.
(j) Non-metric CRS raises ValueError.
(k) AlignmentParams overridden from config → defaults not used.
(l) UTM zone outside France (e.g. EPSG:32632) produces same modes as EPSG:2154 on same
    synthetic data reprojected to both CRS. Proves no French CRS assumption.
```

**Definition of done:**
- [ ] `business/alignment.py` created
- [ ] `data/crs.py` has `project_centroids` and `project_geometry`
- [ ] `rosette_dir` in `canonical_output_paths` and `PROJECT_DIRECTORIES`
- [ ] All tests (a)–(l) pass
- [ ] `alignment.py` imports nothing from `conduit.py` or `backtest.py`
- [ ] `make test` passes

---

## Plan F — Conduit Prediction Corridor

**New file:** `src/karstlab/business/conduit.py`

**Modified file:** `src/karstlab/data/project_io.py`

### Dataclasses

```python
# business/conduit.py

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import shapely.geometry
from rasterio.crs import CRS

from karstlab.business.alignment import AlignmentMode, RosetteResult
from karstlab.data.schemas import DepressionResult


@dataclass(frozen=True)
class ConduitProjectionParams:
    sigma_m: float = 500.0
    # Lateral uncertainty radius. Scale-dependent; adjust per study area.
    decay_lambda: float = 0.001
    # Along-axis decay rate (1/m). Halving distance = ln(2)/decay_lambda ≈ 693 m.
    max_projection_distance_m: float = 5000.0
    # Computational cutoff only; not a meaningful uncertainty boundary.
    raster_resolution_m: float = 10.0
    # Output GeoTIFF cell size. Independent of sigma_m.
    isoline_values: tuple[float, ...] = (0.5, 0.2, 0.05)
    # Fixed model value isolines. NOT probability quantiles.
    terminal_length_m: float = 200.0
    # Length of terminal segment for heading regression (meters).
    override_heading_deg: float | None = None
    # If set, bypasses linear regression heading derivation.
    heading_angle_tolerance_deg: float = 40.0
    # 45° is the axial upper bound for "closer to along than across"; default is 40°.
    conduit_weight: float = 0.6
    alignment_weight: float = 0.25
    target_weight: float = 0.15
    # Static weights. NOT auto-adjusted by heading reliability.
    barrier_line_buffer_m: float = 0.0
    # Optional secondary mask strip around line barriers (in addition to halfplane mask).


@dataclass(frozen=True)
class HeadingProvenance:
    combined_deg: float                       # heading used in project_conduit()
    conduit_component_deg: float              # derived or override value
    conduit_was_overridden: bool
    alignment_component_deg: float | None     # None if no mode within tolerance
    target_component_deg: float | None        # None if no valid target
    target_point_used: shapely.geometry.Point | None  # WGS84; None if no target
    weights: tuple[float, float, float]       # renormalized (conduit, alignment, target)


@dataclass(frozen=True)
class CandidateEntrance:
    depression: DepressionResult              # source doline, incl. quality flags
    corridor_score: float                     # relative model likelihood at centroid, 0.0–1.0
    # NOT a calibrated probability. See module docstring.
    rank: int                                 # 1 = highest corridor_score


@dataclass(frozen=True)
class ConduitProjectionResult:
    candidates: list[CandidateEntrance]
    raster_path: Path                         # GeoTIFF in analysis CRS
    contours_path: Path                       # GeoJSON in WGS84 (RFC 7946)
    heading_deg: float                        # = heading_provenance.combined_deg
    heading_provenance: HeadingProvenance
    alignment_modes_used: list[AlignmentMode]
    barriers_applied: int
    barrier_paths: tuple[Path, ...]           # empty tuple if no barriers
```

### Main function

```python
def project_conduit(
    known_caveline: shapely.geometry.LineString,
    # WGS84. First vertex = downstream, last = upstream terminus.
    depressions: list[DepressionResult],
    rosette_results: list[RosetteResult],
    *,
    crs: CRS | str,
    output_dir: Path,
    slug: str,
    target_points: list[shapely.geometry.Point] | None = None,
    # WGS84 points. Nearest within heading_angle_tolerance_deg is used.
    # Fixed "nearest within tolerance" strategy — no averaging.
    barrier_geometries: list[shapely.geometry.base.BaseGeometry] | None = None,
    # WGS84. Polygons → rasterize mask. Lines → halfplane mask + optional buffer.
    barrier_source_paths: tuple[Path, ...] = (),
    params: ConduitProjectionParams | None = None,
) -> ConduitProjectionResult:
    """
    Predict a karst conduit continuation as a relative likelihood corridor.

    Probability field:
      p(x, y) = exp(-0.5 * (d_perp / sigma_m)^2) * exp(-decay_lambda * d_along)
    Normalized to peak = 1.0 at (conduit terminus, d_along=0, d_perp=0).
    Barrier mask applied AFTER normalization.

    Heading = weighted mix of:
      (a) conduit continuering (terminal segment linear regression, or override)
      (b) highest-confidence rosette mode within heading_angle_tolerance_deg
      (c) nearest target_point within heading_angle_tolerance_deg
    Missing components drop out; remaining weights renormalized to sum 1.0.
    Weights are STATIC — not adjusted by heading reliability.

    CandidateEntrance.corridor_score: evaluated from CONTINUOUS field function,
    NOT from the GeoTIFF raster. Score is independent of raster_resolution_m.

    Corridor GeoTIFF: analysis CRS (metric), float32.
    Contour GeoJSON: WGS84 (RFC 7946). Do NOT write GeoJSON in EPSG:2154.

    Output represents RELATIVE MODEL LIKELIHOOD, not calibrated probability.
    State this in all exports and user-facing labels.
    """
```

### Pipeline function

```python
def run_conduit_analysis(
    project: ProjectFile,
    known_caveline: shapely.geometry.LineString,
    # WGS84, orientation already applied via survey_line_geometry().
    rosette_results: list[RosetteResult],
    prior_pipeline_result: PipelineResult,
    # From run_headless_analysis(). Validated non-empty.
    *,
    target_points: list[shapely.geometry.Point] | None = None,
    barrier_geometries: list[shapely.geometry.base.BaseGeometry] | None = None,
    barrier_source_paths: tuple[Path, ...] = (),
    params: ConduitProjectionParams | None = None,
) -> ConduitProjectionResult:
    """
    Orchestrate conduit analysis on doline results from a prior DEM pipeline run.

    Raises ValueError if prior_pipeline_result.depressions is empty.
    Does NOT re-run doline detection.
    Uses canonical_output_paths(project) for raster_path and contours_path.
    """
```

### Implementation notes for Codex

**Heading derivation (terminal segment regression):**
1. Reproject `known_caveline` via `project_geometry()` → projected coordinates
2. Interpolate last `terminal_length_m` meters via `shapely.ops.substring`
3. Fit `np.polyfit(x_coords, y_coords, 1)` → slope → `atan2` → azimuth [0°, 360°)
4. Fold to axial 0–180° using same `_fold_bearing` logic as alignment.py
   (define as a shared private function in `data/crs.py` to avoid duplication without
   creating a circular import between alignment.py and conduit.py)

**Field computation:**
1. Build 2D grid over `[terminus, terminus + max_projection_distance_m]` × `[axis ± 4*sigma_m]`
   in projected space, cell size `raster_resolution_m`
2. For each cell: compute `d_along` (signed, along heading) and `d_perp` (perpendicular)
3. Set p=0 for cells with `d_along < 0` or `d_along > max_projection_distance_m`
4. Apply decay formula; normalize to peak=1.0
5. Apply barrier masks (after normalization)
6. Write GeoTIFF via `save_geotiff()` in analysis CRS

**Barrier: polygon** → `rasterio.features.rasterize()` → zero out cells inside polygon.

**Barrier: line → halfplane mask:**
- Reproject via `project_geometry()`
- For each grid cell: cross-product sign vs barrier line → determine side
- Blocked side specified by `blocked_side_point` attribute on barrier geometry
  (a WGS84 `Point`). Blocked = side where reference point falls.
- Zero out all cells on blocked side
- If `barrier_line_buffer_m > 0`: additionally zero cells within that distance of line

**Contour generation:**
- `skimage.measure.find_contours(field, level)` for each `isoline_values` entry
- Convert to shapely `Polygon`; reproject to WGS84 via `project_geometry()` in reverse
- Write as GeoJSON with feature property `"relative_likelihood": value`

**Candidate scoring:**
- Evaluate continuous field analytically at each projected centroid — NOT raster lookup
- Score = 0.0 for masked centroids (barriers)

### `project_io.py` additions

```python
CONDUIT_PROBABILITY_FILENAME = "conduit_probability.tif"

# In CANONICAL_FILENAMES:
"conduit_probability": CONDUIT_PROBABILITY_FILENAME,
"conduit_contours": "conduit_contours_{slug}.geojson",

# In canonical_output_paths():
"conduit_probability": project.output_dir / "rasters" / CONDUIT_PROBABILITY_FILENAME,
"conduit_contours": project.export_dir / f"conduit_contours_{project.slug}.geojson",
```

### Tests (`tests/test_conduit.py`, new file)

```
(a) Normalized field: maximum == 1.0 at (terminus, d_along=0, d_perp=0).
(b) Transverse cross-section at fixed d_along: values match Gaussian formula within 1e-6.
(c) Along-axis at d_perp=0: halving distance matches ln(2)/decay_lambda within 1%.
(d) Isoline invariance: p=0.5 contour position identical for max_projection_distance_m=2000
    and =5000. (Regression test against percentile error.)
(e) corridor_score identical at raster_resolution_m=10 and =5 for same centroid.
    (Proves analytical evaluation.)
(f) Polygon barrier: cells inside → score 0.0; cells outside → unaffected.
(g) Line barrier halfplane: cells on blocked side → 0.0; allowed side → unaffected.
    Regression: corridor axis crossing barrier perpendicularly stops at barrier.
(h) barrier_line_buffer_m > 0: cells within buffer on allowed side also masked.
(i) Barrier in WGS84 reprojected correctly via project_geometry().
(j) Heading derivation: dense vertices in terminal curve + long straight approach →
    heading follows straight section, not terminal curve.
(k) override_heading_deg overrides automatic derivation.
(l) WGS84 LineString → same heading as same line manually reprojected to analysis CRS.
(m) No rosette mode within tolerance → alignment_component_deg=None, weights sum=1.0.
(n) Two modes within tolerance → highest confidence used, not averaged.
(o) Target outside heading_angle_tolerance_deg → component (c) absent, weights renormalized.
(p) Multiple targets → nearest within tolerance chosen, not averaged.
(q) run_conduit_analysis() with empty depressions → ValueError.
(r) run_conduit_analysis() reuses exact doline IDs/centroids from prior_pipeline_result.
(s) contours_path GeoJSON: coordinates in WGS84 degree range.
    raster_path GeoTIFF: CRS matches analysis CRS, not EPSG:4326.
(t) StaticWeights: short known segment does NOT auto-change conduit_weight.
(u) barriers_applied==0 and barrier_paths==() when no barriers passed.
```

**Definition of done:**
- [x] `business/conduit.py` created
- [x] `conduit_probability` and `conduit_contours` in `canonical_output_paths`
- [x] `conduit.py` imports from `alignment.py`; `alignment.py` imports nothing from `conduit.py`
- [x] All tests (a)–(u) pass (implemented as 20 cases in `tests/test_conduit.py`)
- [x] Module docstring declares output is relative model likelihood, not calibrated probability
- [x] `make test` passes

### Plan F — implementation deviations (intentional, approved at build time)

1. **`blocked_side_point` → `LineBarrier` dataclass.** shapely 2.x geometries are
   immutable C objects and cannot carry an arbitrary `blocked_side_point` attribute
   (`AttributeError`). Line barriers are therefore passed as a new frozen dataclass
   `LineBarrier(line, blocked_side_point)` (both WGS84); polygon barriers stay plain
   shapely geometries. `barrier_geometries` is typed `list[BaseGeometry | LineBarrier]`.

2. **Shared `_fold_bearing` lives in `data/crs.py` as `fold_bearing`.** Per the plan's
   own implementation note (avoid an `alignment ↔ conduit` circular import). `alignment.py`
   now imports it as `_fold_bearing`; the folding convention exists in exactly one place.

3. **Heading uses the terminal-segment chord, not `np.polyfit`.** The chord
   (first→last vertex of the last `terminal_length_m`) is independent of vertex density
   and robust to near-vertical orientation, which is exactly what test (j) requires
   (dense terminal curl must not override the straight approach). `np.polyfit` is both
   density-biased and unstable for steep lines, so the chord is used instead. Same
   axial-fold + weighted-circular-mean combination as specified.

4. **Added `corridor_field_value()` and `data/crs.py:unproject_geometry()`** as the
   single continuous-field function (so candidate scores and contours share one formula)
   and the metric→WGS84 inverse used for contour export.

---

## Plan H — Backtest Validation

**New file:** `src/karstlab/business/backtest.py`

**Modified file:** `src/karstlab/data/project_io.py`

### Dataclasses

```python
# business/backtest.py

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import shapely.geometry
from rasterio.crs import CRS

from karstlab.business.alignment import RosetteResult
from karstlab.business.conduit import ConduitProjectionParams
from karstlab.data.schemas import DepressionResult


@dataclass(frozen=True)
class BacktestParams:
    split_fractions: tuple[float, ...] = (0.3, 0.4, 0.5, 0.6, 0.7)
    # Generation mechanism only. Candidates failing min lengths are dropped.
    min_known_length_m: float = 300.0
    # Minimum downstream segment for reliable heading (should exceed terminal_length_m).
    min_hidden_length_m: float = 100.0
    # Minimum upstream segment to measure corridor coverage.
    min_valid_splits: int = 2
    # Below this, report "survey too short for reliable backtest distribution".


@dataclass(frozen=True)
class SplitMetrics:
    split_fraction: float
    chainage_m: float                        # distance from downstream end to cut point
    known_length_m: float
    hidden_length_m: float
    fraction_within_isoline_050: float       # fraction of hidden line where field p ≥ 0.5
    fraction_within_isoline_020: float       # fraction of hidden line where field p ≥ 0.2
    fraction_within_isoline_005: float       # fraction of hidden line where field p ≥ 0.05
    mean_perp_distance_m: float              # mean perp distance from hidden line to predicted axis
    heading_within_tolerance: bool           # actual hidden heading within heading_angle_tolerance_deg


@dataclass(frozen=True)
class SkippedSplit:
    split_fraction: float
    chainage_m: float
    reason: Literal["known_too_short", "hidden_too_short"]


@dataclass(frozen=True)
class BacktestResult:
    valid_splits: list[SplitMetrics]
    skipped_splits: list[SkippedSplit]   # never silently omitted
    total_survey_length_m: float
    is_sufficient: bool                  # len(valid_splits) >= min_valid_splits
    insufficiency_reason: str | None     # None if sufficient
    report_path: Path                    # JSON
    figure_path: Path | None             # PNG; None if write_figure=False
```

### Main function

```python
def run_backtest(
    known_caveline: shapely.geometry.LineString,
    # WGS84. Orientation already applied: first vertex downstream, last upstream.
    depressions: list[DepressionResult],
    rosette_results: list[RosetteResult],
    *,
    crs: CRS | str,
    output_dir: Path,
    slug: str,
    target_points: list[shapely.geometry.Point] | None = None,
    barrier_geometries: list[shapely.geometry.base.BaseGeometry] | None = None,
    conduit_params: ConduitProjectionParams | None = None,
    backtest_params: BacktestParams | None = None,
    write_figure: bool = True,
) -> BacktestResult:
    """
    Validate project_conduit() against a known survey by withholding its upstream end.

    For each valid split:
    1. Cut known_caveline at chainage. Downstream = known; upstream = ground truth.
    2. Call project_conduit() on the downstream part.
    3. Evaluate predicted corridor against the hidden upstream part (analytical field,
       not raster lookup):
       - Fraction within each isoline (p >= 0.5, 0.2, 0.05)
       - Mean perpendicular distance to predicted axis
       - Whether actual heading is within heading_angle_tolerance_deg of predicted

    Skipped splits included in JSON report with reason. Never silently omitted.
    If len(valid_splits) < min_valid_splits: is_sufficient=False, report explains why.

    Reuses project_conduit() and shared reprojection helpers unchanged.
    Does not implement its own field computation or transforms.

    Orientation validation: if target_points provided, validates that vertex-0 is
    geometrically closer to the nearest resurgence than vertex-last. Reports discrepancy
    in provenance if detected; does not silently flip.
    """
```

### JSON report structure

```json
{
  "schema_version": "1.0.0",
  "slug": "...",
  "total_survey_length_m": 2341.5,
  "is_sufficient": true,
  "insufficiency_reason": null,
  "valid_splits": [
    {
      "split_fraction": 0.3,
      "chainage_m": 702.4,
      "known_length_m": 702.4,
      "hidden_length_m": 1639.1,
      "fraction_within_isoline_050": 0.71,
      "fraction_within_isoline_020": 0.88,
      "fraction_within_isoline_005": 0.94,
      "mean_perp_distance_m": 87.3,
      "heading_within_tolerance": true
    }
  ],
  "skipped_splits": [
    {
      "split_fraction": 0.05,
      "chainage_m": 117.1,
      "reason": "known_too_short"
    }
  ]
}
```

### `project_io.py` additions

```python
# In CANONICAL_FILENAMES:
"backtest_report": "backtest_report_{slug}.json",
"backtest_figure": "backtest_figure_{slug}.png",

# In canonical_output_paths():
"backtest_report": project.export_dir / f"backtest_report_{project.slug}.json",
"backtest_figure": project.export_dir / f"backtest_figure_{project.slug}.png",
```

### Tests (`tests/test_backtest.py`, new file)

```
(a) Long synthetic survey (1000 m): all 5 fractions valid, skipped_splits empty,
    is_sufficient=True.
(b) Short survey (400 m, min_known=300, min_hidden=100): some fractions filtered.
    Skipped splits in report with correct reason.
(c) Very short survey (total < min_known + min_hidden): is_sufficient=False,
    insufficiency_reason non-empty, valid_splits empty. No crash.
(d) Reversed orientation: last vertex at resurgence side → backtest detects discrepancy
    when target_points provided.
(e) Positive control: straight synthetic survey, straight corridor aligned to survey →
    fraction_within_isoline_050 >= 0.8.
(f) SplitMetrics fractions evaluated from continuous field: identical at
    raster_resolution_m=10 and =5 on same cut.
(g) Report JSON contains chainage_m, known_length_m, hidden_length_m per split.
(h) Skipped splits NEVER omitted from report JSON.
```

**Definition of done:**
- [x] `business/backtest.py` created
- [x] `backtest_report` and `backtest_figure` in `canonical_output_paths`
- [x] `backtest.py` imports from `conduit.py`; `conduit.py` imports nothing from `backtest.py`
- [x] All tests (a)–(h) pass
- [x] Report JSON matches schema above
- [x] `make test` passes (`make check`: lint + typecheck + 452 tests green)

### Plan H — implementation deviations (intentional)

1. **Field reuse via `conduit.corridor_axis` / `CorridorContext`.** To honour "reuses
   `project_conduit()` … does not implement its own field computation or transforms",
   the heading + analytical field were extracted from `project_conduit` into a shared
   `corridor_axis()` returning a `CorridorContext` (terminus, forward/perp, barriers,
   provenance) with `field_at_metric()` / `field_at_wgs84()`. `project_conduit` now calls
   it too, so backtest and projection share one field formula. Hidden-line coverage is
   evaluated with the continuous field (resolution-independent — test f).

2. **`orientation_warning` added to `BacktestResult` + report JSON.** The plan text says
   orientation discrepancy is "reported in provenance", but `BacktestResult` has no
   provenance field. Added an explicit `orientation_warning: str | None` field and JSON
   key; never auto-flips the line (global invariant 6). Test (d) asserts it is set when
   `target_points` indicate a reversed survey.

---

## Cross-Plan Summary

### New files
| File | Plan |
|------|------|
| `src/karstlab/business/alignment.py` | E |
| `src/karstlab/business/conduit.py` | F |
| `src/karstlab/business/backtest.py` | H |
| `tests/test_alignment.py` | E |
| `tests/test_conduit.py` | F |
| `tests/test_backtest.py` | H |

### Modified files
| File | Plans |
|------|-------|
| `src/karstlab/data/crs.py` | E (project_centroids, project_geometry) |
| `src/karstlab/data/project_io.py` | A, B, E, F, H (canonical paths) |
| `src/karstlab/data/vector_io.py` | C (read_gpx_track, read_kml_lines, survey_line_geometry) |
| `src/karstlab/data/schemas.py` | D (PoiType, PoiRecord.poi_type) |
| `src/karstlab/data/poi.py` | D (BRGM type mapping) |
| `src/karstlab/business/terrain.py` | A (multidirectional_hillshade) |
| `src/karstlab/business/pipeline.py` | A, B, G |
| `src/karstlab/data/raster_io.py` | G |
| `src/karstlab/data/vrt_builder.py` | G |

### New canonical output paths
| Key | Path | Plan |
|-----|------|------|
| `hillshade_multi` | `output/rasters/hillshade_multi.tif` | A |
| `depression_depth` | `output/rasters/depression_depth.tif` | B |
| `rosette_dir` | `output/rosettes/` (directory) | E |
| `conduit_probability` | `output/rasters/conduit_probability.tif` | F |
| `conduit_contours` | `output/export/conduit_contours_{slug}.geojson` | F |
| `backtest_report` | `output/export/backtest_report_{slug}.json` | H |
| `backtest_figure` | `output/export/backtest_figure_{slug}.png` | H |

### New dependencies
| Package | Plan | Condition |
|---------|------|-----------|
| `scikit-learn` | E | Optional; lazy import; only when `use_dbscan=True` |

### Module dependency direction (non-negotiable)
```
data/crs.py ← business/alignment.py ← business/conduit.py ← business/backtest.py
```
No circular imports. `alignment.py` must not import from `conduit.py` or `backtest.py`.

### Global invariants enforced across all plans
1. No CRS hardcoded in `business/` functions — CRS always a parameter from project config
2. All geometric inputs in WGS84; all analytical computation after reprojection to metric
   analysis CRS via shared `data/crs.py` helpers
3. All GeoJSON output in WGS84 (RFC 7946); GeoTIFFs in analysis CRS
4. Analytical scores (CandidateEntrance, SplitMetrics) evaluated from continuous field
   functions, not raster lookups — score must be independent of `raster_resolution_m`
5. Corridor output labeled "relative model likelihood" — never "probability",
   never "50%/80%/95%"
6. No silent skipping of validation failures — skipped cuts, missing components, orientation
   issues must appear in reports/provenance

---

## Feature Gap Plan — ARIS Lidar Prospector parity (Plans I–L)

These four features bring KarstLab to functional parity with ARIS Lidar Prospector.
They are independent of plans A–H and can be built after v1.1.0 ships.

**Execution order: I → J → K → L** (ascending complexity, no hard dependencies between them).

**Architecture note:** The map is static Folium HTML saved to disk and loaded via
`map_view.load_file()` into QWebEngineView. Two patterns are available:
- **Render-time**: features baked into `render_top_depressions_map_html()` (basemaps, WMS).
- **Runtime JS injection**: features added after load via `map_view._web_view.page().runJavaScript()`.
  The Leaflet map object is found via the same `window[k]._leaflet_id` pattern already in
  `map_view.py` (`_CLICK_HANDLER_JS`).

---

### Plan I — Distance Measurement

**Complexity:** S

**Files (modified):**
- `src/karstlab/presentation/map_view.py`
- `src/karstlab/presentation/tools_tab.py`
- `src/karstlab/presentation/main_window.py`

**No new files. No new dependencies.**

**Approach:** Pure client-side JS. Leaflet has `map.distance(latlng1, latlng2)` built in.
No Python round-trip needed.

```python
# map_view.py — new JS snippets
_DISTANCE_HANDLER_JS = """
(function() {
    if (window._kl_dist_active) return;
    window._kl_dist_active = true;
    window._kl_dist_p1 = null;
    for (var k in window) {
        try {
            var m = window[k];
            if (m && m._leaflet_id && m.on) {
                window._kl_dist_map = m;
                m.on('click', function(e) {
                    if (!window._kl_dist_p1) {
                        window._kl_dist_p1 = e.latlng;
                        window._kl_dist_marker = L.circleMarker(e.latlng,
                            {radius:5,color:'#f59e0b'}).addTo(m);
                    } else {
                        var d = m.distance(window._kl_dist_p1, e.latlng);
                        L.polyline([window._kl_dist_p1, e.latlng],
                            {color:'#f59e0b',dashArray:'6'}).addTo(m);
                        L.popup().setLatLng(e.latlng)
                            .setContent('<b>' + (d >= 1000
                                ? (d/1000).toFixed(2) + ' km'
                                : Math.round(d) + ' m') + '</b>')
                            .openOn(m);
                        window._kl_dist_p1 = null;
                        if (window._kl_dist_marker) { window._kl_dist_marker.remove(); }
                    }
                });
                break;
            }
        } catch(_) {}
    }
})();
"""
```

**New methods on `MapView`:**
```python
def start_distance_mode(self) -> None: ...   # injects _DISTANCE_HANDLER_JS
def clear_distance_mode(self) -> None: ...   # resets _kl_dist_active, removes line/marker
```

**`tools_tab.py`:** Add "Measure distance" toggle button, emit `distance_mode_toggled = Signal(bool)`.

**`main_window.py`:** Connect signal to `map_view.start_distance_mode()` /
`clear_distance_mode()`. Also call `clear_distance_mode()` on analysis start.

**Definition of done:**
- [x] Click 1 places yellow dot, click 2 shows polyline + popup with distance
      (`_DISTANCE_HANDLER_JS` via `MapView.start_distance_mode()`)
- [x] Toggle off removes line and resets state (`_CLEAR_DISTANCE_JS` via
      `clear_distance_mode()`; also cleared on analysis start)
- [x] `make test` passes (`make check` green; `tests/test_distance_tool.py`)

---

### Plan J — BRGM Cavités Overlay

**Complexity:** M

**Files (modified):**
- `src/karstlab/data/poi.py`
- `src/karstlab/presentation/map_view.py`
- `src/karstlab/presentation/markers_tab.py`
- `src/karstlab/presentation/main_window.py`

**No new files. No new dependencies.**
`poi.py` already has `fetch_brgm_cavites()` with caching.

**New function in `poi.py`:**
```python
def brgm_cavites_to_geojson(records: list[PoiRecord]) -> str:
    """Convert PoiRecord list to RFC 7946 GeoJSON FeatureCollection string."""
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r.lon, r.lat]},
            "properties": {
                "name": r.name,
                "description": r.description,
                "external_id": r.external_id,
                "source": r.source,
            },
        }
        for r in records
    ]
    return json.dumps({"type": "FeatureCollection", "features": features})
```

**New method on `MapView`:**
```python
_INJECT_POI_JS_TEMPLATE = """
(function(data, layerName, color) {{
    var geojson = JSON.parse(data);
    for (var k in window) {{
        try {{
            var m = window[k];
            if (m && m._leaflet_id && m.addLayer) {{
                L.geoJSON(geojson, {{
                    pointToLayer: function(f, ll) {{
                        return L.circleMarker(ll, {{
                            radius:6, color:color,
                            fillColor:color, fillOpacity:0.85, weight:1
                        }});
                    }},
                    onEachFeature: function(f, l) {{
                        l.bindTooltip(f.properties.name || 'Cave');
                        l.bindPopup('<b>'+(f.properties.name||'')+'</b><br>'
                            +(f.properties.description||''));
                    }}
                }}).addTo(m);
                break;
            }}
        }} catch(_) {{}}
    }}
}})({geojson!r}, {layer_name!r}, {color!r});
"""

def inject_poi_layer(
    self,
    geojson_str: str,
    layer_name: str = "BRGM Cavités",
    color: str = "#dc2626",
) -> None: ...
```

**`markers_tab.py`:** Add BRGM section: `QLineEdit` for department code (e.g. "25"),
"Load" button, status label. Emit `brgm_load_requested = Signal(str)`.

**`main_window.py`:** On `brgm_load_requested`: run `fetch_brgm_cavites()` in `QRunnable`,
on result call `brgm_cavites_to_geojson()` then `map_view.inject_poi_layer()`.
`fetch_brgm_cavites()` never raises — handle empty result with status label update.

**Tests:**
```
(a) brgm_cavites_to_geojson() → valid RFC 7946, coordinates [lon, lat] order
(b) Empty records → valid FeatureCollection with empty features array
```

**Definition of done:**
- [ ] Department code input + Load button in markers tab
- [ ] BRGM points appear as red dots on map after load
- [ ] Works with cached data (offline fallback)
- [ ] `make test` passes

---

### Plan K — Extra Basemaps + WMS Overlays

**Complexity:** M

**Files (modified):**
- `src/karstlab/presentation/map_builder.py`
- `src/karstlab/data/schemas.py`
- `src/karstlab/resources/regions/fr.json`
- `src/karstlab/business/pipeline.py`

**No new files. No new dependencies** (`folium.raster_layers.WmsTileLayer` is part of folium).

**Approach:** Render-time. All basemaps baked in as Folium TileLayers at map generation.
LayerControl shows them as radio buttons. WMS layers added as Folium WmsTileLayer overlays.

**New dataclasses (in `schemas.py` or `map_builder.py`):**
```python
@dataclass(frozen=True)
class TileLayerSpec:
    name: str
    url: str          # XYZ template: {z}/{x}/{y}
    attribution: str
    show: bool = False

@dataclass(frozen=True)
class WmsLayerSpec:
    name: str
    url: str
    layers: str       # WMS layer name(s)
    attribution: str
    fmt: str = "image/png"
    transparent: bool = True
    version: str = "1.3.0"
    show: bool = False
```

**`map_builder.py` signature extension:**
```python
def build_top_depressions_map(
    depressions: ...,
    *,
    extra_tile_layers: Sequence[TileLayerSpec] = (),
    wms_layers: Sequence[WmsLayerSpec] = (),
    ...
) -> folium.Map:
    ...
    for spec in extra_tile_layers:
        folium.TileLayer(
            tiles=spec.url, attr=spec.attribution,
            name=spec.name, show=spec.show, overlay=False,
        ).add_to(folium_map)

    for spec in wms_layers:
        folium.raster_layers.WmsTileLayer(
            url=spec.url, layers=spec.layers,
            name=spec.name, fmt=spec.fmt,
            transparent=spec.transparent, version=spec.version,
            show=spec.show, overlay=True,
        ).add_to(folium_map)
```

**`fr.json` additions:**
```json
"extra_tile_layers": [
  {
    "name": "IGN Plan",
    "url": "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&FORMAT=image/png&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}",
    "attribution": "© IGN",
    "show": false
  },
  {
    "name": "IGN Satellite",
    "url": "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&FORMAT=image/jpeg&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}",
    "attribution": "© IGN",
    "show": false
  },
  {
    "name": "Cadastre",
    "url": "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=CADASTRALPARCELS.PARCELLAIRE_EXPRESS&STYLE=normal&FORMAT=image/png&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}",
    "attribution": "© IGN",
    "show": false
  }
],
"wms_layers": [
  {
    "name": "BRGM Géologique 50k",
    "url": "https://geoservices.brgm.fr/geologie",
    "layers": "SCAN_H_GEOL50",
    "attribution": "© BRGM",
    "show": false
  },
  {
    "name": "Zones karstiques BDLISA",
    "url": "https://bdlisa.eaufrance.fr/geoserver/ows",
    "layers": "secteurs_karstiques",
    "attribution": "© OFB / BRGM",
    "show": false
  }
]
```

**NOTE:** Verify WMTS URL format (`TILEMATRIXSET=PM`) and WMS endpoint URLs before
release — public endpoints but subject to change. Confirm `TILEMATRIXSET=PM` is compatible
with Leaflet/Folium default tile matrix.

**Tests (`tests/test_map_builder.py`, new cases):**
```
(a) extra_tile_layers → tile URLs appear in rendered HTML
(b) wms_layers → WMS URL appears in rendered HTML with correct layer name
(c) overlay=False for tile layers, overlay=True for WMS layers
```

**Definition of done:**
- [ ] Extra basemaps visible as radio buttons in map LayerControl
- [ ] WMS overlays visible as checkboxes in map LayerControl
- [ ] `make test` passes

---

### Plan L — Altimetric Profile

**Complexity:** M-L

**Files (new):**
- `src/karstlab/presentation/profile_dialog.py`

**Files (modified):**
- `src/karstlab/business/terrain.py`
- `src/karstlab/presentation/map_view.py`
- `src/karstlab/presentation/tools_tab.py`
- `src/karstlab/presentation/main_window.py`

**No new dependencies.** `matplotlib` already in stack; `FigureCanvas` available via
`matplotlib.backends.backend_qtagg` (PySide6 environment).

**New function in `terrain.py`:**
```python
def extract_elevation_profile(
    dem_path: Path,
    start: tuple[float, float],   # (lat, lon) WGS84
    end: tuple[float, float],     # (lat, lon) WGS84
    *,
    crs: CRS | str,
    n_samples: int = 256,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Sample DEM along a geodetic great-circle line.

    Returns (distances_m, elevations_m). distances_m[0] == 0.
    Uses pyproj.Geod for geodetic distance + interpolated projected coordinates
    for rasterio.DatasetReader.sample(). Nodata → nan in elevations_m.
    Raises ValueError if both endpoints are outside the DEM bounds.
    """
```

**`map_view.py` URL scheme extension:**
```python
# In acceptNavigationRequest, add alongside "addmarker":
if url.scheme() == "karstlab" and url.host() == "profile":
    q = QUrlQuery(url.query())
    try:
        lat = float(q.queryItemValue("lat"))
        lon = float(q.queryItemValue("lon"))
        outer.profile_point_placed.emit(lat, lon)
    except ValueError:
        pass
    return False
```

New signal: `profile_point_placed = Signal(float, float)`

New methods:
```python
def start_profile_mode(self) -> None: ...   # 2-click JS, sends karstlab://profile?...
def clear_profile_mode(self) -> None: ...
```

**`main_window.py`:** On `profile_point_placed`: store point 1, on point 2 run
`extract_elevation_profile()` in `QRunnable` (with current project's DEM path and CRS),
open `ProfileDialog` with result. Call `clear_profile_mode()` after dialog closes.

**`profile_dialog.py`:**
```python
class ProfileDialog(QDialog):
    def __init__(
        self,
        distances: np.ndarray,    # metres from start
        elevations: np.ndarray,   # metres ASL, may contain nan
        start: tuple[float, float],
        end: tuple[float, float],
        *,
        parent: QWidget | None = None,
    ) -> None:
        # matplotlib FigureCanvas in QVBoxLayout
        # x-axis: distance (m or km), y-axis: elevation (m)
        # fill_between for visual area under profile
        # title: start/end WGS84 coordinates, total distance
```

**Tests (`tests/test_terrain.py`, new cases):**
```
(a) extract_elevation_profile on synthetic DEM → len(distances) == n_samples
(b) distances[0] == 0, distances[-1] == total_geodetic_distance ± 1%
(c) Known elevated point in DEM → elevations at that location correct ± 1 m
(d) Endpoint outside DEM bounds → elevations at that sample are nan, no crash
```

**Definition of done:**
- [ ] Profile tool toggle in tools tab
- [ ] Click 1 places yellow dot, click 2 shows ProfileDialog with matplotlib chart
- [ ] Profile samples DEM correctly including nodata handling
- [ ] `make test` passes
