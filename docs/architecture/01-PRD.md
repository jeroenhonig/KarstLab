# Product Requirements Document (PRD)
# KarstLab — Cross-Platform Terrain Analysis for Karst Regions

## 1. Product Overview

**Product Name:** KarstLab
**Version:** v1.0
**Type:** Desktop GIS application for karst terrain analysis (speleology, cave diving, geology)
**Heritage:** Functional rebuild of ARIS Lidar Prospector V3d with modern architecture

### 1.1 Problem Statement

Speleologists, karst researchers, and GIS professionals worldwide need a user-friendly, cross-platform tool to analyze Digital Elevation Models (DEMs) for karst terrain features (dolines, sinkholes, underground drainage patterns). Existing tools are either proprietary, platform-limited, or require extensive GIS expertise. KarstLab provides accessible, worldwide terrain analysis with modern multi-language UI and dark-mode design.

### 1.2 Solution

Build a new cross-platform desktop application that provides intuitive DEM-based terrain analysis with multi-language support (Dutch, French, English, expandable), runs natively on both macOS and Windows, and delivers a modern dark-mode interface with accessible keyboard shortcuts and visual feedback.

### 1.3 Target Users

- Speleologists and cave diving professionals worldwide
- Karst researchers and hydrogeologists
- GIS professionals analyzing terrain data
- Archaeological prospectors studying underground features
- Environmental consultants assessing land stability
- Educational institutions teaching karst geomorphology

### 1.4 Migration & Compatibility with ARIS Lidar Prospector V3d

KarstLab v1.0 rebuilds the core functionality of ARIS Lidar Prospector V3d (May 2026) on a modern, cross-platform stack. The following table summarizes what is replicated, what is improved, and what is deferred.

| ARIS V3d Feature | KarstLab v1.0 | Notes |
|------------------|---------------|-------|
| DEM loading (GeoTIFF) | Replicated | Same MNT/GeoTIFF input |
| Tile assembly (Assemblage Rasters) | Improved | VRT + GeoTIFF output, drag-and-drop |
| Analysis parameters (6 params) | Improved | Same 6 + `doline_max_area_m2`, land-profile presets |
| Fill-subtract doline detection | Replicated | Same algorithm |
| Top 25 deepest depressions | Replicated | Same ranking by max depth with ID, depth, area, lat/lon |
| GPX export of top depressions | Replicated | Auto-generated after analysis |
| Interactive webmap (Folium/Leaflet) | Improved | Same layer set + land-profile-driven overlays |
| Numbered depression markers on map | Replicated | Labels match Top 25 / results table |
| Layer controls (IGN, cadastre, BRGM, BDLISA, etc.) | Replicated | Configured per land profile |
| BRGM Cavités Géorisques import | Replicated | Departmental selection via POI panel |
| Spélébase CAVECENTER import | Replicated | Departmental selection via POI panel |
| KML import | Replicated | Same functionality |
| GPX import in webmap | Replicated | Load GPX markers into map |
| Marker panel (place, GPS entry, export GPX) | Replicated | Same marker workflow |
| Elevation profile tool | Replicated | Same cross-section functionality |
| Distance measurement tool | Replicated | Same 2-point measurement |
| GPS coordinate entry | Replicated | Lat/lon point placement |
| CRLF normalization (LF_CRLF tool) | Not needed | Python handles line endings natively |
| HTTP Downloader integration | Deferred v1.1 | v1.0 shows download links; future: batch helper |
| Windows-only deployment | Improved | macOS + Windows cross-platform |
| Single-language UI | Improved | Dutch, French, English |
| No project file format | Improved | Structured .karstlab JSON project files |

---

## 2. Functional Requirements

### 2.1 Project Management

| ID | Requirement | Priority |
|----|------------|----------|
| FR-01 | Create new analysis project with name and directory | Must |
| FR-02 | Open existing project and restore state | Must |
| FR-03 | Persist project settings as JSON (`project.karstlab`) with Pydantic validation | Must |
| FR-04 | Auto-detect and create work directories (input/, output/, export/) | Must |
| FR-05 | Automatic project name slugging (replace spaces, accents) with warning for legacy-incompatible characters | Must |
| FR-06 | Recent projects list in Tools tab | Should |

### 2.2 DEM Input & Preprocessing

