# System Architecture
# KarstLab v1.0

## 1. Architecture Overview

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                       KarstLab                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Presentation │  │   Business   │  │     Data     │  │
│  │    Layer      │  │    Layer     │  │    Layer     │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                  │          │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐  │
│  │ PySide6 GUI  │  │  Pipeline    │  │  Rasterio    │  │
│  │ QWebEngine   │  │  DAG Engine  │  │  GDAL/OGR    │  │
│  │ Qt Linguist  │  │  Workers     │  │  GeoPandas   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Infrastructure Layer                 │   │
│  │  WhiteboxTools │ Folium │ PyProj │ Pydantic      │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 1.2 Layer Responsibilities

| Layer | Responsibility | Key Principle |
|-------|---------------|---------------|
| **Presentation** | GUI, map display, user interaction, i18n | No business logic |
| **Business** | Pipeline orchestration (DAG), analysis algorithms, provenance | Framework-agnostic |
| **Data** | File I/O, raster/vector operations, CRS transforms | Stateless functions |
| **Infrastructure** | External tools, map generation, validation schemas, HTTP server | Adapter pattern |

---

## 2. Component Architecture

### 2.1 Component Diagram

```
┌─ Presentation ──────────────────────────────────────────────┐
│                                                              │
│  MainWindow               MapViewer         SettingsDialog   │
│  ├─ Sidebar (collapsible) ├─ QWebEngineView ├─ Language     │
│  │  ├─ Layers Tab        └─ JS Bridge      ├─ CRS Override  │
│  │  ├─ Results Tab                         ├─ Path Config   │
│  │  │  └─ Top 25 Panel                    ├─ Land Profile  │
│  │  ├─ Tools Tab                           └─ Settings      │
│  │  ├─ Markers Tab                                          │
│  │  └─ Export Tab         GuidedWorkflow    ShortcutsDialog │
│  ├─ StatusBar             ├─ Step indicator  └─ Keyboard ref │
│  └─ Update Banner         └─ Progress links                  │
│                           ProgressDialog                     │
│                            ├─ DAG step progress              │
│                            └─ Worker signals                 │
└──────────────────────────────────────────────────────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
┌─ Business ───────────────────────────────────────────────────┐
│                                                              │
│  PipelineDAG                                                 │
│  ├─ Step registry with dependencies                         │
│  ├─ Cache invalidation (hash-based)                         │
│  ├─ Rerun-from-failed-step                                  │
│  └─ Provenance collector                                    │
│                                                              │
│  Pipeline Steps:                                             │
│  ├─ DEMAssembler (VRT + optional GeoTIFF)                   │
│  ├─ TerrainAnalyzer (hillshade, slope, curvature)           │
│  ├─ HydrologyAnalyzer (fill, flow, accumulation, streams)   │
│  ├─ DolineDetector (fill-subtract + quality flags)          │
│  ├─ DepressionRanker (Top 25 + confidence scoring)          │
│  ├─ ContourExtractor (contour lines at interval)            │
│  ├─ Exporter (KML, GeoJSON, GPX)                           │
│  ├─ ReportGenerator (HTML report with static map image)     │
│  └─ MapBuilder (Folium interactive map)                     │
│                                                              │
│  DEMValidator (scientific validation suite)                   │
│  ├─ format_check() │ crs_check() │ type_check()             │
│  ├─ nodata_check() │ resolution_check() │ size_check()       │
│  ├─ vertical_unit_check() │ dsm_detection()                  │
│  ├─ nodata_gap_check() │ edge_artifact_check()               │
│  └─ hydro_preconditioned_check()                             │
│                                                              │
│  LandProfileManager                                          │
│  ├─ load_profile() │ list_profiles() │ get_defaults()        │
│  └─ validate_schema() (JSON Schema + Pydantic)              │
│                                                              │
│  MarkerManager                                               │
│  ├─ add_marker() │ remove_marker() │ import_gpx()           │
│  ├─ import_kml() │ export_gpx() │ gps_entry()              │
│                                                              │
│  POIManager                                                  │
│  ├─ load_brgm_cavites() │ load_spelebase()                  │
│  └─ filter_by_department()                                  │
│                                                              │
│  ProjectManager                                              │
│  ├─ create / open / save / slugify_name                     │
│  └─ settings persistence (Pydantic-validated)               │
│                                                              │
│  UpdateChecker                                               │
│  └─ check_github_releases()                                 │
└──────────────────────────────────────────────────────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
┌─ Data ───────────────────────────────────────────────────────┐
│                                                              │
│  RasterIO              VectorIO              CRSTransformer  │
│  ├─ read_dem()         ├─ to_geojson()       ├─ to_metric()  │
│  ├─ save_geotiff()     ├─ to_kml()           ├─ to_wgs84()   │
│  └─ read_band()        ├─ to_gpx()           └─ detect_crs() │
│                        └─ contours_to_vector()               │
│                                                              │
│  VRTBuilder            GPXImporter           KMLImporter     │
│  ├─ assemble_vrt()     └─ import_gpx()       └─ import_kml() │
│  └─ assemble_geotiff()                                       │
└──────────────────────────────────────────────────────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
┌─ Infrastructure ─────────────────────────────────────────────┐
│                                                              │
│  WhiteboxAdapter       FoliumAdapter       LocalHTTPServer   │
│  ├─ find_executable()  ├─ build_map()      ├─ serve_exports()│
│  ├─ fill_dem()         ├─ add_layers()     └─ profile_endpt  │
│  ├─ d8_pointer()       ├─ add_numbered_markers()             │
│  ├─ flow_accum()       └─ add_tile_grid()                    │
│  └─ extract_streams()                                        │
│                                                              │
│  SchemaValidator        ProjGdalBootstrap    LogManager       │
│  ├─ validate_project()  ├─ setup_proj_lib()  ├─ structured   │
│  ├─ validate_profile()  └─ setup_gdal_data() └─ rotation     │
│  └─ validate_settings()                                      │
│                                                              │
│  ProvenanceCollector                                         │
│  ├─ collect_versions() (app, GDAL, PROJ, WhiteboxTools)     │
│  ├─ collect_input_hash()                                    │
│  └─ collect_step_metadata()                                 │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Component Descriptions

#### Presentation Layer

| Component | Responsibility |
|-----------|---------------|
| `MainWindow` | Map-centric layout (70% map, 30% sidebar), menu bar, status bar, update banner |
| `Sidebar` | Collapsible sidebar with 5 tabs: Layers, Results, Tools, Markers, Export |
| `LayersTab` | Toggle layer visibility (hillshade, slope, streams, dolines, contours, tile grid, imported KML/GPX) |
| `ResultsPanel` | Top 25 deepest depressions + full clickable doline list; click navigates map to feature |
| `ToolsTab` | Analysis parameter inputs, DEM selection, land profile selector, "Analyze" button |
| `MarkersTab` | Marker list, manual placement toggle, GPS coordinate entry, GPX import/export |
| `ExportTab` | Export buttons (KML, GeoJSON, GPX), report generation |
| `MapViewer` | QWebEngineView embedding Folium HTML, JS bridge for profile/measurement tools |
| `GuidedWorkflow` | Optional step-by-step beginner panel (collapsible) |
| `SettingsDialog` | Language selection, CRS override (profile default + manual), paths, land profile selection |
| `ShortcutsDialog` | Keyboard shortcuts reference (Ctrl+?) |
| `ProgressDialog` | Pipeline DAG progress with step breakdown, partial results support on failure |
| `UpdateBanner` | Dismissible banner showing available update from GitHub Releases |

#### Business Layer

| Component | Responsibility |
|-----------|---------------|
| `PipelineDAG` | DAG-based step orchestration with dependency tracking, cache invalidation, rerun-from-failed |
| `DEMAssembler` | Multi-tile assembly: VRT mosaic + optional GeoTIFF output |
| `TerrainAnalyzer` | Hillshade, slope, curvature calculations via rasterio/GDAL/scipy |
| `HydrologyAnalyzer` | DEM filling, D8 flow, accumulation, stream extraction via WhiteboxTools |
| `DolineDetector` | Depression detection using fill-subtract method with depth/area filtering + quality flags |
| `DepressionRanker` | Sort depressions by depth, produce Top 25 table, assign confidence scores |
| `ContourExtractor` | Contour line extraction at given interval |
| `Exporter` | KML, GeoJSON, GPX file writing |
| `ReportGenerator` | HTML report from Jinja2 templates with static map image |
| `MapBuilder` | Folium map construction with layers, numbered markers, and tile grid |
| `DEMValidator` | Scientific DEM validation suite (format, CRS, vertical unit, DSM detection, gaps, edges) |
| `LandProfileManager` | Load/select/validate JSON land profiles from regions/ directory |
| `MarkerManager` | Manual markers, GPS entry, GPX/KML import, GPX export |
| `POIManager` | Load BRGM/Spélébase POI data with departmental filtering |
| `ProjectManager` | Project creation (with slug validation), loading, saving, directory management |
| `UpdateChecker` | Check GitHub Releases API on startup, show dismissible update banner |

#### Data Layer

| Component | Responsibility |
|-----------|---------------|
| `RasterIO` | Read/write GeoTIFF, extract bands, metadata |
| `VectorIO` | Convert analysis results to GeoJSON, KML, GPX |
| `CRSTransformer` | CRS detection, metric reprojection, WGS84 conversion |
| `VRTBuilder` | GDAL VRT mosaic + GeoTIFF merge for multi-tile DEM assembly |
| `KMLImporter` | Import KML files for POI data |
| `GPXImporter` | Import GPX files for markers |

#### Infrastructure Layer

| Component | Responsibility |
|-----------|---------------|
| `WhiteboxAdapter` | Wrapper around WhiteboxTools executable |
| `FoliumAdapter` | Map HTML generation with configured layers, numbered markers, tile grid |
| `LocalHTTPServer` | Serves map files and altitude profile endpoint |
| `SchemaValidator` | Pydantic models + JSON Schema validation for project, profile, settings |
| `ProjGdalBootstrap` | Sets up PROJ_LIB and GDAL_DATA paths for bundled environment |
| `ProvenanceCollector` | Collects version info, input hashes, step metadata for reproducibility |
| `LogManager` | Structured file logging to ~/.karstlab/logs/, rotation (keep 5 sessions) |

---

## 3. Pipeline DAG Architecture

### 3.1 Step Dependency Graph

```
                    ┌───────────┐
                    │ Step 0:   │
                    │ Load Raw  │
                    │ DEM Tiles │
                    └─────┬─────┘
                          │
                    ┌─────▼─────────┐
                    │ Step 1:       │
                    │ Assemble VRT &│
                    │ Reproject to  │
                    │ Metric CRS    │
                    └─────┬─────────┘
                          │
         ┌────────────────┼────────────────┐
         │                │                │
    ┌────▼────┐      ┌────▼────┐      ┌───▼───┐
    │Step 2:  │      │Step 3:  │      │Step 4:│
    │Hillshade│      │Slope    │      │Curv-  │
    └─────────┘      └─────────┘      │ature  │
         │                │            └───┬───┘
         │                │                │
         │          ┌──────┴────────┐      │
         │          │               │      │
    ┌────▼────┐ ┌───▼────┐     ┌───▼───┐ │
    │Step 5:  │ │Step 6: │     │Step 7:│ │
    │Hydro-   │ │Contours│     │Fill   │ │
    │logy     │ └────────┘     │DEM    │ │
    │(streams)│                └───┬───┘ │
    └─────────┘                    │     │
                                   │     │
                            ┌──────▼─────▼──────┐
                            │    Step 8:        │
                            │   Doline          │
                            │   Detection       │
                            │ (fill-subtract)   │
                            └─────────┬─────────┘
                                      │
                            ┌─────────▼─────────┐
                            │    Step 9:        │
                            │   Depression      │
                            │   Ranking +       │
                            │   Quality Flags   │
                            └─────────┬─────────┘
                                      │
                            ┌─────────▼─────────┐
                            │   Step 10:        │
                            │   WGS84 Transform │
                            │ (display/export)  │
                            └─────────┬─────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
              ┌─────▼────┐      ┌─────▼─────┐    ┌────▼───┐
              │ Step 11a: │      │ Step 11b: │    │Step 11c│
              │  Export   │      │   Report  │    │  Map   │
              │(KML/JSON/ │      │  (HTML)   │    │(Folium)│
              │   GPX)    │      └───────────┘    └────────┘
              └───────────┘
