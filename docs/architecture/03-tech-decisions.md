# Technical Decisions Record
# KarstLab v1.0

## TD-01: GUI Framework — PySide6

**Decision:** Use PySide6 (Qt 6) for the GUI framework with dark mode theming and map-centric layout.

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| PySide6 | LGPL license, built-in i18n (QTranslator), QWebEngineView for maps, mature, 34-50MB | Heavier than pywebview |
| pywebview | Tiny (<10MB), web-first UI | No built-in i18n, requires separate web framework |
| Electron + Python | Rich web UI | 150-200MB, complex IPC |
| Flet | Modern, Flutter-based | i18n immature, less GIS community usage |

**Rationale:** PySide6 provides the best combination of built-in i18n support (Qt Linguist), web content embedding (QWebEngineView for Leaflet maps), cross-platform packaging maturity, and LGPL licensing (no commercial restrictions). Dark mode theming reduces eye strain for researchers working with terrain data. The map-centric layout (occupying ~70% of window with collapsible sidebar) prioritizes visual analysis of karst topography.

---

## TD-02: Hydrology — WhiteboxTools

**Decision:** Use WhiteboxTools (via Python wrapper) for hydrological analysis, with binary bundled per platform.

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| WhiteboxTools | 328 tools, battle-tested, depression handling, bundled per platform | Requires ~30MB binary per OS |
| PySheds | Pure Python, lightweight | Less complete hydrology suite |
| RichDEM | Good for flow routing | Weaker stream extraction |
| GRASS GIS | Comprehensive | Heavy dependency, complex setup |

**Rationale:** WhiteboxTools is the industry standard for DEM hydrology with specialized karst-aware depression handling (`breach_depressions_least_cost`). The binary is platform-specific (macOS, Windows, Linux) and bundled with the application, ensuring consistent behavior across machines. Cross-platform Python wrapper provides a clean interface.

---

## TD-03: Doline Detection — Fill-Subtract Method

**Decision:** Use the fill-subtract method where depressions are found by subtracting the original DEM from a filled DEM (removing depressions). This is the core algorithm ARIS uses.

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| Fill-subtract method | Simple, direct, what ARIS implements, no external dependencies | Requires custom hierarchy code for nested depressions |
| opengeos/lidar | Purpose-built for depressions, peer-reviewed | Additional dependency, potentially over-engineered |
| Machine learning | High accuracy (94%) | Needs training data, reserved for future versions |

**Rationale:** The fill-subtract method is straightforward and proven in production. It works by filling depressions in the DEM and subtracting the original, leaving only the depression pixels. This is the algorithm that ARIS uses and has validated. Machine learning-based detection is reserved for a future version once we have sufficient labeled data and research groundwork.

---

## TD-04: Terrain Analysis — rasterio + scipy + GDAL

**Decision:** Use rasterio, scipy, scikit-image, and GDAL for terrain attribute computation. RichDEM is not used.

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| rasterio + scipy + GDAL | All already dependencies for other features; no additional install; well-maintained | Requires manual gradient/curvature formulas |
| RichDEM | One-liner API for slope, curvature | Extra compiled dependency with platform-specific build issues; limited maintenance |
| GRASS GIS | Complete morphometric suite | Heavy dependency, complex setup |

**Rationale:** All terrain attributes needed for KarstLab can be computed with libraries already in the dependency tree:

| Attribute | Implementation |
|-----------|---------------|
| Hillshade | `gdal.DEMProcessing()` — gold standard, supports configurable azimuth/altitude |
| Slope | NumPy gradient on DEM array (`np.gradient`) → arctan → degrees |
| Curvature | `scipy.ndimage` Laplacian or second-derivative filter on DEM array |
| Contours | `rasterio.features.shapes()` or `gdal.ContourGenerate()` |
| Labeling | `scikit-image.measure.label()` for connected-component doline polygonization |

RichDEM was considered but rejected because it introduces a compiled C++ dependency with known build issues on Apple Silicon and Windows, while the above combination covers all requirements with zero additional installs.

---

## TD-05: Interactive Maps — Folium