| ID | Requirement | Priority |
|----|------------|----------|
| FR-10 | Load GeoTIFF DEM files | Must |
| FR-11 | Auto-detect and display CRS information | Must |
| FR-12 | Reproject DEM to metric CRS (configurable, default from land profile) | Must |
| FR-13 | Reproject results to WGS84 (EPSG:4326) for web display | Must |
| FR-14 | Multi-DEM tile assembly via GDAL VRT mosaic with optional GeoTIFF output (`input/assembled_dem.tif`) | Must |
| FR-15 | DEM input validation (see section 2.2.1) | Must |
| FR-16 | Display tile boundary grid as optional map overlay | Should |

#### 2.2.1 DEM Validation Checks

The following checks run before pipeline execution. Each produces an actionable, translated error message.

| Check | Description |
|-------|-------------|
| Format | Must be GeoTIFF (.tif/.tiff) |
| CRS | Must have a valid, detectable CRS; warn if geographic (non-metric) |
| Vertical unit/datum | Detect and warn if vertical unit is not meters or if vertical datum is missing |
| Data type | Must be numeric (float32/float64/int16/int32) |
| NoData | Must have NoData value set; warn about NoData coverage percentage |
| Resolution | Warn if resolution too coarse for minimum doline size detection; check consistency across bands |
| DEM vs DSM | Warn if file metadata or name suggests DSM instead of DEM/MNT |
| NoData gaps | Warn if large contiguous NoData regions exist (potential holes in coverage) |
| Edge artifacts | Warn if elevation values at raster edges are suspiciously uniform (possible fill artifacts) |
| Hydrological preprocessing | Warn if DEM appears already hydrologically conditioned (flat areas suggesting prior filling) |
| File size | Check against available disk space for all pipeline outputs |
| Resampling | Document recommended resampling method (bilinear for continuous elevation data) |

### 2.3 Terrain Analysis Pipeline

| ID | Requirement | Priority |
|----|------------|----------|
| FR-20 | Generate hillshade from DEM (configurable azimuth/altitude) | Must |
| FR-21 | Calculate slope in degrees | Must |
| FR-22 | Calculate curvature index | Must |
| FR-23 | Run hydrological analysis: DEM filling, D8 flow pointer, flow accumulation | Must |
| FR-24 | Extract stream network from flow accumulation (configurable `stream_threshold_cells`) | Must |
| FR-25 | Detect dolines/depressions with configurable depth min/max and area min/max filters | Must |
| FR-26 | Extract contour lines at configurable `contour_interval_m` | Must |
| FR-27 | Full pipeline execution with single "Analyze" action | Must |
| FR-28 | Progress reporting during pipeline execution (per-step progress with estimated time) | Must |
| FR-29 | Partial pipeline results on failure — retain completed steps, display clear error for failed step | Must |
| FR-30 | Pipeline modeled as DAG with step dependencies and cache invalidation (see architecture doc) | Must |

### 2.4 Interactive Map

| ID | Requirement | Priority |
|----|------------|----------|
| FR-40 | Display interactive Leaflet map with analysis results | Must |
| FR-41 | Base layers: Plan IGN (WMTS), OpenStreetMap, Esri World Imagery (configurable per land profile) | Must |
| FR-42 | Analysis overlays: raw LiDAR MNT, hillshade, contours, depressions, streams | Must |
| FR-43 | Reference overlays: geological map (BRGM 1/50k for France), cadastre, karst zones (BDLISA) — configurable per land profile | Should |
| FR-44 | Tile boundary grid overlay (optional, toggled in Layers tab) | Should |
| FR-45 | Imported KML/GPX data as map layer | Should |
| FR-46 | Numbered depression markers matching Top 25 / results table | Must |
| FR-47 | Distance measurement tool on map | Must |
| FR-48 | Elevation profile along user-drawn line | Must |
| FR-49 | Layer toggle controls with opacity sliders | Must |
| FR-50 | Clickable results panel: clicking a doline in results list zooms map to and highlights that feature | Must |

### 2.5 Results & Ranking

| ID | Requirement | Priority |
|----|------------|----------|
| FR-55 | Top 25 deepest depressions table, sorted by max depth | Must |
| FR-56 | Each ranked depression shows: rank/ID, max depth (m), area (m²), centroid lat/lon | Must |
| FR-57 | Numbered map markers corresponding to Top 25 ranks | Must |
| FR-58 | Full depression list (beyond Top 25) in scrollable results panel | Must |
| FR-59 | Confidence/quality flags per depression (see section 2.5.1) | Should |

#### 2.5.1 Depression Quality Flags

Each detected depression receives quality indicators:

| Flag | Description |
|------|-------------|
| `edge_proximity` | Depression polygon touches or is within N pixels of raster edge |
| `nodata_adjacent` | Depression borders NoData pixels |
| `depth_confidence` | Low/medium/high based on depth relative to DEM vertical precision |
| `shape_regularity` | Ratio of area to convex hull area (distinguishes natural dolines from artifacts) |
| `nested` | Depression is contained within a larger depression |

### 2.6 Point of Interest (POI) & Marker Management

| ID | Requirement | Priority |
|----|------------|----------|
| FR-60 | BRGM Cavités Géorisques as explicit French POI source with departmental selection | Must |
| FR-61 | Spélébase CAVECENTER as explicit French POI source with departmental selection | Must |
| FR-61a | BRGM & Spélébase API availability and fallback behavior (see section 2.6.1) | Must |
| FR-62 | KML import for existing POI data (known caves, reference points) | Should |
| FR-63 | GPX import for markers into map/project | Must |
| FR-64 | Manual marker placement on map by clicking | Must |
| FR-65 | GPS coordinate entry (lat/lon) for manual marker addition | Must |
| FR-66 | Marker list panel showing all project markers | Must |
| FR-67 | Export project markers to GPX file | Must |
| FR-68 | Configurable POI sources per land profile (WFS endpoints, static GeoJSON, departmental CSV) | Should |

#### 2.6.1 BRGM Cavités & Spélébase Availability and Fallback

**v1.0 Scope:** Both BRGM Cavités Géorisques and Spélébase CAVECENTER are Must-have for v1.0. The app fetches cave and cavity point-of-interest (POI) data from these sources and displays them as markers on the map.

**API Characteristics:**
- Both are free, public web APIs
- BRGM Cavités Géorisques requires no API key
- Spélébase CAVECENTER requires no API key
- Both support departmental filtering (French département number)

**Fallback Behavior:**
- **API Timeout:** If an API is unreachable or does not respond within 10 seconds, the app shows a user-friendly warning in the POI panel: "Could not reach [source name]. Check your internet connection and try again."
- **Cached Data:** Previously fetched data is cached per department in the project directory. If the API fails, the app automatically displays cached data if available, with a note showing the cache date (e.g., "Using cached data from 2026-05-15").
- **No Blocking:** POI fetch operations never block the rest of the application. Analysis, map rendering, and other features remain fully functional while POI data is being fetched or if fetch fails.
- **Offline Mode:** If no internet connection is available, the POI panels display either "Offline — cached data shown" (if cached data exists for the selected department) or "Offline — no cached data available" (if no cache exists). Users can proceed with analysis without POI data.

**Department Filtering:** Users select a French department number (01–95) via a dropdown in the POI panel. The app queries only that department's data, reducing load on external servers and improving fetch speed.

### 2.7 Export

| ID | Requirement | Priority |
|----|------------|----------|
| FR-70 | Export dolines as KML polygons | Must |
| FR-71 | Export contours as KML polylines | Must |
| FR-72 | Export dolines as GeoJSON | Must |
| FR-73 | Export contours as GeoJSON | Must |
| FR-74 | Auto-generate GPX of top depressions after analysis: `export/Top_Depressions_<project>.gpx` | Must |
| FR-75 | Export analysis statistics as JSON (with provenance metadata) | Must |
| FR-76 | Export assembled DEM as GeoTIFF (`input/assembled_dem.tif`) | Should |

### 2.8 Reporting

| ID | Requirement | Priority |
|----|------------|----------|
| FR-80 | Generate self-contained HTML report with KarstLab-branded dark-mode design | Must |
| FR-81 | Report contains: static map image (pre-rendered PNG, no external tile requests) | Must |
| FR-82 | Report contains: Top 25 deepest depressions table (sortable) | Must |
| FR-83 | Report contains: analysis parameters used with provenance metadata | Must |
| FR-84 | Report contains: summary statistics (doline count, area range, depth range, basin info) | Must |
| FR-85 | Localized report content based on selected language | Must |
| FR-86 | Report contains: quality flag summary for detected depressions | Should |

### 2.9 Project & Configuration Management

| ID | Requirement | Priority |
|----|------------|----------|
| FR-90 | Structured project directory with `.karstlab` JSON project file (Pydantic-validated) | Must |
| FR-91 | Land profiles as JSON configuration files validated against JSON Schema | Must |
| FR-92 | Configure per-profile: metric CRS, base DEM sources, WMS overlays, POI sources, analysis defaults | Must |
| FR-93 | Canonical settings schema shared across settings.json, project.karstlab, land profiles; settings resolved in priority order (per-run UI overrides → project settings → user settings → land profile defaults → built-in defaults) | Must |