```

**DAG Summary:**
- **Step 0**: Load raw DEM tiles from input directory
- **Step 1**: Assemble multi-tile DEM (VRT), reproject to metric CRS (from land profile)
- **Steps 2-6** (parallel): Hillshade, Slope, Curvature, Contours, Hydrology (streams)
  - All depend on metric DEM from Step 1
  - Run independently; no inter-dependencies
- **Step 7**: Fill DEM (depends on metric DEM from Step 1)
- **Step 8**: Doline Detection via fill-subtract (depends on metric DEM + filled DEM)
- **Step 9**: Depression Ranking + quality flags (depends only on dolines from Step 8)
- **Step 10**: WGS84 coordinate transform (post-processing for display/export, depends on dolines)
- **Steps 11a-c** (parallel): Export, Report generation, Interactive map
  - All depend on ranking + WGS84 coords (Steps 9-10)

### 3.2 Cache Invalidation Rules

Each pipeline step produces output files. The DAG engine tracks:

| Tracked Item | Method | Stored In |
|-------------|--------|-----------|
| Input DEM hash | SHA-256 of file content | `project.karstlab` → `provenance.input_hash` |
| Input DEM mtime/size | File metadata | `project.karstlab` → `provenance.input_mtime`, `input_size` |
| Analysis parameters | Hash of parameter dict | `project.karstlab` → `provenance.params_hash` |
| Land profile version | Profile `version` field | `project.karstlab` → `provenance.land_profile_version` |
| Step output files | Existence + mtime | `output/` directory |

**Invalidation logic:**

- **Metric DEM changes** (Step 1): Invalidate ALL downstream steps (Steps 2-11)
  - Steps 2-6 depend directly on metric DEM
  - Step 7 (fill) depends on metric DEM
  - Step 8 (dolines) depends on both metric DEM and filled DEM
  - Steps 9-11 depend transitively through dolines

- **Analysis parameter changes** (parameter-specific):
  - `contour_interval_m` changes → Invalidate Step 6 (Contours) + Steps 11 (Export/Report/Map)
  - `doline_min_depth_m` or `doline_max_depth_m` changes → Invalidate Step 8 (Doline Detection) + Steps 9-11
  - `doline_min_area_m2` or `doline_max_area_m2` changes → Invalidate Step 8 (Doline Detection) + Steps 9-11
  - `stream_threshold_cells` changes → Invalidate Step 5 (Hydrology) + Steps 11

- **Steps 2-6 are independent** of each other
  - Hillshade, Slope, Curvature, Contours, and Hydrology can run in parallel
  - Invalidating one does not affect the others (unless Metric DEM changed)

- **Step 7 (Fill) is independent** of Steps 2-6
  - Invalidating hillshade/slope/curvature/contours/hydrology does not affect filling
  - Fill depends only on metric DEM

- **Doline detection invalidation** (Step 8 → Steps 9-11)
  - If Step 8 is invalidated, Steps 9-11 must also be invalidated
  - Ranking and exports depend on valid doline results

- **WGS84 transform invalidation** (Step 10)
  - Invalidated only when dolines change (Step 8)
  - Independent of all terrain/contour analysis results

- **Rerun-from-failed**: Skip all completed steps whose cache is still valid, resume from first invalid/failed step

### 3.3 Provenance Metadata

Every analysis run records provenance in `project.karstlab`:

```json
{
  "provenance": {
    "app_version": "1.0.0",
    "pipeline_version": "1.0.0",
    "run_timestamp": "2026-05-28T14:02:01Z",
    "run_duration_seconds": 145,
    "input": {
      "dem_path": "input/assembled_dem.tif",
      "sha256": "a1b2c3...",
      "size_bytes": 60817408,
      "mtime": "2026-05-28T13:55:00Z"
    },
    "land_profile": {
      "id": "fr",
      "version": "1.0.0",
      "sha256": "d4e5f6..."
    },
    "params_hash": "7a8b9c...",
    "tool_versions": {
      "python": "3.12.4",
      "gdal": "3.9.1",
      "proj": "9.4.1",
      "rasterio": "1.3.10",
      "whitebox_tools": "2.4.0",
      "pyside6": "6.7.2",
      "folium": "0.17.0"
    },
    "steps": [
      {
        "name": "validate",
        "status": "completed",
        "duration_seconds": 0.3,
        "warnings": ["Vertical datum not specified in DEM metadata"]
      },
      {
        "name": "assemble",
        "status": "completed",
        "duration_seconds": 2.1,
        "output_files": ["input/assembled_dem.tif"]
      }
    ],
    "quality_summary": {
      "depressions_total": 342,
      "depressions_high_confidence": 280,
      "depressions_edge_flagged": 12,
      "depressions_nodata_adjacent": 5
    }
  }
}
```

---

## 4. Data Flow

### 4.1 Analysis Pipeline Flow

```
User clicks "Analyze"
        │
        ▼