**Decision:** Use Folium (Leaflet.js wrapper) for interactive map generation.

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| Folium | Simple, WMS/WMTS native, HTML output | Static after generation |
| Leafmap | Higher-level, 6 backends | Heavier dependency |
| ipyleaflet | Bidirectional | Jupyter-focused |

**Rationale:** Folium generates standalone HTML files that embed in QWebEngineView perfectly. It natively supports WMS/WMTS layers, GeoJSON overlays, and custom JS plugins. The original app uses Folium, validating the approach. Map interactivity (measurement, profiles) is handled via custom JS injected into the Folium output.

---

## TD-06: i18n — Qt Linguist

**Decision:** Use Qt's built-in translation system (QTranslator + `.ts`/`.qm` files) with KarstLab-branded file naming.

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| Qt Linguist | Built into PySide6, GUI for translators, plural support | Requires app restart for switch |
| gettext (.po) | Standard Python i18n | Separate from Qt, no GUI tool |
| Custom JSON | Simple | No plural forms, no tooling |

**Rationale:** Since we're already using PySide6, Qt Linguist is the natural choice. It provides a dedicated GUI for translators, handles plural forms and context, and integrates seamlessly with `self.tr()` calls. The `.ts` files are XML and version-control friendly. Translation files are named `karstlab_<locale>.ts` and compiled to `.qm` format.

---

## TD-07: Packaging — PyInstaller

**Decision:** Use PyInstaller to bundle the application for macOS (.app → .dmg) and Windows (.exe).

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| PyInstaller | Mature, PySide6-aware, cross-platform | Large bundles |
| pyside6-deploy (Nuitka) | Official Qt tool, faster binaries | Less mature |
| cx_Freeze | Alternative bundler | Less PySide6 support |
| py2app (macOS only) | macOS-native | No Windows support |

**Rationale:** PyInstaller is the most battle-tested option for bundling PySide6 applications. It handles complex dependency trees (GDAL, PROJ, WhiteboxTools binaries) and has extensive documentation for both macOS .dmg and Windows .exe creation. The original app uses PyInstaller successfully.

---

## TD-08: Python Version — 3.12+

**Decision:** Target Python 3.12 or later.

**Rationale:** Python 3.12 offers improved error messages (important for debugging user DEM issues), faster startup time, and all our dependencies (PySide6, rasterio, whitebox, scipy, scikit-image) fully support it. We skip 3.11 to benefit from 3.12's performance improvements and superior error diagnostics, which are particularly valuable for geospatial processing where DEM validation errors must be clear.

---

## TD-09: Testing — pytest with fixtures

**Decision:** Use pytest with small DEM fixtures for unit/integration testing.

**Rationale:** Business logic (terrain analysis, hydrology, doline detection) is testable with small synthetic DEMs (e.g., 100x100 pixel arrays with known elevation patterns). This allows fast, deterministic tests without large real-world data. Integration tests verify the full pipeline with a small fixture DEM.

---

## TD-10: Vector Export — GeoPandas + simplekml + gpxpy

**Decision:** Use GeoPandas for GeoJSON, simplekml for KML, and gpxpy for GPX export.

**Rationale:** GeoPandas provides native GeoJSON export via `to_file()`. For KML, `simplekml` offers a cleaner API than Fiona's KML driver (which requires explicit enabling and has nested structure limitations). GPX export (for waypoints and tracks) uses `gpxpy`, the standard Python GPX library. gpxpy is also used for GPX import of markers.

---

## TD-11: Report Generation — Jinja2 with Static Map Image

**Decision:** Use Jinja2 HTML templates for report generation with branded dark-mode styling, sortable doline table, and embedded static map image (pre-rendered PNG).

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| Jinja2 HTML with static PNG | Self-contained, no external requests to view | Map is static (no pan/zoom) |
| Jinja2 HTML with embedded Folium | Interactive map in report | Requires external tile servers to render |
| PDF via weasyprint | Printable, professional | Extra heavyweight dependency |

**Rationale:** The report must be self-contained and viewable offline without external tile requests. A pre-rendered static map image (PNG, generated by matplotlib) is embedded directly in the HTML. This means the report works identically whether the user is online or offline and can be shared as a single file. Dark-mode HTML uses KarstLab's earth-tone color palette (#1a1f2e base, #c75d4a terracotta, #4a90d9 water). The doline table is sortable via embedded JavaScript.

