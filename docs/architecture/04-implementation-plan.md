# Implementation Plan
# KarstLab v1.0

## Phase Overview

| Phase | Name | Duration | Dependencies |
|-------|------|----------|-------------|
| 0 | Project Setup & Packaging Spike | 3 days | None |
| 1 | Data Layer | 5 days | Phase 0 |
| 2 | Business Layer — Terrain & Hydrology | 5 days | Phase 1 |
| 3 | Business Layer — Dolines, Ranking & Contours | 5 days | Phase 2 |
| 4 | Business Layer — Export, Report & Provenance | 4 days | Phase 3 |
| 5 | Business Layer — Markers, POI & Guided Workflow | 4 days | Phase 3 |
| 6 | Infrastructure — Map Builder & Services | 4 days | Phase 4, Phase 5 |
| 7 | Presentation — GUI Shell | 5 days | Phase 6 |
| 8 | Presentation — Sidebar Panels & Dialogs | 5 days | Phase 7 |
| 9 | Internationalization | 3 days | Phase 8 |
| 10 | Packaging & Distribution | 4 days | Phase 9 |
| 11 | Testing & Polish | 4 days | Phase 10 |

**Total estimated: ~10 weeks** (with phases 4 & 5 running in parallel)

---

## Phase 0: Project Setup & Packaging Spike (3 days)

### Tasks
- [ ] Initialize Python 3.12+ project with `pyproject.toml`
- [ ] Create directory structure with `karstlab/` package root (src/, resources/, tests/)
- [ ] Configure ruff, mypy, pytest, pytest-cov
- [ ] Set up Makefile with common commands (`make test`, `make lint`, `make typecheck`, `make translate`)
- [ ] Install and verify all dependencies:
  - PySide6 (GUI framework)
  - rasterio (raster I/O)
  - pyproj (CRS transformations)
  - shapely (geometry operations)
  - geopandas (geospatial dataframes)
  - numpy (numerical computing)
  - scipy (scientific computing)
  - scikit-image (image processing)
  - whitebox (hydrological analysis)
  - folium (interactive maps)
  - branca (folium HTML elements)
  - simplekml (KML export)
  - gpxpy (GPX import/export)
  - jinja2 (HTML report templating)
  - matplotlib (static map rendering for reports)
  - pydantic (config validation)
  - contextily (basemap tiles for static reports)
- [ ] Note: GDAL and PROJ are bundled via rasterio wheels. PyInstaller hooks must include GDAL/PROJ shared libraries and the PROJ data directory (epsg, proj.db) for CRS support at runtime.
- [ ] Create small synthetic test DEM fixture (100×100 with known depressions)
- [ ] Verify WhiteboxTools runs on macOS AND Windows
- [ ] **Packaging spike**: Build minimal PyInstaller .app/.exe with PySide6 + GDAL + PROJ + WhiteboxTools bundled
- [ ] Set up dark mode QSS stylesheet skeleton
- [ ] Create Pydantic schemas: `AnalysisParams`, `ProjectFile`, `UserSettings`, `LandProfile`
- [ ] Create JSON Schema files from Pydantic models
- [ ] Create land profile JSON files (fr.json, nl.json, be.json, generic.json) with canonical parameter names
- [ ] Validate land profiles against schema

### Deliverables
- Working development environment
- `make test` runs (with zero tests)
- `make lint` and `make typecheck` pass
- Package name: `karstlab`
- WhiteboxTools verified on both macOS and Windows
- **Packaging spike**: proof-of-concept .app and .exe that launch with bundled GDAL/PROJ/WhiteboxTools
- Pydantic schemas and JSON Schema files created
- Land profiles validated

### Why packaging spike in Phase 0
Bundling GDAL, PROJ, and WhiteboxTools binaries via PyInstaller is a known risk. Discovering bundling issues at the end of the project (Phase 10) would require architectural changes. A minimal spike now surfaces platform-specific issues early.

### Test Categorization

Tests are organized into two categories:

- **Offline tests** (default): All tests that don't require network access. These run in CI and locally without internet. This is the default test suite.
- **Network-gated tests**: Tests that hit external APIs (BRGM, Spélébase, tile servers). Marked with `@pytest.mark.network` and skipped by default. Run explicitly with `pytest -m network`.