┌─ DEMValidator ──────────────────────────────┐
│  Scientific DEM validation                  │
│  ├─ format_check()                          │
│  ├─ crs_check()                             │
│  ├─ vertical_unit_check()                   │
│  ├─ type_check()                            │
│  ├─ nodata_check() + gap analysis           │
│  ├─ resolution_vs_min_doline_check()        │
│  ├─ dsm_detection()                         │
│  ├─ edge_artifact_check()                   │
│  ├─ hydro_preconditioned_check()            │
│  ├─ size_check()                            │
│  └─ disk_space_check()                      │
└─────────────────────────────────────────────┘
        │
        ▼ (validation passed, warnings shown)
┌─ PipelineDAG ──────────────────────────────────────┐
│                                                      │
│  0. Load Raw DEM Tiles                               │
│     └─► Load individual GeoTIFF tiles from input/   │
│                                                      │
│  1. Assemble & Reproject                            │
│     ├─► VRTBuilder.assemble_vrt() (multi-tile)     │
│     ├─► VRTBuilder.assemble_geotiff() (optional)    │
│     └─► CRSTransformer.to_metric() (land CRS)      │
│                                                      │
│  2. Hillshade (parallel with Steps 3-6)             │
│     └─► TerrainAnalyzer.hillshade()                 │
│                                                      │
│  3. Slope (parallel with Steps 2, 4-6)              │
│     └─► TerrainAnalyzer.slope()                     │
│                                                      │
│  4. Curvature (parallel with Steps 2-3, 5-6)        │
│     └─► TerrainAnalyzer.curvature()                 │
│                                                      │
│  5. Hydrology: Streams (parallel with Steps 2-4, 6) │
│     └─► HydrologyAnalyzer.run()                     │
│         ├─ fill_dem() (internal)                    │
│         ├─ d8_pointer()                             │
│         ├─ flow_accumulation()                      │
│         └─ extract_streams()                        │
│                                                      │
│  6. Contours (parallel with Steps 2-5)              │
│     └─► ContourExtractor.extract()                  │
│                                                      │
│  7. Fill DEM (independent of Steps 2-6)             │
│     └─► WhiteboxAdapter.fill_dem()                  │
│                                                      │
│  8. Doline Detection (fill-subtract)                │
│     └─► DolineDetector.detect()                     │
│         ├─ subtract(original_dem, filled_dem)       │
│         ├─ filter_by_depth(min, max)                │
│         ├─ filter_by_area(min, max)                 │
│         └─ assign_quality_flags()                   │
│                                                      │
│  9. Depression Ranking & Quality Flags              │
│     └─► DepressionRanker.rank()                     │
│         ├─ sort_by_max_depth()                      │
│         ├─ assign_rank_ids()                        │
│         ├─ compute_confidence_scores()              │
│         └─ generate_top_25_list()                   │
│                                                      │
│  10. WGS84 Coordinate Transform                     │
│     └─► CRSTransformer.to_wgs84()                  │
│         (convert doline coords for display/export)  │
│                                                      │
│  11. Export, Report & Map (parallel)                │
│     ├─► Exporter.to_kml()                           │
│     ├─► Exporter.to_geojson()                       │
│     ├─► Exporter.to_gpx() (Top Depressions)        │
│     ├─► Exporter.stats_json() (with provenance)    │
│     ├─► ReportGenerator.generate() (HTML + PNG map)│
│     └─► MapBuilder.build() (Folium interactive)    │
│                                                      │
│  Provenance: each step records duration, status,    │
│  output files, warnings to ProvenanceCollector      │
│                                                      │
│  On step failure:                                   │
│  ├─ Mark step as failed in DAG                      │
│  ├─ Keep all completed results (cache valid)        │
│  ├─ Report failed step + exception                  │
│  └─ User can rerun from failed step                 │
│                                                      │
└──────────────────────────────────────────────────────┘
        │
        ▼
  MapViewer displays results (partial or complete)
  Top 25 displayed in Results tab
  GPX auto-exported to export/Top_Depressions_<project>.gpx