---

## TD-12: Project Structure — Layered Architecture

**Decision:** Organize code in four layers: Presentation, Business, Data, Infrastructure.

**Rationale:** Clean separation ensures:
- Business logic is testable without GUI
- Data layer is reusable across different interfaces
- Infrastructure adapters are swappable (e.g., replace WhiteboxTools with alternative)
- Presentation layer handles only UI concerns and i18n

---

## TD-13: DEM Assembly — GDAL VRT

**Decision:** Use GDAL Virtual Raster (VRT) for multi-tile DEM assembly, with optional GeoTIFF output.

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| GDAL VRT | Lazy, no data duplication, handles overlaps, native GIS tool | Requires creating .vrt XML file |
| Manual numpy mosaic | Direct control | Fragile, memory-heavy with large tiles |
| rasterio merge | Pythonic API | In-memory operation, poor for 4+ tiles |

**Rationale:** A VRT (Virtual Raster) is a lightweight XML file that references multiple GeoTIFF files without copying data. GDAL reads the VRT as a single unified raster, handling overlapping tiles automatically. This is the standard GIS approach for multi-tile DEMs and requires zero data duplication. Users can optionally export the assembled DEM as a single GeoTIFF (`input/assembled_dem.tif`) for use in other GIS tools. A tile boundary grid overlay is available on the map for visual reference.

---

## TD-14: Settings Persistence — JSON File with Pydantic Validation

**Decision:** Use a JSON file in the app data directory (~/.karstlab/settings.json) for user settings, validated by Pydantic models at load time.

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| JSON file + Pydantic | Human-readable, easy to debug/share/backup, schema-enforced | Requires model definitions |
| QSettings | Cross-platform, handles directories | Platform-specific storage, hard to debug |
| SQLite | Structured, query-able | Overkill for simple key-value storage |

**Rationale:** A simple JSON settings file is human-readable and easy to debug, share, and backup. Pydantic v2 models validate settings at load time, catching type errors and missing fields immediately. Project-specific settings live in a `project.karstlab` file (JSON) in the project directory. This approach is transparent to users — they can inspect and edit settings directly if needed. JSON Schema files are also generated from the Pydantic models for external tooling.

---

## TD-15: Logging — Python logging + File Rotation

**Decision:** Use Python's standard logging module with RotatingFileHandler to log to ~/.karstlab/logs/, keeping the last 5 sessions.

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| Python logging | Standard library, no dependency, rotation built-in | Requires setup code |
| loguru | Cleaner API, auto-rotation | Extra dependency |
| Custom to file | Simple | No rotation, logs grow unbounded |

**Rationale:** Python's standard `logging` module with `RotatingFileHandler` requires no external dependency and handles file rotation automatically. Logs are written to ~/.karstlab/logs/karstlab_YYYY-MM-DD_HH-MM-SS.log, with the last 5 sessions kept. A built-in log viewer is available in the Help menu. Error dialogs include a "Copy Log" button for quick debugging.

---

## TD-16: Large DEM Processing — Windowed Reads

**Decision:** Use rasterio windowed reads for DEMs above a configurable threshold (~500MB). Process in tiles (e.g., 4096x4096 blocks) and merge results.

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| Windowed reads | Memory-efficient, scales to 100GB+ DEMs | Requires tiling logic |
| Full in-memory | Simple, fast for small DEMs | Crashes on large DEMs |
| WhiteboxTools only | Already handles tiling internally | Limited control, slower |

**Rationale:** rasterio's windowed read interface allows processing large DEMs in memory-efficient blocks. DEMs below the threshold take the fast path (full in-memory). WhiteboxTools itself handles large rasters internally via GDAL, so this decision primarily affects our terrain analysis (slope, curvature, hillshade) steps. For multi-block processing, we merge results using rasterio's rio-merge or manual numpy concatenation, then write to GeoTIFF.

---

## TD-17: Update Notification — GitHub Releases API

**Decision:** Check GitHub Releases API on startup and show a dismissible banner if a new version is available. No auto-download.

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| GitHub Releases API | Zero infrastructure, works offline, user in control | Requires internet at startup |
| Custom update server | Fine-grained control | Needs hosting and maintenance |
| Auto-download | Seamless UX | User loses control, potential security issue |