Rationale: Ensures CI reliability and fast local test runs (no flaky external API calls) while still allowing integration testing of external services when needed.

---

## Phase 1: Data Layer (5 days)

### Tasks
- [ ] `raster_io.py`: `read_dem()`, `save_geotiff()`, `read_band()`, metadata extraction
- [ ] `vrt_builder.py`: `assemble_vrt()` for multi-tile DEM assembly via GDAL VRT; `assemble_geotiff()` for optional GeoTIFF export
- [ ] `crs.py`: `detect_crs()`, `to_metric()`, `to_wgs84()` with pyproj
- [ ] `vector_io.py`: `to_geojson()`, `to_kml()`, `to_gpx()`, `contours_to_vector()`
- [ ] `kml_importer.py`: `import_kml()` for loading existing POI data
- [ ] `gpx_importer.py`: `import_gpx()` for loading marker data
- [ ] Unit tests for all data layer functions

### TDD Approach
1. Write test: load single GeoTIFF, verify array shape, CRS, and NoData value
2. Write test: load multi-tile DEM via VRT, verify assembled array covers all tiles
3. Write test: VRT → GeoTIFF export produces valid single file
4. Write test: reproject DEM from EPSG:4326 to EPSG:2154, verify spatial extent
5. Write test: convert GeoDataFrame to GeoJSON, validate structure
6. Write test: convert GeoDataFrame to KML, validate XML structure
7. Write test: GPX import parses waypoints with coordinates
8. Write test: KML import parses placemarks with coordinates
9. Implement to pass tests

### Acceptance Criteria
- Multi-tile DEMs assemblable via VRT without duplicating data
- Optional GeoTIFF export of assembled DEM works
- Can read any valid GeoTIFF and return numpy array + metadata
- CRS auto-detection works for common EPSG codes
- Reprojection preserves spatial extent within tolerance
- KML and GPX import parse coordinates correctly
- 80%+ test coverage for data layer

---

## Phase 2: Business Layer — Terrain & Hydrology (5 days)

### Tasks
- [ ] `dem_validator.py`: Scientific DEM validation suite (12 checks: format, CRS, vertical unit/datum, data type, NoData, resolution, DSM detection, NoData gaps, edge artifacts, hydro-preconditioning, file size, disk space)
- [ ] `terrain.py`: `hillshade()` via GDAL DEMProcessing, `slope()` via numpy gradient, `curvature()` via scipy
- [ ] `hydrology.py`: `fill_dem()`, `d8_pointer()`, `flow_accumulation()`, `extract_streams()` via WhiteboxTools
- [ ] `infrastructure/whitebox_adapter.py`: WhiteboxTools wrapper with executable detection
- [ ] `infrastructure/env_bootstrap.py`: PROJ/GDAL path setup for bundled environment
- [ ] Unit tests with synthetic DEM

### TDD Approach
1. Write test: validation catches missing CRS metadata → clear error
2. Write test: validation rejects wrong data type → clear error
3. Write test: validation detects missing NoData value → clear error
4. Write test: validation warns on vertical datum absence → warning
5. Write test: validation warns on DSM-like filename → warning
6. Write test: validation warns on edge artifacts → warning
7. Write test: hillshade of flat surface → uniform result
8. Write test: slope of tilted plane → expected angle (±0.1°)
9. Write test: curvature of concave surface → positive values
10. Write test: fill known depression in synthetic DEM → filled array
11. Write test: flow accumulation on simple slope → known pattern
12. Write test: stream extraction at threshold → expected network
13. Implement to pass tests

### Acceptance Criteria
- Validation catches all 12 issue types with actionable, translatable messages
- All terrain attributes compute correctly on synthetic DEM
- WhiteboxTools adapter works on macOS and Windows
- Hydrology pipeline produces valid flow accumulation grid
- 80%+ test coverage

---

## Phase 3: Business Layer — Dolines, Ranking & Contours (5 days)

### Tasks
- [ ] `dolines.py`: Fill-subtract doline detection with `detect()`, `filter_by_depth(min, max)`, `filter_by_area(min, max)`, `assign_quality_flags()`
- [ ] `depression_ranker.py`: `rank()` sorts by max depth, produces Top 25 table, assigns rank IDs, computes confidence scores
- [ ] `contours.py`: `extract()` at configurable `contour_interval_m`
- [ ] Quality flag implementation: edge_proximity, nodata_adjacent, depth_confidence, shape_regularity, nested
- [ ] Unit tests with synthetic DEM containing known depressions

