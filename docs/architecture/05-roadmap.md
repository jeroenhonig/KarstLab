# KarstLab Roadmap

## Migration from ARIS Lidar Prospector V3d

KarstLab v1.0 is a functional rebuild of ARIS Lidar Prospector V3d (May 2026) on a modern, cross-platform stack. See [01-PRD.md §1.4](./01-PRD.md) for the full migration/compatibility table. Key changes:

| Area | ARIS V3d | KarstLab v1.0 |
|------|----------|---------------|
| Platform | Windows-only | macOS + Windows |
| GUI framework | tkinter | PySide6 (LGPL), dark mode |
| Language | Single (French) | Dutch, French, English |
| Pipeline | Linear | DAG with cache invalidation |
| Validation | Basic | 12 scientific DEM checks |
| Config | Hardcoded | Pydantic-validated JSON (settings, projects, land profiles) |
| Quality | None | 5 depression quality flags |
| Provenance | None | Full reproducibility metadata |

All core ARIS functionality is replicated or improved in v1.0. Features explicitly deferred to v1.1 or later are listed in the Archived Decisions table below.

---

## v1.0 Completeness Checklist

Every ARIS Lidar Prospector V3d feature must be replicated, improved, or explicitly deferred. This checklist tracks parity:

| # | ARIS V3d Feature | KarstLab v1.0 Status | Reference |
|---|-----------------|---------------------|-----------|
| 1 | DEM file loading | ✅ Replicated + improved (multi-tile VRT assembly) | FR-01–FR-05 |
| 2 | Hillshade generation | ✅ Replicated | FR-10 |
| 3 | Slope analysis | ✅ Replicated | FR-11 |
| 4 | Contour generation | ✅ Replicated | FR-12 |
| 5 | Stream network extraction | ✅ Replicated | FR-13 |
| 6 | Fill-subtract doline detection | ✅ Replicated + improved (quality flags) | FR-20–FR-25 |
| 7 | Depth/area filtering | ✅ Replicated + improved (min AND max bounds) | FR-21–FR-22 |
| 8 | Depression ranking (Top 25) | ✅ Replicated + improved (quality flags) | FR-30 |
| 9 | Interactive map with overlays | ✅ Replicated + improved (Folium/Leaflet) | FR-40–FR-49 |
| 10 | KML export | ✅ Replicated | FR-70 |
| 11 | GeoJSON export | ✅ Replicated | FR-71 |
| 12 | GPX export | ✅ Replicated + improved (auto-generated) | FR-72 |
| 13 | Manual marker placement | ✅ Replicated | FR-50 |
| 14 | GPS coordinate entry | ✅ Replicated | FR-51 |
| 15 | GPX/KML import | ✅ Replicated | FR-52–FR-53 |
| 16 | BRGM Cavités integration | ✅ Replicated + improved (caching, fallback) | FR-60 |
| 17 | Spélébase integration | ✅ Replicated + improved (caching, fallback) | FR-61 |
| 18 | Distance measurement tool | ✅ Replicated | FR-45 |
| 19 | HTML report generation | ✅ Replicated + improved (self-contained, dark mode) | FR-80 |
| 20 | Parameter configuration | ✅ Replicated + improved (5-level settings hierarchy) | FR-90–FR-93 |
| 21 | DEM batch download links | ⏳ Deferred to v1.1 | Roadmap v1.1 |
| 22 | French language UI | ✅ Replicated + improved (+ Dutch, English) | FR-100 |

**Gate:** All ✅ items must pass acceptance tests before v1.0 release. No item may be removed from this list without adding it to the Archived Decisions table with rationale.

---

## v1.0 — Initial Release

Summary of v1.0 scope (reference [01-PRD.md](./01-PRD.md) and [02-architecture.md](./02-architecture.md) for details):

**Core Analysis**
- Full terrain analysis pipeline: hillshade, slope, curvature, hydrology, dolines, contours
- Fill-subtract doline detection with depth and area filtering (min + max bounds)
- Depression ranking: Top 25 deepest depressions with quality flags
- Pipeline modeled as DAG with step dependencies, cache invalidation, and rerun-from-failed
- Scientific DEM validation (12 checks including vertical unit, DSM detection, edge artifacts)
- Provenance metadata for reproducibility (versions, input hash, parameter hash, per-step timings)

**Interactive Map**
- Folium/Leaflet map with land-profile-based layers (base maps, overlays, WMS/WMTS)
- Numbered depression markers matching Top 25 ranks
- Analysis overlays: hillshade, slope, contours, streams, dolines
- Reference overlays: geological maps, cadastre, karst zones (per land profile)
- Tile boundary grid overlay for multi-tile DEMs
- Distance measurement tool and elevation profile tool
- Layer toggle controls with opacity sliders

**Data & Export**
- Multi-tile DEM assembly via GDAL VRT with optional GeoTIFF output
- Export: KML, GeoJSON, GPX, statistics JSON (with provenance)
- Auto-generated GPX of top depressions after analysis
- KML and GPX import for existing data
- Marker management: manual placement, GPS coordinate entry, GPX/KML import/export