**Rationale:** GitHub Releases API requires zero custom infrastructure. The check happens on a background thread at startup; if offline, it silently skips with no user impact. A dismissible banner appears if an update is available, with a link to the release page. Users stay in control — no forced updates or unexpected restarts.

---

## TD-18: Land Profiles — JSON Configuration with Pydantic + JSON Schema

**Decision:** Use region-specific JSON files (in resources/regions/) to define land profiles: localized names, default CRS, map layers, POI sources, and analysis defaults. Validated by Pydantic models and JSON Schema.

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| JSON configuration + Pydantic | Extensible, version-controllable, community PRs, schema-enforced | Requires model definitions |
| Hardcoded profiles | Simple | Not extensible, code bloat |
| Database | Queryable | Overkill, requires setup |

**Rationale:** Each profile is a JSON file defining region-specific defaults. The `name` field uses a nested object structure to support multiple language variants:

```json
{
  "id": "france-mainland",
  "version": "1.0.0",
  "name": {
    "en": "France – mainland",
    "nl": "Frankrijk – vasteland",
    "fr": "France – métropolitaine"
  },
  "default_crs": "EPSG:2154",
  "map_layers": [...],
  "poi_sources": [...],
  "analysis_defaults": {...}
}
```

Profiles include a `version` field for cache invalidation. New regions are contributed via GitHub PRs without touching code. Pydantic models validate all fields at load time; JSON Schema files are shipped alongside for external tooling. The nested `name` object allows community translations without modifying the profile structure.

---

## TD-19: Project Format — Structured Directories with Slug Validation

**Decision:** .karstlab project files are JSON with structured subdirectories: input/, output/rasters/, output/vectors/, output/export/, logs/. Project names are slugified with legacy-incompatible character warnings.

**Rationale:** Clean directory separation makes projects GIS-friendly — users can open output/rasters/ and output/vectors/ directly in QGIS. The project.karstlab file (JSON) contains metadata, parameters, results, and provenance. Project names are automatically slugified (spaces → hyphens, accents stripped) with a warning for characters that would cause issues in file paths. This structure is browsable in the file manager and human-readable.

---

## TD-20: DEM Validation — Scientific Upfront Checks

**Decision:** Validate DEMs before pipeline execution with 12 scientific checks: format, CRS, vertical unit/datum, data type, NoData values, resolution, DSM detection, NoData gap analysis, edge artifact detection, hydrological preconditioning detection, file size, and disk space.

**Rationale:** Early validation prevents cryptic errors deep in the pipeline (e.g., WhiteboxTools crash on invalid NoData). Each check produces an actionable, translated error or warning message (e.g., "Vertical datum not specified — results may be inaccurate" or "File metadata suggests DSM rather than DEM — analysis designed for bare-earth DEM"). The scientific validation suite goes beyond basic format checking to detect subtle data quality issues that affect analysis accuracy. Warnings allow the user to proceed with informed decisions; errors block the pipeline.

---

## TD-21: Error Recovery — Partial Results with DAG Pipeline

**Decision:** The pipeline is modeled as a DAG (Directed Acyclic Graph). Each step tracks its dependencies. On failure, completed steps' outputs are preserved and the user can rerun from the failed step.

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| DAG with cache invalidation | Fine-grained reruns, dependency-aware invalidation | More complex orchestration |
| Linear pipeline with checkpoints | Simpler | Cannot skip independent steps |
| Full restart only | Simplest | Wastes computation, poor UX |

**Rationale:** Terrain analysis steps (hillshade, slope, curvature, hydrology, doline detection) have a dependency graph where some steps are independent (hillshade, slope, curvature can run in parallel) and others depend on prior results (dolines depend on hydrology). The DAG engine tracks completed outputs via file existence + mtime + input hashes. When parameters change, only affected downstream steps are invalidated. This saves computation time and improves the user experience on flaky operations.

---

## TD-22: UI Framework — Dark Mode Map-Centric with 5 Tabs