### TDD Approach
1. Write test: fill-subtract method detects 3 known depressions in synthetic DEM
2. Write test: depth filter excludes depressions below `doline_min_depth_m`
3. Write test: depth filter excludes depressions above `doline_max_depth_m`
4. Write test: area filter excludes depressions below `doline_min_area_m2`
5. Write test: area filter excludes depressions above `doline_max_area_m2`
6. Write test: quality flag `edge_proximity` set for depression touching raster edge
7. Write test: quality flag `nodata_adjacent` set for depression bordering NoData
8. Write test: quality flag `nested` set for depression inside larger depression
9. Write test: ranker sorts 50 depressions and returns correct Top 25 by depth
10. Write test: ranked depressions have sequential rank IDs (1–25)
11. Write test: contour extraction at 5m interval produces expected polyline count
12. Implement to pass tests

### Acceptance Criteria
- Doline detection finds known depressions in test DEM
- Depth/area filtering works correctly with both min and max bounds
- Quality flags assigned correctly for all 5 flag types
- Top 25 ranking sorts correctly and assigns sequential IDs
- Contour extraction produces valid GeoDataFrame with proper geometry
- Output includes quality flags per depression
- 80%+ test coverage

---

## Phase 4: Business Layer — Export, Report & Provenance (4 days)

*Can run in parallel with Phase 5.*

### Tasks
- [ ] `exporter.py`: KML, GeoJSON, GPX, statistics JSON export with provenance metadata
- [ ] `report.py`: Jinja2 HTML report generation with dark-mode styling, sortable doline table, static map PNG
- [ ] `resources/templates/report.html.j2`: KarstLab-branded dark-mode template
- [ ] `infrastructure/provenance.py`: ProvenanceCollector — version collection, input hashing, step metadata
- [ ] `land_profiles.py`: Load/select/validate JSON land profiles with Pydantic
- [ ] Unit tests for export formats, report content, provenance

### TDD Approach
1. Write test: GeoJSON export contains expected features with correct geometry types
2. Write test: KML export is valid XML with Placemark elements
3. Write test: GPX export produces valid waypoints with coordinates
4. Write test: statistics JSON includes depression count, area range, depth range, provenance
5. Write test: HTML report contains Top 25 table, parameters, summary statistics
6. Write test: HTML report contains embedded map image (base64 PNG)
7. Write test: provenance collector records app version, tool versions, input hash
8. Write test: land profiles load from JSON and validate against Pydantic model
9. Write test: invalid land profile produces clear error and falls back to generic
10. Implement to pass tests

### Acceptance Criteria
- All export formats are valid and loadable by GIS software
- Auto-generated GPX of top depressions: `export/Top_Depressions_<project>.gpx`
- Report contains all required sections with KarstLab branding and dark-mode styling
- Report displays sortable doline table and embedded static map PNG
- Statistics JSON includes provenance metadata
- Land profiles load and validate correctly
- 80%+ test coverage

---

## Phase 5: Business Layer — Markers, POI & Guided Workflow (4 days)

*Can run in parallel with Phase 4.*

### Tasks
- [ ] `markers.py`: MarkerManager — add/remove markers, GPS coordinate entry, GPX/KML import, GPX export
- [ ] `poi.py`: POIManager — load BRGM Cavités Géorisques, load Spélébase CAVECENTER, filter by department
- [ ] `business/guided_workflow.py`: Step state tracking for guided beginner workflow (6 steps)
- [ ] `project.py`: ProjectManager — create (with slug validation), open, save, directory management, recent projects
- [ ] Unit tests for markers, POI, slug validation, guided workflow state

### TDD Approach
1. Write test: add marker with name and lat/lon → stored in markers list
2. Write test: import GPX with 5 waypoints → 5 markers created
3. Write test: export markers to GPX → valid GPX file with all waypoints
4. Write test: GPX import → export round-trip preserves coordinates within tolerance
5. Write test: POI manager loads BRGM data for department "09" (Ariège)
6. Write test: POI manager loads Spélébase data for department "46" (Lot)
7. Write test: slug validation converts "Trou du Vent" → "trou-du-vent"
8. Write test: slug validation strips accents "Résurgence" → "resurgence"
9. Write test: slug validation warns on legacy-incompatible characters
10. Write test: guided workflow tracks step completion state (6 steps)
11. Implement to pass tests