### 2.10 Application Features

| ID | Requirement | Priority |
|----|------------|----------|
| FR-100 | Keyboard shortcuts for common actions: Ctrl+R=Run Analysis, Ctrl+E=Export, Tab=Switch panels | Should |
| FR-101 | Shortcuts help dialog accessible via Ctrl+? | Should |
| FR-102 | High-contrast mode toggle for accessibility | Should |
| FR-103 | Check-on-startup update notification via GitHub Releases API | Should |
| FR-104 | Built-in log viewer and "Copy Log" button in error dialogs for debugging | Should |
| FR-105 | Windowed/tiled processing for large DEMs above configurable threshold | Should |

### 2.11 Guided Workflow (Beginner Mode)

| ID | Requirement | Priority |
|----|------------|----------|
| FR-110 | Step-by-step guided workflow panel (collapsible, optional) replicating ARIS process | Should |
| FR-111 | Step 1: Links to official DEM sources for the active land profile (e.g., IGN LiDAR HD MNT for France) | Must |
| FR-112 | Step 2: Import DEM tiles — file picker or drag-and-drop into project input/ directory | Must |
| FR-113 | Step 3: Assemble tiles — one-click VRT + optional GeoTIFF assembly with progress | Must |
| FR-114 | Step 4: Configure analysis parameters (pre-filled from land profile) | Must |
| FR-115 | Step 5: Run analysis | Must |
| FR-116 | Step 6: View results in interactive map | Must |
| FR-117 | Future (v1.1): Optional helper for IGN download link-list import, CRLF normalization, batch download integration | Should |

### 2.12 Internationalization

| ID | Requirement | Priority |
|----|------------|----------|
| FR-120 | Support Dutch (nl), French (fr), English (en) | Must |
| FR-121 | Language selection in application preferences | Must |
| FR-122 | All UI strings translatable via Qt Linguist (`self.tr()` + `.ts`/`.qm` files) | Must |
| FR-123 | Report content translated per selected language | Must |
| FR-124 | Easy addition of new languages without code changes | Should |

---

## 3. Non-Functional Requirements

| ID | Requirement | Priority |
|----|------------|----------|
| NFR-01 | Native macOS application (.dmg installer) | Must |
| NFR-02 | Native Windows application (.exe installer) | Must |
| NFR-03 | App startup time < 5 seconds | Should |
| NFR-04 | Pipeline processing of 1 km² DEM < 60 seconds | Should |
| NFR-05 | Memory usage < 2 GB for typical DEM (1 km²) | Should |
| NFR-06 | Offline operation (no internet required for core analysis) | Must |
| NFR-07 | Internet only for map tile loading and WMS overlays | Must |
| NFR-08 | Application size < 500 MB bundled | Should |
| NFR-09 | Settings stored as JSON in ~/.karstlab/ (macOS) or %APPDATA%/KarstLab/ (Windows) | Must |
| NFR-10 | Structured file logging with rotation (keep last 5 sessions max, 10 MB per log) | Must |
| NFR-11 | Python 3.12+ runtime target for analysis backend | Must |
| NFR-12 | Settings persistence between sessions | Must |
| NFR-13 | Graceful error handling with user-friendly messages | Must |
| NFR-14 | Modern dark-mode UI design throughout application | Must |
| NFR-15 | All configuration files (settings, project, land profiles) validated via Pydantic models | Must |
| NFR-16 | Full provenance metadata in analysis outputs (see architecture doc section on provenance) | Must |

---

## 4. Out of Scope (v1.0)

- Linux support (can be added in future version)
- Point cloud (LAS/LAZ) processing — input is GeoTIFF DEM only
- Batch/automated processing of multiple projects
- Cloud/server-based processing or remote analysis
- User accounts, project sharing, or collaboration features
- Custom user-defined WMS/WMTS layer configuration (must use land profiles)
- 3D visualization of terrain
- Custom tile caching beyond browser cache mechanism
- Machine learning-based doline detection (future version)
- Auto-update or delta patches (manual download via GitHub Releases)
- Full WCAG 2.1 AA accessibility compliance (high-contrast mode is a start)
- Automated DEM download/batch download (v1.0 provides links to official sources; download helper deferred to v1.1)