```

### 4.2 CRS Strategy

KarstLab employs a two-CRS analysis and display strategy:

**Analysis CRS (Metric):**
- All terrain, hydrology, and doline detection analysis runs in the metric CRS specified by the active land profile
  - Example: EPSG:2154 (Lambert 93) for France
  - Example: EPSG:28992 (RD New) for Netherlands
- This ensures all calculations use real-world distances in meters
- Metric CRS is applied in Step 1 (Reproject)

**Display & Export CRS (WGS84):**
- Interactive map displays coordinates and doline properties in WGS84 (EPSG:4326)
- Status bar shows the land-profile metric CRS code (e.g., "EPSG:2154")
- Top 25 results table shows lat/lon (WGS84) for user reference

**Post-Processing Transform (Step 10):**
- After doline detection (Step 8) and ranking (Step 9), a one-way WGS84 transform is applied (Step 10)
- This transform is NOT part of the analysis pipeline — it only converts output coordinates
- Enables seamless export to display-oriented formats (KML, GeoJSON, GPX)

**Export Formats:**
- KML exports use WGS84 coordinates
- GeoJSON exports use WGS84 coordinates
- GPX exports (Top Depressions) use WGS84 coordinates
- Internal raster outputs remain in metric CRS

**Configuration:**
- User can override the metric CRS in Settings dialog (Advanced CRS Override)
- Default metric CRS comes from the land profile
- Per-run UI overrides in Tools Tab do not affect CRS (CRS is land-profile locked)

### 4.4 Static Report Map Image

The HTML report includes an embedded static map image (PNG, base64-encoded). This map image is generated at report-generation time and includes:

**Map Layers (in rendering order):**
1. Base map tiles (rendered via contextily or static tile fetch)
   - Tiles are fetched at report-generation time and embedded as base64
   - No network requests when opening the report
2. Hillshade overlay (semi-transparent, ~60% opacity)
3. Doline depression polygons (terracotta color #c75d4a, 50% fill, darker border)
4. Top 25 depth-ranked doline markers with sequential numbers (1-25)

**Exclusions from static map:**
- Contour lines (too dense, would obscure dolines at report scale)
- Stream network (too detailed, would overcrowd map)
- Tile grid (internal reference, not user-relevant in static output)

**Map Image Specifications:**
- Default size: 1200 × 800 pixels
- Projection: WGS84 (EPSG:4326) for web display
- Format: PNG embedded in HTML as base64 data URL
- Self-contained: entire HTML report is a single file (no external image references)

**Report Generation Flow:**
1. Analysis completes, dolines ranked in metric CRS
2. Dolines transformed to WGS84 (Step 10)
3. MapBuilder.build_static_map() is called by ReportGenerator
4. Contextily fetches tiles covering the analysis bounds (WGS84)
5. Tiles + hillshade + dolines rendered to PNG
6. PNG base64-encoded and embedded in Jinja2 template
7. HTML file written to `output/export/report.html` (self-contained)

### 4.5 Pipeline Stages & Data Formats (Reference Table)

| Stage | Input | Output | Format | CRS |
|-------|-------|--------|--------|-----|
| Validate | User file | Validation result + warnings | GeoTIFF metadata | Original |
| Assemble | Multi-tile GeoTIFF | VRT + optional GeoTIFF | GDAL Virtual Raster / GeoTIFF | Original |
| Load | User file or VRT | DEM array + metadata | GeoTIFF/VRT → numpy ndarray | Original |
| Reproject | DEM (source CRS) | DEM (metric CRS) | ndarray + Affine transform | Metric |
| Hillshade | DEM (metric) | Shaded relief | ndarray → GeoTIFF | Metric |
| Slope | DEM (metric) | Slope degrees | ndarray → GeoTIFF | Metric |
| Curvature | DEM (metric) | Curvature index | ndarray → GeoTIFF | Metric |
| Hydrology | DEM (metric) | Flow accum, streams | ndarray → GeoTIFF | Metric |
| Dolines | DEM (metric) + filled | Polygons + quality flags | ndarray → GeoDataFrame | Metric |
| Ranking | Dolines GDF (metric) | Ranked dolines + Top 25 | GeoDataFrame | Metric |
| Contours | DEM (metric) | Polylines | ndarray → GeoDataFrame | Metric |
| WGS84 Transform | Dolines (metric) | Dolines (WGS84 coords) | GeoDataFrame | WGS84 |
| Export | GeoDataFrames (WGS84) | Files | GeoJSON, KML, GPX | WGS84 |
| Map | All layers, dolines (WGS84) | Interactive Folium map | HTML (Folium) | WGS84 display |
| Report | Statistics + params, map tiles | HTML report + map PNG | HTML (Jinja2) + embedded PNG | WGS84 |

### 4.6 File Formats Reference

| Format | Extension | Purpose | CRS | Location |
|--------|-----------|---------|-----|----------|
| Project file | `.karstlab` (JSON) | Project configuration, results, provenance | Mixed | `project_dir/project.karstlab` |
| User settings | `settings.json` (JSON) | User preferences, language, defaults | N/A | `~/.karstlab/settings.json` |
| Land profile | `.json` | Regional CRS, analysis defaults, layer config | N/A | `resources/regions/{id}.json` |
| Virtual Raster | `.vrt` | Multi-tile DEM reference (zero-memory) | Metric | `input/assembled_dem.vrt` |
| Assembled DEM | `.tif` (GeoTIFF) | Combined DEM raster (optional) | Metric | `input/assembled_dem.tif` |
| Hillshade | `.tif` (GeoTIFF) | Shaded relief raster | Metric | `output/rasters/hillshade.tif` |
| Slope | `.tif` (GeoTIFF) | Slope angle raster (degrees) | Metric | `output/rasters/slope.tif` |
| Curvature | `.tif` (GeoTIFF) | Curvature index raster | Metric | `output/rasters/curvature.tif` |
| Filled DEM | `.tif` (GeoTIFF) | DEM with depressions filled | Metric | `output/rasters/dem_filled.tif` |
| Flow Accumulation | `.tif` (GeoTIFF) | Hydrologic flow accumulation | Metric | `output/rasters/flow_accum.tif` |
| Streams | `.tif` (GeoTIFF) | Stream network raster | Metric | `output/rasters/streams.tif` |
| Dolines (GeoJSON) | `.geojson` (vector) | Doline polygons + properties | WGS84 | `output/vectors/dolines.geojson` |
| Dolines (KML) | `.kml` (vector) | Doline polygons for GIS import | WGS84 | `output/vectors/dolines.kml` |
| Contours (GeoJSON) | `.geojson` (vector) | Contour lines + elevation | WGS84 | `output/vectors/contours.geojson` |
| Contours (KML) | `.kml` (vector) | Contour lines for GIS import | WGS84 | `output/vectors/contours.kml` |
| Streams (GeoJSON) | `.geojson` (vector) | Stream lines | WGS84 | `output/vectors/streams.geojson` |
| Export Dolines (KML) | `.kml` | User-downloadable doline export | WGS84 | `output/export/dolines.kml` |
| Export Dolines (GeoJSON) | `.geojson` | User-downloadable doline export | WGS84 | `output/export/dolines.geojson` |
| Top 25 GPX | `.gpx` | Top 25 depressions as waypoints | WGS84 | `output/export/Top_Depressions_*.gpx` |
| Markers GPX | `.gpx` | User markers export/import | WGS84 | `output/export/*_markers.gpx` |
| Statistics | `.json` | Analysis summary with provenance | N/A | `output/export/statistics.json` |
| HTML Report | `.html` | Self-contained report with embedded map | WGS84 | `output/export/report.html` |
| Interactive Map | `.html` | Folium map with all layers | WGS84 | `map/index.html` |

---

## 5. Threading Model

```
┌─ Main Thread (GUI) ─────────────────────────────┐
│                                                   │
│  MainWindow ←─── Qt signals ────── AnalysisWorker │
│  ├─ enable/disable UI                  (QThread)  │
│  ├─ update progress bar (DAG steps)         │     │
│  ├─ display results + Top 25                │     │
│  └─ update update banner                    │     │
│                                             │     │
└─────────────────────────────────────────────┼─────┘
                                              │
┌─ Worker Thread ─────────────────────────────┼─────┐
│                                             │     │
│  PipelineDAG.run()                          │     │
│  ├─ emits progress_updated(step, pct, msg)──┘     │
│  ├─ emits step_completed(step_name)               │
│  ├─ emits step_failed(step_name, Exception)       │
│  ├─ emits pipeline_finished(results, provenance)  │
│  └─ checks cancellation_requested flag            │
│                                                   │
│  On failure:                                      │
│  ├─ Completed results remain accessible (cached)  │
│  ├─ Failed step reported to user                  │
│  └─ User can rerun from failed step               │
│                                                   │
└───────────────────────────────────────────────────┘
```

- All GUI updates happen on the main thread via Qt signals
- Pipeline runs entirely on a worker QThread
- Cancellation via atomic flag checked between pipeline steps
- No shared mutable state between threads
- Pipeline supports partial results: completed steps' outputs are preserved on failure

---

## 6. Directory Structure

```
karstlab/
├── src/
│   ├── karstlab/
│   │   ├── __init__.py
│   │   ├── main.py                     # Entry point, QApplication setup
│   │   ├── config.py                   # AnalysisParams dataclass, app constants
│   │   │
│   │   ├── presentation/               # GUI layer
│   │   │   ├── __init__.py
│   │   │   ├── main_window.py          # Map-centric layout
│   │   │   ├── sidebar.py              # Collapsible sidebar with tabs
│   │   │   ├── layers_tab.py           # Layer toggle controls
│   │   │   ├── results_tab.py          # Top 25 + full clickable results
│   │   │   ├── tools_tab.py            # Analysis params + run button
│   │   │   ├── markers_tab.py          # Marker management, GPX import/export
│   │   │   ├── export_tab.py           # Export controls + report
│   │   │   ├── guided_workflow.py      # Step-by-step beginner panel
│   │   │   ├── map_viewer.py           # QWebEngineView wrapper
│   │   │   ├── settings_dialog.py      # Preferences dialog
│   │   │   ├── shortcuts_dialog.py     # Keyboard shortcuts reference
│   │   │   ├── progress_dialog.py      # DAG pipeline progress
│   │   │   └── styles.py               # Dark mode QSS stylesheet
│   │   │
│   │   ├── business/                   # Business logic layer
│   │   │   ├── __init__.py
│   │   │   ├── pipeline_dag.py         # PipelineDAG orchestrator
│   │   │   ├── terrain.py              # TerrainAnalyzer
│   │   │   ├── hydrology.py            # HydrologyAnalyzer
│   │   │   ├── dolines.py              # DolineDetector + quality flags
│   │   │   ├── depression_ranker.py    # DepressionRanker (Top 25)
│   │   │   ├── contours.py             # ContourExtractor
│   │   │   ├── exporter.py             # KML/GeoJSON/GPX export
│   │   │   ├── report.py               # ReportGenerator
│   │   │   ├── map_builder.py          # MapBuilder (Folium)
│   │   │   ├── project.py              # ProjectManager + slug validation
│   │   │   ├── dem_validator.py        # Scientific DEMValidator
│   │   │   ├── land_profiles.py        # LandProfileManager
│   │   │   ├── markers.py              # MarkerManager
│   │   │   ├── poi.py                  # POIManager (BRGM, Spélébase)
│   │   │   └── update_checker.py       # UpdateChecker
│   │   │
│   │   ├── data/                       # Data access layer
│   │   │   ├── __init__.py
│   │   │   ├── raster_io.py            # GeoTIFF read/write
│   │   │   ├── vector_io.py            # Vector format conversions
│   │   │   ├── crs.py                  # CRS detection & transformation
│   │   │   ├── vrt_builder.py          # GDAL VRT + GeoTIFF assembly
│   │   │   ├── kml_importer.py         # KML import for POI data
│   │   │   └── gpx_importer.py         # GPX import for markers
│   │   │
│   │   ├── infrastructure/             # External tool adapters
│   │   │   ├── __init__.py
│   │   │   ├── whitebox_adapter.py     # WhiteboxTools wrapper
│   │   │   ├── folium_adapter.py       # Folium map configuration
│   │   │   ├── http_server.py          # Local HTTP server
│   │   │   ├── schema_validator.py     # Pydantic models + JSON Schema
│   │   │   ├── provenance.py           # ProvenanceCollector
│   │   │   ├── env_bootstrap.py        # PROJ/GDAL path setup
│   │   │   └── log_manager.py          # Structured file logging
│   │   │
│   │   └── schemas/                    # Canonical Pydantic models
│   │       ├── __init__.py
│   │       ├── analysis_params.py      # AnalysisParams model
│   │       ├── project_schema.py       # ProjectFile model
│   │       ├── settings_schema.py      # UserSettings model
│   │       ├── land_profile_schema.py  # LandProfile model
│   │       └── result_metadata.py      # ResultMetadata + provenance
│   │
│   └── resources/
│       ├── icons/
│       │   ├── app-icon.icns           # macOS icon
│       │   ├── app-icon.ico            # Windows icon
│       │   └── app-icon.png            # Source icon
│       ├── templates/
│       │   ├── report.html.j2          # Jinja2 report template
│       │   └── profile.html.j2         # Altitude profile template
│       ├── translations/
│       │   ├── karstlab_nl.ts          # Dutch translations
│       │   ├── karstlab_fr.ts          # French translations
│       │   └── karstlab_en.ts          # English translations
│       ├── schemas/
│       │   ├── land_profile.schema.json   # JSON Schema for land profiles
│       │   ├── project.schema.json        # JSON Schema for project files
│       │   └── settings.schema.json       # JSON Schema for settings
│       └── regions/                    # Land profiles
│           ├── fr.json
│           ├── nl.json
│           ├── be.json
│           ├── generic.json
│           └── README.md               # How to contribute new profiles
│
├── tests/
│   ├── unit/
│   │   ├── test_terrain.py
│   │   ├── test_hydrology.py
│   │   ├── test_dolines.py
│   │   ├── test_dolines_max_area.py    # Max area filtering
│   │   ├── test_depression_ranker.py   # Top 25 ranking
│   │   ├── test_contours.py
│   │   ├── test_exporter.py
│   │   ├── test_gpx_import_export.py   # GPX round-trip
│   │   ├── test_numbered_markers.py    # Numbered map markers
│   │   ├── test_raster_io.py
│   │   ├── test_vector_io.py
│   │   ├── test_crs.py
│   │   ├── test_dem_validator.py
│   │   ├── test_land_profiles.py       # Schema validation
│   │   ├── test_project_schema.py      # Project migration/versioning
│   │   ├── test_pipeline_cache.py      # Cache invalidation
│   │   └── test_slug_validation.py     # Project name slugging
│   ├── integration/
│   │   ├── test_pipeline.py
│   │   ├── test_pipeline_rerun.py      # Rerun-from-failed
│   │   └── test_map_builder.py
│   └── fixtures/
│       ├── sample_dem_small.tif        # Small test DEM
│       ├── sample_profile.json         # Test land profile
│       └── expected_outputs/
│
├── build/
│   ├── macos/
│   │   └── karstlab.spec               # PyInstaller spec for macOS
│   └── windows/
│       └── karstlab.spec               # PyInstaller spec for Windows
│
├── pyproject.toml                      # Project config, dependencies
├── requirements.txt                    # Pinned dependencies
└── Makefile                            # Build, test, translate commands
```

---

## 7. Technology Stack

### 7.1 Core Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| Python | 3.12+ | Runtime |
| PySide6 | 6.7+ | GUI framework (LGPL) |
| rasterio | 1.3+ | GeoTIFF I/O, hillshade, contours |
| pyproj | 3.6+ | CRS transformations |
| shapely | 2.0+ | Geometry operations |
| geopandas | 0.14+ | Vector data handling |
| numpy | 1.26+ | Array operations |
| scipy | 1.11+ | Curvature computation, morphological analysis |
| scikit-image | 0.22+ | Labeling, morphological operations for doline polygonization |
| whitebox | 2.3+ | Hydrological analysis (DEM fill, flow, streams) |
| folium | 0.15+ | Interactive maps |
| branca | 0.7+ | Folium dependency |
| simplekml | 1.3+ | KML export |
| gpxpy | 1.6+ | GPX export/import |
| jinja2 | 3.1+ | HTML templating |
| matplotlib | 3.8+ | Elevation profiles, static map image for report |
| pydantic | 2.5+ | Schema validation for settings, projects, land profiles |

### 7.2 Removed from Earlier Design

| Library | Reason for Removal |
|---------|--------------------|
| RichDEM | Slope/curvature achievable with rasterio + scipy + GDAL; see TD-04 in tech decisions |

### 7.3 Build & Development

| Tool | Purpose |
|------|---------|
| PyInstaller | Application bundling |
| pytest | Testing |
| pytest-cov | Coverage |
| ruff | Linting + formatting |
| mypy | Type checking |
| Qt Linguist | Translation management |

---

## 8. Cross-Platform Strategy

### 8.1 Platform Differences

| Concern | macOS | Windows |
|---------|-------|---------|
| App data dir | `~/.karstlab/` | `%APPDATA%/KarstLab/` |
| Logs dir | `~/.karstlab/logs/` | `%APPDATA%/KarstLab/logs/` |
| Temp dir | `$TMPDIR` | `%TEMP%` |
| WhiteboxTools binary | `whitebox_tools` (unix) | `whitebox_tools.exe` |
| PROJ/GDAL data | Bundled via PyInstaller | Bundled via PyInstaller |
| App icon | `.icns` | `.ico` |
| Packaging | `.dmg` via `create-dmg` | `.exe` via NSIS or Inno Setup |
| File paths | POSIX (`/`) | Win32 (`\`) — use `pathlib` |

### 8.2 Platform Abstraction

All platform-specific logic is isolated in `infrastructure/env_bootstrap.py`:

```python
# Pseudocode — actual implementation uses pathlib.Path
def app_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / ".karstlab"
    elif sys.platform == "win32":
        return Path(os.environ["APPDATA"]) / "KarstLab"

def logs_dir() -> Path:
    return app_data_dir() / "logs"

def whitebox_executable() -> Path:
    name = "whitebox_tools.exe" if sys.platform == "win32" else "whitebox_tools"
    return bundled_tools_dir() / name
```

---

## 9. Internationalization Architecture

### 9.1 Qt Linguist Workflow

```
Source Code                       Translation Files              Compiled
───────────                       ─────────────────              ────────
self.tr("Analyze")         ──►    karstlab_nl.ts (XML)    ──►   karstlab_nl.qm
self.tr("Export KML")      ──►    karstlab_fr.ts (XML)    ──►   karstlab_fr.qm
self.tr("New project")     ──►    karstlab_en.ts (XML)    ──►   karstlab_en.qm
                                         │
                                 Qt Linguist GUI
                                 (translator tool)
```

### 9.2 Translation Scope

| Scope | Method |
|-------|--------|
| GUI labels, buttons, menus | `self.tr()` + Qt Linguist |
| Pipeline log messages | `self.tr()` in orchestrator |
| Report content | Jinja2 templates with i18n context |
| Map layer names | Passed as translated strings to Folium |
| Error messages | `self.tr()` in presentation layer |
| File dialogs | Qt auto-translates with QTranslator |
| Land profile names | Translated strings from region JSON |

### 9.3 Language Switching

```
User selects language in Settings
        │
        ▼
SettingsDialog saves locale to config
        │
        ▼
App restarts with new QTranslator loaded
        │
        ▼
All self.tr() calls resolve to new language
```

Language change requires application restart (standard Qt pattern).

---

## 10. Canonical Settings Schema

### 10.1 Analysis Parameters (shared across all config levels)

The following parameter names are canonical and used identically in `settings.json`, `project.karstlab`, and land profile `analysis_defaults`:

```json
{
  "contour_interval_m": 5.0,
  "doline_min_depth_m": 0.25,
  "doline_max_depth_m": 40.0,
  "doline_min_area_m2": 1.0,
  "doline_max_area_m2": 60000.0,
  "stream_threshold_cells": 1000
}
```

**ARIS-compatible French preset** (matches ARIS Lidar Prospector V3d defaults):
- `contour_interval_m`: 5.0
- `doline_min_depth_m`: 0.25
- `doline_max_depth_m`: 40.0
- `doline_min_area_m2`: 1.0
- `doline_max_area_m2`: 60000.0
- `stream_threshold_cells`: 1000

### 10.2 Settings Hierarchy

Settings are resolved in the following priority order (lowest to highest — highest priority last overrides lower):

```
1. Built-in defaults (hardcoded in config.py)
   ↓
2. Land Profile defaults (regions/{id}.json → analysis_defaults)
   ↓
3. User Settings (~/.karstlab/settings.json)
   ↓
4. Project Settings (project_dir/project.karstlab → analysis_params)
   ↓
5. Per-Run UI Overrides (sidebar parameter fields, e.g., Tools Tab input)
```

**Resolution order**: For any parameter, check levels 5→1 in reverse, stop at first match.
- Level 5 (UI) overrides everything
- Level 4 (Project) overrides Levels 1-3
- Level 3 (User) overrides Levels 1-2
- Level 2 (Land Profile) overrides Level 1
- Level 1 (Hardcoded) is the fallback

### 10.3 User Settings Schema (settings.json)

```json
{
  "schema_version": "1.0.0",
  "language": "nl",
  "land_profile": "nl",
  "crs_override": null,
  "analysis_params": {
    "contour_interval_m": 5.0,
    "doline_min_depth_m": 1.0,
    "doline_max_depth_m": 100.0,
    "doline_min_area_m2": 10.0,
    "doline_max_area_m2": 100000.0,
    "stream_threshold_cells": 1000
  },
  "whitebox_path": null,
  "update_check": true,
  "large_dem_threshold_mb": 500,
  "last_project_dir": null,
  "recent_projects": [],
  "window_geometry": null,
  "sidebar_width": 400,
  "sidebar_position": "right"
}
```

---

## 11. UI Design

### 11.1 Design System

**Color Palette** (dark mode):
- Base background: `#1a1f2e` (dark charcoal)
- Terracotta accent (doline features): `#c75d4a`
- Water accent (streams): `#4a90d9`
- Text primary: `#e8e8e8`
- Text secondary: `#a8a8a8`

**Typography**:
- Font: Geist Sans
- Primary sizes: 14px (body), 16px (labels), 20px (titles)

### 11.2 Layout Architecture

**Map-Centric Design**:
- Map occupies ~70% of main window
- Collapsible sidebar (~30%) slides from right or left (configurable)
- Five sidebar tabs: Layers, Results, Tools, Markers, Export
- Update banner slides in at top (dismissible)

**Sidebar Tabs**:

1. **Layers Tab** — Toggle visibility of:
   - Raw LiDAR MNT
   - Hillshade
   - Slope
   - Contours
   - Streams
   - Dolines (depression polygons)
   - Tile boundary grid
   - Imported KML/GPX
   - Base map layers (from land profile)

2. **Results Tab**:
   - Top 25 deepest depressions (ranked table: ID, depth, area, lat/lon)
   - Full scrollable doline list (clickable → zooms map)
   - Summary statistics at top (count, avg depth, total area)
   - Sort options (depth, area, location)
   - Quality flag indicators per depression

3. **Tools Tab** — Analysis parameters:
   - Contour interval (m) — `contour_interval_m`
   - Doline depth min/max (m) — `doline_min_depth_m`, `doline_max_depth_m`
   - Doline area min/max (m²) — `doline_min_area_m2`, `doline_max_area_m2`
   - Stream accumulation threshold — `stream_threshold_cells`
   - "Analyze" button
   - Land profile selector
   - DEM file selection

4. **Markers Tab**:
   - Marker list (all project markers)
   - Manual marker placement toggle
   - GPS coordinate entry (lat/lon)
   - Import GPX / Import KML buttons
   - Export markers to GPX button

5. **Export Tab** — Export controls:
   - KML export
   - GeoJSON export
   - GPX export (top depressions)
   - Report generation
   - Statistics JSON export

---

## 12. Project Structure on Disk

### 12.1 Project Directory Layout

```
my-analysis/
├── project.karstlab                  # JSON metadata + parameters + provenance
├── input/
│   ├── tile_001.tif                  # Original DEM tiles
│   ├── tile_002.tif
│   ├── assembled_dem.vrt             # VRT mosaic (auto-generated)
│   ├── assembled_dem.tif             # Combined GeoTIFF (optional)
│   └── markers.gpx                   # Imported markers
├── output/
│   ├── rasters/
│   │   ├── hillshade.tif
│   │   ├── slope.tif
│   │   ├── curvature.tif
│   │   ├── flow_accum.tif
│   │   ├── dem_filled.tif
│   │   └── streams.tif
│   ├── vectors/
│   │   ├── dolines.geojson
│   │   ├── dolines.kml
│   │   ├── contours.geojson
│   │   ├── contours.kml
│   │   └── streams.geojson
│   └── export/
│       ├── dolines.kml
│       ├── dolines.geojson
│       ├── Top_Depressions_my-analysis.gpx
│       ├── my-analysis_markers.gpx
│       ├── statistics.json
│       └── report.html
├── map/
│   └── index.html                    # Interactive Folium map
└── logs/
    └── session_20260528_120000.log
```

### 12.2 project.karstlab Schema

```json
{
  "schema_version": "1.0.0",
  "pipeline_version": "1.0.0",
  "analysis_run_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Trou du Vent Analysis",
  "slug": "trou-du-vent-analysis",
  "land_profile": "fr",
  "dem_path": "input/assembled_dem.tif",
  "created": "2026-05-28T12:00:00Z",
  "modified": "2026-05-28T14:30:00Z",
  "crs_analysis": "EPSG:2154",
  "crs_display": "EPSG:4326",
  "analysis_params": {
    "contour_interval_m": 5.0,
    "doline_min_depth_m": 0.25,
    "doline_max_depth_m": 40.0,
    "doline_min_area_m2": 1.0,
    "doline_max_area_m2": 60000.0,
    "stream_threshold_cells": 1000
  },
  "dem_info": {
    "crs_original": "EPSG:2154",
    "bounds": [0.5, 44.7, 1.0, 44.9],
    "resolution_m": 1.0,
    "data_type": "float32",
    "tile_count": 6
  },
  "results": {
    "depressions_count": 342,
    "depressions_total_area_m2": 45000,
    "top_25": [
      {
        "rank": 1,
        "depth_m": 12.4,
        "area_m2": 850.0,
        "lat": 44.812,
        "lon": 0.987,
        "quality_flags": ["high_confidence"]
      }
    ],
    "contours_count": 850,
    "streams_length_m": 125000,
    "processing_time_seconds": 145,
    "completion_status": "success"
  },
  "pipeline_results": [
    {
      "step_name": "validate",
      "status": "completed",
      "error_message": null,
      "duration_s": 0.3
    },
    {
      "step_name": "assemble_reproject",
      "status": "completed",
      "error_message": null,
      "duration_s": 2.1
    },
    {
      "step_name": "doline_detection",
      "status": "completed",
      "error_message": null,
      "duration_s": 12.5
    }
  ],
  "markers": [
    {
      "id": "marker_001",
      "name": "Survey Point A",
      "lat": 44.8123,
      "lon": 0.9876,
      "source": "manual",
      "created_at": "2026-05-28T12:15:00Z"
    },
    {
      "id": "marker_002",
      "name": "Cave Entrance",
      "lat": 44.8145,
      "lon": 0.9901,
      "source": "gpx_import",
      "created_at": "2026-05-28T12:20:00Z"
    }
  ],
  "poi_cache": {
    "brgm_cavites": {
      "source_id": "brgm_cavites",
      "department": "46",
      "fetched_at": "2026-05-28T12:00:00Z",
      "feature_count": 23
    },
    "spelebase": {
      "source_id": "spelebase",
      "department": "46",
      "fetched_at": "2026-05-28T12:01:00Z",
      "feature_count": 8
    }
  },
  "statistics": {
    "total_dolines": 342,
    "avg_depth_m": 3.2,
    "max_depth_m": 12.4,
    "min_depth_m": 0.25,
    "total_area_m2": 45000.0,
    "avg_area_m2": 131.6,
    "top_25": [
      {"rank": 1, "depth_m": 12.4, "area_m2": 850.0},
      {"rank": 2, "depth_m": 11.8, "area_m2": 720.0}
    ],
    "provenance": {
      "app_version": "1.0.0",
      "gdal_version": "3.9.1",
      "proj_version": "9.4.1",
      "whitebox_version": "2.4.0",
      "python_version": "3.12.4"
    }
  },
  "provenance": {
    "app_version": "1.0.0",
    "pipeline_version": "1.0.0",
    "run_timestamp": "2026-05-28T14:02:01Z",
    "run_duration_seconds": 145,
    "input": {
      "dem_path": "input/assembled_dem.tif",
      "sha256": "a1b2c3...",
      "size_bytes": 60817408,
      "mtime": "2026-05-28T13:55:00Z"
    },
    "land_profile": {
      "id": "fr",
      "version": "1.0.0",
      "sha256": "d4e5f6..."
    },
    "params_hash": "7a8b9c...",
    "tool_versions": {
      "python": "3.12.4",
      "gdal": "3.9.1",
      "proj": "9.4.1",
      "rasterio": "1.3.10",
      "whitebox_tools": "2.4.0",
      "pyside6": "6.7.2",
      "folium": "0.17.0"
    },
    "steps": [
      {
        "name": "validate",
        "status": "completed",
        "duration_seconds": 0.3,
        "warnings": ["Vertical datum not specified in DEM metadata"]
      },
      {
        "name": "assemble",
        "status": "completed",
        "duration_seconds": 2.1,
        "output_files": ["input/assembled_dem.tif"]
      }
    ],
    "quality_summary": {
      "depressions_total": 342,
      "depressions_high_confidence": 280,
      "depressions_edge_flagged": 12,
      "depressions_nodata_adjacent": 5
    }
  }
}
```

**Schema Versioning & Migration:**

- `schema_version`: Tracks the project file format version for forward compatibility
- `pipeline_version`: Tracks the pipeline logic version — if current version differs from stored version, all cached results are invalidated and re-analysis is required
- `analysis_run_id`: UUID uniquely identifying this analysis run for provenance and reproducibility tracking
- `crs_analysis` and `crs_display`: Document the metric CRS used for analysis and the display CRS (always WGS84)
- `pipeline_results`: Per-step status and duration for transparency into which steps completed/failed
- `markers`: All user-created or imported markers with metadata (source: manual, gpx_import, kml_import)
- `poi_cache`: Cached POI sources (BRGM, Spélébase) with fetch timestamp to avoid redundant downloads
- `statistics`: Analysis summary with provenance for reports and user-facing displays

**Migration strategy:**
- On project load, if `pipeline_version` differs from the current pipeline version, log a warning
- All cached results (`output/` directory) are invalidated; re-analysis is required before exports/reports can be generated
- User is prompted: "Pipeline updated — re-analysis required" with a one-click "Re-analyze" button

---

## 13. Error Handling Strategy

### 13.1 Error Categories

| Category | Example | Handling |
|----------|---------|----------|
| **Validation error** | Invalid DEM format, wrong CRS, DSM instead of DEM | Upfront validation, translated message with remediation |
| **Validation warning** | Missing vertical datum, edge artifacts detected | Warning dialog, user can proceed or cancel |
| **User error** | Invalid parameters, wrong file | Translated message dialog |
| **Processing error** | WhiteboxTools fails, memory limit | Translated error + log details, partial results preserved |
| **Infrastructure error** | Missing PROJ data, no disk space | Startup check + clear message |
| **Network error** | WMS tile timeout, GitHub check timeout | Graceful degradation, offline tiles, silent failure on update check |

### 13.2 Error Flow

```
Business layer raises typed exception
        │
        ▼
Presentation layer catches, translates message
        │
        ▼
QMessageBox with user-friendly translated text
        │
        ├─► Option: "View Log" button opens log viewer
        │
        ▼
Detailed error written to structured log file
        │
        ▼
LogManager maintains rotation (keep 5 recent session logs)
```

---

## 14. Land Profile System

### 14.1 Purpose

Land profiles encapsulate region-specific defaults:
- Default metric CRS (e.g., Lambert 93 for France)
- Common alternative CRS options
- Default analysis parameters (using canonical parameter names)
- Recommended DEM sources (with links)
- Map layer configuration (base maps, overlays)
- POI data sources (with departmental filtering support)
- Localized names

### 14.2 Validation

Land profiles are validated at load time against:
1. JSON Schema (`resources/schemas/land_profile.schema.json`)
2. Pydantic model (`schemas/land_profile_schema.py`)

Invalid profiles produce a clear error message and fall back to the generic profile.

See [07-land-profiles.md](./07-land-profiles.md) for full schema and examples.

---

## 15. Update Checker System

### 15.1 Update Check Flow

```
App startup
        │
        ▼
UpdateChecker.check_github_releases()
        │
        ├─► Query: GET /repos/<owner>/KarstLab/releases/latest
        │   (non-blocking, silent failure on timeout)
        │
        ├─ Compare app version vs latest release tag
        │
        ├─ If newer available:
        │  └─► Show dismissible banner at top of MainWindow
        │      "Version X.Y.Z available. Download"
        │
        └─ If up-to-date or network error: no banner
```

### 15.2 Update Check Settings

Users can disable update checks in Settings dialog:
- Checkbox: "Check for updates on startup" (default: enabled)
- Disabled checks don't show banner, no network request

---

## 16. Logging Architecture

### 16.1 Log Files

Structured logging to `~/.karstlab/logs/`:

```
~/.karstlab/logs/
├── session_20260528_140000.log
├── session_20260528_150000.log
├── session_20260528_160000.log
├── session_20260528_170000.log
└── session_20260528_180000.log        # Oldest deleted on rotation
```

**Rotation policy**: Keep 5 most recent session logs; oldest deleted when new session created.

### 16.2 Log Format

```
2026-05-28 14:00:00 | INFO | KarstLab v1.0.0 starting
2026-05-28 14:00:00 | INFO | GDAL 3.9.1 | PROJ 9.4.1 | WhiteboxTools 2.4.0
2026-05-28 14:00:01 | INFO | Configuration: land_profile=fr, language=fr
2026-05-28 14:02:01 | INFO | Pipeline started (11 steps, DAG mode)
2026-05-28 14:02:01 | INFO | Step 1/11: Validate DEM [COMPLETED] (0.3s, 1 warning)
2026-05-28 14:02:03 | INFO | Step 2/11: Assemble DEM [COMPLETED] (2.1s)
...
2026-05-28 14:04:26 | INFO | Step 8/11: Depression Ranking [COMPLETED] (0.5s, 342 depressions, top depth=12.4m)
...
2026-05-28 14:05:10 | INFO | Pipeline completed: 11/11 steps, 145s total
2026-05-28 14:05:10 | INFO | Provenance hash: abc123...
```

---

## 17. Performance Considerations

### 17.1 Large DEM Handling

For DEMs larger than `large_dem_threshold_mb` (default 500 MB):
- Use windowed/chunked processing in RasterIO
- Process in tiles to avoid loading entire DEM into memory
- Relevant for terrain analysis (hillshade, slope, curvature)
- Hydrology analysis (WhiteboxTools) handles large files natively

### 17.2 Multi-Tile DEM Assembly

For multi-tile input (e.g., separate GeoTIFF files per tile):
- VRTBuilder creates GDAL Virtual Raster (VRT) mosaic
- VRT has zero memory footprint, references original files
- Optional: export assembled DEM as single GeoTIFF (`input/assembled_dem.tif`)
- Used by all downstream analysis steps

### 17.3 Pipeline Cache

The DAG engine caches step outputs:
- Completed step outputs saved to `output/rasters/` and `output/vectors/`
- Provenance metadata tracks input hash, parameter hash, step status
- On parameter change: only invalidated downstream steps re-run
- On DEM change: all steps re-run from assembly onward
- Enables iterative debugging without full re-processing

---

## 18. Security & Data Privacy

### 18.1 Data Handling

- No cloud upload of user data (all processing local)
- DEM and analysis results stored in user-controlled project directory
- Settings stored in `~/.karstlab/settings.json` (user-readable JSON)
- Logs stored in `~/.karstlab/logs/` (file-based, local only)

### 18.2 Update Check Privacy

- Update check queries GitHub API (public endpoint, no authentication)
- No user data sent with update check
- Update check can be disabled in settings
- No telemetry or analytics

### 18.3 Sensitive Data in Logs

- Logs may contain file paths (project directories)
- Logs do not contain DEM pixel values or coordinates
- Errors include exception tracebacks (helpful for debugging)
- No passwords, API keys, or secrets logged