### Acceptance Criteria
- Markers can be added manually (map click, GPS entry) and imported (GPX, KML)
- Markers exported to GPX are valid and importable
- BRGM and Spélébase POI sources load with departmental filtering
- API timeout handling: 10-second timeout on requests → user-friendly warning
- Cached data fallback: if API fails, show cached data with date indicator
- Offline mode: app notifies user ("Offline — cached data shown" or "Offline — no cached data available")
- Department filtering works correctly for all regions
- POI fetch is non-blocking (UI remains responsive during load)
- Project names slugified correctly with accent stripping and character warnings
- Guided workflow tracks 6 steps matching ARIS process
- 80%+ test coverage

---

## Phase 6: Infrastructure — Map Builder & Services (4 days)

*Depends on Phase 4 (export/report services) and Phase 5 (POI integration).*

### Tasks
- [ ] `map_builder.py`: Folium map construction with layers loaded from active land profile
- [ ] `folium_adapter.py`: Layer configuration from land profile (tiles, WMS, overlays); numbered depression markers; tile boundary grid
- [ ] `http_server.py`: Local server for map files + altitude profile endpoint
- [ ] `update_checker.py`: GitHub Releases API check for app updates
- [ ] `log_manager.py`: Structured file logging with session rotation (keep 5)
- [ ] Measurement tool JS plugin for Folium
- [ ] Elevation profile generation (matplotlib)
- [ ] Unit tests for map builder, HTTP server, update checker, log manager

### TDD Approach
1. Write test: generated map HTML contains expected tile layers from active profile
2. Write test: GeoJSON layers appear in map HTML
3. Write test: numbered markers (1–25) appear for Top 25 depressions
4. Write test: tile boundary grid layer appears when multi-tile DEM used
5. Write test: HTTP server serves files and responds to profile endpoint
6. Write test: update checker parses GitHub Releases API response
7. Write test: log manager creates log files and rotates at 5 sessions
8. Implement to pass tests

### Acceptance Criteria
- Interactive map displays with base layers from active land profile
- All analysis layers toggleable (hillshade, slope, contours, dolines, streams)
- Numbered markers correspond to Top 25 depression ranks
- Tile boundary grid shows when multi-tile DEM assembled
- Map layers configured per land profile (not hardcoded)
- Update checker detects new releases on GitHub
- Structured logging with rotation works correctly
- Measurement tool and elevation profile work in browser
- 80%+ test coverage

---

## Phase 7: Presentation — GUI Shell (5 days)