**POI Sources**
- BRGM Cavités Géorisques (French caves, departmental filtering)
- Spélébase CAVECENTER (community speleological database, departmental filtering)
- Configurable POI sources per land profile

**User Experience**
- Modern dark-mode PySide6 UI with map-centric layout (70% map, 30% sidebar)
- Five sidebar tabs: Layers, Results, Tools, Markers, Export
- Guided beginner workflow (6-step panel matching ARIS process)
- Multi-language support: Dutch, French, English (Qt Linguist)
- Land profiles: pre-configured for France, Netherlands, Belgium + generic worldwide
- Self-contained HTML report with dark-mode styling, sortable table, static map image
- Keyboard shortcuts with help dialog
- High-contrast mode toggle
- Update notification via GitHub Releases API

**Distribution**
- macOS (.dmg) and Windows (.exe) installers via PyInstaller
- All config validated via Pydantic + JSON Schema

---

## v1.1 — Community & Polish

**Target release**: TBD

- **DEM download helper**: Optional batch download integration for IGN link-lists; CRLF normalization no longer needed (Python handles natively)
- **Additional land profiles**: Community-contributed profiles for Germany, Spain, Slovenia, and other karst regions
- **Performance optimization**: Large DEM handling (50+ km²) with streaming and incremental analysis
- **Batch processing**: Run analysis sequentially on multiple DEMs with consolidated reporting
- **Map bookmarks**: Save and restore map view states (center, zoom, visible layers)
- **Custom color ramps**: User-defined color schemes for terrain layers (slope, curvature, etc.)
- **Improved elevation profile**: Area-under-curve calculation, image export for reports

---

## v1.2 — Advanced Detection

**Target release**: TBD

- **Machine learning doline detection**: Trained models for automated sinkhole identification (see [03-tech-decisions.md](./03-tech-decisions.md) TD-03)
- **Doline classification**: Type identification (solution, collapse, suffosion) based on morphology
- **Depression hierarchy analysis**: Nested doline trees and parent-child relationships
- **Statistical analysis**: Doline density maps, spatial distribution patterns, clustering metrics
- **Comparison mode**: Overlay dolines from different time periods to track temporal changes

---

## v2.0 — Platform Expansion

**Target release**: TBD

- **Linux support**: .AppImage or .deb distribution for Linux users
- **Plugin architecture**: Third-party analysis module system with stable internal APIs
- **Custom WMS/WMTS layers**: User-configurable remote tile and feature service integration
- **3D visualization**: Terrain and doline representation using pyvista or similar libraries
- **Point cloud preprocessing**: LAS/LAZ input with DEM generation from raw LiDAR data
- **Auto-update mechanism**: Sparkle (macOS) / WinSparkle (Windows) with code signing
- **Cloud processing**: Offload large datasets to cloud infrastructure for analysis
- **Collaborative features**: Project sharing, annotations, and profile collaboration workflows

---

## v2.1 — Advanced GIS

**Target release**: TBD

- **Custom tile caching**: Download and cache tiles for offline field work
- **Field mode**: Simplified UI optimized for tablet and touch interaction
- **GPS integration**: Real-time position overlay on map with accuracy indicator
- **Photo geotagging**: Attach field photos to map locations with metadata preservation
- **Multi-DEM time-series analysis**: Track terrain changes across temporal datasets

---

## Feature Requests & Contributions

- **Land profiles**: Submit new regional profiles via GitHub Pull Request (see [07-land-profiles.md](./07-land-profiles.md))
- **Feature requests**: Open an issue on [GitHub Issues](https://github.com/)
- **Translations**: New languages can be added via Qt Linguist (.ts files) and submitted as PRs
- **Bug reports**: Include DEM sample, OS version, and steps to reproduce

---

## Archived Decisions

Features considered but deferred, with rationale:

| Feature | Deferred to | Reason |
|---------|-------------|--------|
| HTTP Downloader / DEM batch download | v1.1 | v1.0 shows download links to official sources; batch helper adds complexity |
| ML doline detection | v1.2 | Requires training data collection and validation; fill-subtract algorithm proven sufficient for v1.0 |
| 3D visualization | v2.0 | Significant new dependency (pyvista/VTK); not core to analysis workflow |
| Point cloud processing | v2.0 | Entirely different input pipeline and tooling; DEM-focused for v1.0 |
| Linux support | v2.0 | Limited testing resources; macOS + Windows covers primary user base |
| Plugin architecture | v2.0 | Requires stable internal APIs and comprehensive testing; v1.0 establishes core foundations |
| Full WCAG 2.1 AA compliance | v2.0 | Complex for interactive Leaflet maps; essential shortcuts + high-contrast mode in v1.0 |
| Auto-update mechanism | v2.0 | Requires code signing certificates (~$300/year); GitHub notifications sufficient for v1.0 |
| Collaborative cloud features | v2.0 | Out of scope for single-user desktop app; server infrastructure needed |
| Custom user-defined WMS/WMTS layers | v2.0 | Must use land profiles in v1.0; custom layers add UI complexity |
| CRLF normalization tool | Never | Python handles line endings natively; not needed |