**Decision:** Modern dark mode with earth-tone color palette (#1a1f2e base, #c75d4a terracotta, #4a90d9 water). Map occupies ~70% of window; sidebar (~30%) is collapsible with 5 tabs: Layers, Results, Tools, Markers, Export. Typography: Geist Sans.

**Rationale:** Maps are the primary output of geospatial analysis. Maximizing map space improves user workflows. Dark mode reduces eye strain for researchers working long sessions with terrain data. Earth-tone colors (terracotta for dolines, water blue for hydrology) are intuitive. The sidebar has 5 tabs: Layers (toggle visibility), Results (Top 25 + full list with quality flags), Tools (parameters + run), Markers (manual placement, GPS entry, GPX/KML import/export), and Export (KML, GeoJSON, GPX, report).

---

## TD-23: Tile Caching — Browser Cache Only

**Decision:** Rely on QWebEngineView's built-in Chromium HTTP cache for tile caching. No custom tile caching implementation.

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| Browser cache only | Zero custom code, auto-management | Cache limited to browser defaults |
| Custom tile cache | Full control, no provider limits | Custom code, potential licensing issues |
| MBTiles database | Offline capable | Heavyweight, requires pre-generation |

**Rationale:** QWebEngineView (Chromium) has a built-in HTTP cache that caches tile requests automatically. This is sufficient for typical usage (recent projects, familiar regions). DEM-derived layers (hillshade, slope, hydrology) are always available offline since they're local GeoTIFFs. No custom code needed. If offline mapping becomes critical, MBTiles support can be added in a future version.

---

## TD-24: Schema Validation — Pydantic v2 + JSON Schema

**Decision:** Use Pydantic v2 for runtime validation of all configuration files (settings.json, project.karstlab, land profiles). Ship JSON Schema files alongside for external tooling.

**Alternatives considered:**
| Option | Pros | Cons |
|--------|------|------|
| Pydantic v2 + JSON Schema | Type-safe, auto-migration, IDE support, external schema | Requires model definitions |
| JSON Schema only | Language-agnostic | No runtime Python validation |
| Manual validation | No dependencies | Error-prone, verbose |

**Rationale:** Pydantic v2 provides fast runtime validation with clear error messages, type coercion, and default values. A single source of truth (Pydantic models in `schemas/`) defines the canonical structure for all configuration formats. JSON Schema files are generated from the models and shipped in `resources/schemas/` for external tools and community profile validation.

---

## TD-25: Depression Ranking — Top 25 with Quality Flags

**Decision:** Rank depressions by maximum depth, present the Top 25 in a dedicated panel, and assign quality flags per depression.

**Rationale:** ARIS presents the 25 deepest depressions as the primary analysis output, matching the workflow of speleologists who prioritize the most significant terrain features. Quality flags (edge_proximity, nodata_adjacent, depth_confidence, shape_regularity, nested) help users distinguish genuine dolines from artifacts. Numbered markers on the map correspond to the Top 25 table ranks. An auto-generated GPX file (`export/Top_Depressions_<project>.gpx`) enables immediate field navigation.

---

## TD-26: POI Sources — BRGM Cavités + Spélébase CAVECENTER

**Decision:** Integrate BRGM Cavités Géorisques and Spélébase CAVECENTER as explicit French POI sources with departmental filtering. POI sources are configured per land profile.

**Rationale:** French speleologists use two authoritative cave databases: BRGM's Cavités Géorisques (official geological survey) and the Spélébase CAVECENTER (community speleological database). Both support departmental filtering for targeted data retrieval. The land profile system makes POI sources configurable per region, so other countries can define their own sources via profile JSON.

---

## TD-27: Provenance & Reproducibility

**Decision:** Every analysis run records full provenance metadata: app version, tool versions (GDAL, PROJ, WhiteboxTools, etc.), input DEM hash (SHA-256), parameter hash, per-step timings, warnings, and output files.

**Rationale:** Scientific reproducibility requires knowing exactly what software, data, and parameters produced a result. The provenance record (stored in `project.karstlab` and exported in `statistics.json`) enables:
- Reproducing results with identical parameters on different machines
- Auditing results for publications and reports
- Debugging by comparing provenance between successful and failed runs
- Cache invalidation by detecting changed inputs or parameters