### Tasks
- [ ] `main.py`: QApplication setup, icon, QTranslator loading
- [ ] `main_window.py`: Map-centric layout (70% map, 30% collapsible sidebar)
- [ ] `sidebar.py`: Collapsible sidebar framework with 5 tab buttons
- [ ] `map_viewer.py`: QWebEngineView + JS bridge for map interaction
- [ ] `styles.py`: Dark mode QSS stylesheet (colors: #1a1f2e base, #c75d4a terracotta, #4a90d9 water, Geist Sans typography)
- [ ] `config.py`: AnalysisParams dataclass, constants, settings hierarchy resolution
- [ ] `pipeline_dag.py` (orchestrator): PipelineDAG connecting GUI → business layer, DAG step tracking, cache invalidation
- [ ] Worker thread with progress signals (progress_updated, step_completed, step_failed, pipeline_finished)
- [ ] Cancellation support via atomic flag

### Acceptance Criteria
- App launches with map-centric layout (70% map, 30% sidebar)
- Sidebar collapses/expands with smooth animation
- Map displays in embedded QWebEngineView
- Pipeline DAG executes steps with dependency awareness
- Worker thread reports progress per DAG step
- Cancel stops pipeline gracefully between steps
- Dark mode styling applied throughout
- Settings hierarchy resolves (highest priority wins):
  1. Built-in defaults (hardcoded)
  2. Land profile defaults
  3. User settings (~/.karstlab/settings.json)
  4. Project settings (project.karstlab)
  5. Per-run UI overrides (sidebar parameter fields)

---

## Phase 8: Presentation — Sidebar Panels & Dialogs (5 days)

### Tasks
- [ ] `layers_tab.py`: Layer toggle switches with opacity sliders; tile grid toggle
- [ ] `results_tab.py`: Top 25 deepest depressions panel + full scrollable doline list; click → map zoom; quality flag indicators
- [ ] `tools_tab.py`: Analysis parameter inputs (6 params with canonical names), DEM selection, land profile selector, "Analyze" button
- [ ] `markers_tab.py`: Marker list, manual placement toggle, GPS coordinate entry, GPX/KML import, GPX export
- [ ] `export_tab.py`: Export buttons (KML, GeoJSON, GPX), report generation, statistics JSON
- [ ] `guided_workflow.py` (presentation): Collapsible step-by-step panel with progress links
- [ ] `settings_dialog.py`: Language, CRS override, land profile selection, WhiteboxTools path, update check toggle
- [ ] `shortcuts_dialog.py`: Keyboard shortcuts reference (Ctrl+?)
- [ ] `progress_dialog.py`: DAG pipeline progress with per-step breakdown, partial results on failure, rerun-from-failed button
- [ ] `update_banner.py`: Dismissible update notification banner

### Acceptance Criteria
- User can create project, select DEM, set 6 analysis parameters
- "Analyze" runs full pipeline with DAG progress feedback per step
- Map displays with layer controls (toggles + opacity sliders)
- Results tab shows Top 25 with numbered ranks + quality flags
- Clickable doline list zooms map to selected feature
- Markers tab supports add, import (GPX/KML), export (GPX), GPS entry
- Pipeline can rerun only failed/invalidated steps
- Guided workflow panel shows 6 steps with progress tracking
- Update banner appears and dismisses correctly
- All 6 analysis parameters use canonical names
- Export buttons produce correct files
- Language, CRS, and land profile configurable in settings

---

## Phase 9: Internationalization (3 days)

### Tasks
- [ ] Mark all UI strings with `self.tr()`
- [ ] Run `lupdate` to extract `.ts` files (karstlab_nl.ts, karstlab_fr.ts, karstlab_en.ts)
- [ ] Translate to Dutch (nl), French (fr), English (en)
- [ ] Translate land profile display names per language
- [ ] Translate map layer names
- [ ] Translate guided workflow step names and descriptions
- [ ] Compile `.qm` files with `lrelease`
- [ ] Implement language selection in settings with restart prompt
- [ ] Translate Jinja2 report template (3 locales)

### Acceptance Criteria
- App displays correctly in all three languages
- Language persists between sessions
- Report generates in selected language
- Land profile names display in selected language
- Guided workflow text translated in all languages
- Map layer names translated per locale
- No untranslated strings visible
- All three `.ts`/`.qm` file pairs generated and compiled

---

## Phase 10: Packaging & Distribution (4 days)

### Tasks
- [ ] Finalize PyInstaller `.spec` files for macOS and Windows (building on Phase 0 spike)
- [ ] Bundle WhiteboxTools binary per platform
- [ ] Bundle PROJ/GDAL data files
- [ ] Bundle land profile JSON files and JSON Schema files
- [ ] Bundle compiled `.qm` translation files
- [ ] Create KarstLab app icons (icns + ico)
- [ ] Build macOS `.app` bundle → `.dmg`
- [ ] Build Windows `.exe` installer with `.karstlab` file association
- [ ] Create macOS file association for `.karstlab` files
- [ ] Test on clean macOS and clean Windows machines
- [ ] Verify all land profiles, translations, and schemas bundled correctly

### Acceptance Criteria
- `.dmg` installs and runs on macOS (Apple Silicon + Intel)
- `.exe` installs and runs on Windows 10/11
- `.karstlab` file associations work on both platforms
- Land profiles, JSON Schemas, and translations bundled and accessible
- WhiteboxTools binary works on both platforms
- No Python installation required on end-user machine
- App size < 500MB
- KarstLab branding applied to installer and icons

---

## Phase 11: Testing & Polish (4 days)

### Tasks
- [ ] End-to-end test with real-world DEM (France: IGN LiDAR HD MNT tile)
- [ ] End-to-end test with Netherlands AHN4 DEM tile
- [ ] Performance profiling on large DEM (10 km²)
- [ ] Memory usage testing with windowed processing validation
- [ ] Verify BRGM and Spélébase POI loading with departmental filters
- [ ] Verify guided workflow end-to-end flow
- [ ] Verify GPX/KML marker round-trip (import → display → export)
- [ ] Verify Top 25 panel → numbered map markers → GPX export chain
- [ ] UI polish and edge case handling (empty DEM, huge DEM, wrong format, missing NoData)
- [ ] Final coverage check (80%+)
- [ ] User acceptance testing with speleologist workflow
- [ ] KarstLab branding verification across all UI and reports

### Acceptance Criteria
- All tests pass
- Coverage ≥ 80%
- No crashes on edge cases (empty DEM, huge DEM, wrong format)
- Large DEMs handled with windowed processing
- Performance meets NFR targets (1 km² < 60s, memory < 2GB)
- ARIS-compatible French preset produces comparable results to ARIS V3d
- KarstLab branding consistent throughout application

---

## Test Plan Summary

### Unit Tests (per phase)

| Test File | Phase | Coverage Target |
|-----------|-------|----------------|
| `test_raster_io.py` | 1 | RasterIO read/write/metadata |
| `test_vrt_builder.py` | 1 | VRT assembly + GeoTIFF export |
| `test_vector_io.py` | 1 | GeoJSON/KML/GPX conversion |
| `test_crs.py` | 1 | CRS detection + reprojection |
| `test_gpx_import_export.py` | 1 | GPX import/export round-trip |
| `test_dem_validator.py` | 2 | All 12 validation checks |
| `test_terrain.py` | 2 | Hillshade, slope, curvature |
| `test_hydrology.py` | 2 | Fill, flow, accumulation, streams |
| `test_dolines.py` | 3 | Fill-subtract detection |
| `test_dolines_max_area.py` | 3 | Max area filtering |
| `test_quality_flags.py` | 3 | All 5 quality flag types |
| `test_depression_ranker.py` | 3 | Top 25 ranking + confidence |
| `test_contours.py` | 3 | Contour extraction at intervals |
| `test_exporter.py` | 4 | KML/GeoJSON/GPX/stats export |
| `test_report.py` | 4 | HTML report content + static map |
| `test_provenance.py` | 4 | Version collection, hashing |
| `test_land_profiles.py` | 4 | Schema validation, loading |
| `test_markers.py` | 5 | Marker CRUD + GPS entry |
| `test_poi.py` | 5 | BRGM/Spélébase loading + filtering |
| `test_slug_validation.py` | 5 | Project name slugging |
| `test_guided_workflow.py` | 5 | Step state tracking |
| `test_numbered_markers.py` | 6 | Numbered markers on map |
| `test_map_builder.py` | 6 | Map HTML + layers |
| `test_pipeline_cache.py` | 7 | DAG cache invalidation |
| `test_project_schema.py` | 7 | Project file validation |

### Integration Tests

| Test File | Phase | Scope |
|-----------|-------|-------|
| `test_pipeline.py` | 7 | Full pipeline end-to-end with synthetic DEM |
| `test_pipeline_rerun.py` | 7 | Rerun-from-failed with cached steps |
| `test_pipeline_partial.py` | 7 | Partial results preservation on failure |
| `test_export_roundtrip.py` | 4 | Export → reimport → verify |

---

## Risk Register

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| WhiteboxTools binary compatibility | High | Medium | Phase 0 spike verifies on both platforms; fallback to pure Python pysheds |
| PROJ/GDAL bundling issues | High | Medium | Phase 0 spike tests PyInstaller bundling early |
| Doline detection accuracy | Medium | Low | Fill-subtract is simple, proven in ARIS; TDD with known depressions |
| QWebEngineView rendering differences | Low | Low | Test Folium output on both platforms |
| Large DEM memory issues | Medium | Medium | Windowed processing with configurable threshold |
| BRGM/Spélébase API availability | Medium | Medium | 10-second timeout on API requests; per-department cache in project directory with cache date tracking; graceful degradation (app remains fully functional without POI data); user notification of fetch failures |
| Translation completeness | Low | Low | English as fallback for missing translations |
| Land profile community adoption | Medium | Medium | Ship with curated default profiles for France, Netherlands, Belgium |
| scikit-image + scipy terrain accuracy | Low | Low | TDD with known surfaces validates correctness before integration |
