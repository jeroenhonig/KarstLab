# KarstLab Land Profiles Specification

## 1. Overview

Land profiles are JSON configuration files that adapt KarstLab to different geographic regions. Each profile provides region-specific settings for coordinate systems, map layers, points of interest, and analysis parameters.

Profiles are stored in `resources/regions/` and shipped with the application. New profiles can be contributed via GitHub Pull Requests.

All profiles are validated at load time against both a Pydantic model (`schemas/land_profile_schema.py`) and a JSON Schema file (`resources/schemas/land_profile.schema.json`). Invalid profiles produce a clear error message and fall back to the generic profile.

## 2. Schema

### 2.1 Complete Schema

```json
{
  "id": "string (required) — unique identifier, typically ISO 3166-1 alpha-2 country code",
  "version": "string (required) — semantic version for cache invalidation, e.g. '1.0.0'",
  "name": {
    "en": "string (required) — English name",
    "nl": "string (optional) — Dutch name",
    "fr": "string (optional) — French name"
  },
  "default_crs": "string (required) — EPSG code, e.g. 'EPSG:2154'",
  "common_crs": ["array of EPSG codes — shown in CRS dropdown for this region"],
  "dem_sources": [
    {
      "name": "string — name of the DEM dataset",
      "url": "string — URL where users can download DEM data",
      "description": {
        "en": "string — English description",
        "nl": "string (optional)",
        "fr": "string (optional)"
      },
      "resolution_m": "number — typical resolution in meters"
    }
  ],
  "map_layers": {
    "base": [
      {
        "name": "string — display name",
        "type": "tile | wmts | wms",
        "url": "string — tile URL template or service URL",
        "layer": "string (optional) — layer name for WMS/WMTS",
        "attribution": "string (optional) — attribution text"
      }
    ],
    "overlays": [
      {
        "name": "string — display name",
        "type": "wms | wmts | tile",
        "url": "string — service URL",
        "layer": "string — layer name",
        "opacity": "number (0-1) — default opacity",
        "attribution": "string (optional)"
      }
    ]
  },
  "poi_sources": [
    {
      "name": "string — display name",
      "type": "geojson | csv | wfs | brgm_cavites | spelebase",
      "path": "string (for geojson/csv) — relative path from resources/data/",
      "url": "string (for wfs) — WFS service URL",
      "layer": "string (for wfs, optional) — WFS layer name",
      "departmental": "boolean (optional) — whether source supports departmental filtering"
    }
  ],
  "analysis_defaults": {
    "contour_interval_m": "number — default contour interval in meters",
    "stream_threshold_cells": "number — flow accumulation threshold for stream extraction",
    "doline_min_depth_m": "number — minimum depression depth to detect",
    "doline_max_depth_m": "number — maximum depression depth",
    "doline_min_area_m2": "number — minimum depression area in square meters",
    "doline_max_area_m2": "number — maximum depression area in square meters"
  }
}
```

### 2.2 Required vs Optional Fields

| Field | Required | Notes |
|-------|----------|-------|
| id | Yes | Unique identifier |
| version | Yes | Semantic version string (e.g., "1.0.0"); used for cache invalidation |
| name.en | Yes | English name always required |
| name.{other} | No | Add translations as available |
| default_crs | Yes | Must be a valid EPSG code |
| common_crs | Yes | At least default_crs must be included |
| dem_sources | No | Informational — helps users find DEM data |
| map_layers.base | Yes | At least one base layer required |
| map_layers.overlays | No | Region-specific overlays |
| poi_sources | No | Points of interest |
| poi_sources[].departmental | No | Defaults to false |
| analysis_defaults | Yes | All 6 sub-fields required |

### 2.3 Canonical Parameter Names

The `analysis_defaults` field uses the same canonical parameter names as `settings.json` and `project.karstlab`:

| Parameter | Type | Description |
|-----------|------|-------------|
| `contour_interval_m` | number | Contour line interval in meters |
| `stream_threshold_cells` | number | Flow accumulation threshold (cell count) |
| `doline_min_depth_m` | number | Minimum depression depth to detect (meters) |
| `doline_max_depth_m` | number | Maximum depression depth (meters) |
| `doline_min_area_m2` | number | Minimum depression area (square meters) |
| `doline_max_area_m2` | number | Maximum depression area (square meters) |

## 3. Example Profiles

### 3.1 France (fr.json)

```json
{
  "id": "fr",
  "version": "1.0.0",
  "name": {
    "en": "France",
    "nl": "Frankrijk",
    "fr": "France"
  },
  "default_crs": "EPSG:2154",
  "common_crs": ["EPSG:2154", "EPSG:32631", "EPSG:32632"],
  "dem_sources": [
    {
      "name": "IGN LiDAR HD MNT",
      "url": "https://geoservices.ign.fr/lidarhd",
      "description": {
        "en": "French national LiDAR HD bare-earth DEM (1m resolution)",
        "fr": "Modèle Numérique de Terrain LiDAR HD (résolution 1m)"
      },
      "resolution_m": 1.0
    },
    {
      "name": "RGE ALTI",
      "url": "https://geoservices.ign.fr/rgealti",
      "description": {
        "en": "French national DEM (1m and 5m resolution)",
        "fr": "Modèle Numérique de Terrain national (résolution 1m et 5m)"
      },
      "resolution_m": 1.0
    }
  ],
  "map_layers": {
    "base": [
      {
        "name": "Plan IGN",
        "type": "wmts",
        "url": "https://wxs.ign.fr/cartes/geoportail/wmts",
        "layer": "GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2",
        "attribution": "© IGN"
      },
      {
        "name": "OpenStreetMap",
        "type": "tile",
        "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "© OpenStreetMap contributors"
      },
      {
        "name": "Esri World Imagery",
        "type": "tile",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attribution": "© Esri"
      }
    ],
    "overlays": [
      {
        "name": "Geological Map (BRGM 1/50k)",
        "type": "wms",
        "url": "https://geoservices.brgm.fr/geologie",
        "layer": "SCAN_H_GEOL50",
        "opacity": 0.5,
        "attribution": "© BRGM"
      },
      {
        "name": "Cadastre (PCI)",
        "type": "wms",
        "url": "https://inspire.cadastre.gouv.fr/scpc/wms",
        "layer": "PARCELLES",
        "opacity": 0.4,
        "attribution": "© DGFiP"
      },
      {
        "name": "Karst Zones (BDLISA)",
        "type": "wms",
        "url": "https://bdlisa.eaufrance.fr/geoserver/wms",
        "layer": "bdlisa:EntiteKarst",
        "opacity": 0.5,
        "attribution": "© BRGM/EauFrance"
      }
    ]
  },
  "poi_sources": [
    {
      "name": "BRGM Cavités Géorisques",
      "type": "brgm_cavites",
      "url": "https://georisques.gouv.fr/api/v1/cavites",
      "departmental": true
    },
    {
      "name": "Spélébase CAVECENTER",
      "type": "spelebase",
      "url": "https://www.spelebase.fr/api/cavites",
      "departmental": true
    },
    {
      "name": "Known Caves (France)",
      "type": "geojson",
      "path": "data/fr_caves.geojson"
    }
  ],
  "analysis_defaults": {
    "contour_interval_m": 5.0,
    "stream_threshold_cells": 1000,
    "doline_min_depth_m": 0.25,
    "doline_max_depth_m": 40.0,
    "doline_min_area_m2": 1.0,
    "doline_max_area_m2": 60000.0
  }
}
```

The French `analysis_defaults` match the ARIS Lidar Prospector V3d defaults for backward compatibility.

### 3.2 Netherlands (nl.json)

```json
{
  "id": "nl",
  "version": "1.0.0",
  "name": {
    "en": "Netherlands",
    "nl": "Nederland",
    "fr": "Pays-Bas"
  },
  "default_crs": "EPSG:28992",
  "common_crs": ["EPSG:28992", "EPSG:32631", "EPSG:32632"],
  "dem_sources": [
    {
      "name": "AHN4",
      "url": "https://www.pdok.nl/introductie/-/categories/applicaties/ahn4-downloads",
      "description": {
        "en": "Dutch national height model (0.5m resolution)",
        "nl": "Actueel Hoogtebestand Nederland (0.5m resolutie)"
      },
      "resolution_m": 0.5
    }
  ],
  "map_layers": {
    "base": [
      {
        "name": "BRT Achtergrondkaart",
        "type": "wmts",
        "url": "https://service.pdok.nl/brt/achtergrondkaart/wmts/v2_0",
        "layer": "standaard",
        "attribution": "© Kadaster"
      },
      {
        "name": "OpenStreetMap",
        "type": "tile",
        "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "© OpenStreetMap contributors"
      },
      {
        "name": "Esri World Imagery",
        "type": "tile",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attribution": "© Esri"
      }
    ],
    "overlays": [
      {
        "name": "Geological Map",
        "type": "wms",
        "url": "https://geodata.nationaalgeoregister.nl/geologie/wms",
        "layer": "lithostratigrafie",
        "opacity": 0.5,
        "attribution": "© TNO-GDN"
      }
    ]
  },
  "poi_sources": [],
  "analysis_defaults": {
    "contour_interval_m": 1.0,
    "stream_threshold_cells": 1000,
    "doline_min_depth_m": 0.5,
    "doline_max_depth_m": 50.0,
    "doline_min_area_m2": 10.0,
    "doline_max_area_m2": 100000.0
  }
}
```

### 3.3 Belgium (be.json)

```json
{
  "id": "be",
  "version": "1.0.0",
  "name": {
    "en": "Belgium",
    "nl": "België",
    "fr": "Belgique"
  },
  "default_crs": "EPSG:31370",
  "common_crs": ["EPSG:31370", "EPSG:32631", "EPSG:32632"],
  "dem_sources": [
    {
      "name": "DTM Vlaanderen",
      "url": "https://overheid.vlaanderen.be/informatie-vlaanderen/producten-diensten/digitaal-hoogtemodel-dhmv",
      "description": {
        "en": "Flemish digital terrain model (1m resolution)",
        "nl": "Digitaal Hoogtemodel Vlaanderen (1m resolutie)"
      },
      "resolution_m": 1.0
    },
    {
      "name": "MNT Wallonie",
      "url": "https://geoportail.wallonie.be/catalogue/b795de68-726c-4bdf-a62a-a42686aa5b6f.html",
      "description": {
        "en": "Walloon digital terrain model (1m resolution)",
        "fr": "Modèle Numérique de Terrain de Wallonie (résolution 1m)"
      },
      "resolution_m": 1.0
    }
  ],
  "map_layers": {
    "base": [
      {
        "name": "OpenStreetMap",
        "type": "tile",
        "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "© OpenStreetMap contributors"
      },
      {
        "name": "Esri World Imagery",
        "type": "tile",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attribution": "© Esri"
      }
    ],
    "overlays": [
      {
        "name": "Geological Map (Wallonie)",
        "type": "wms",
        "url": "https://geoservices.wallonie.be/arcgis/services/SOL_SSOL/CARTE_GEOLOGIQUE_SIMPLE/MapServer/WMSServer",
        "layer": "0",
        "opacity": 0.5,
        "attribution": "© SPW"
      }
    ]
  },
  "poi_sources": [],
  "analysis_defaults": {
    "contour_interval_m": 5.0,
    "stream_threshold_cells": 1000,
    "doline_min_depth_m": 1.0,
    "doline_max_depth_m": 100.0,
    "doline_min_area_m2": 10.0,
    "doline_max_area_m2": 100000.0
  }
}
```

## 4. Profile Selection

### 4.1 Selection Methods

1. **Manual selection**: User chooses from dropdown in Settings dialog
2. **Remembered**: Last-used profile stored in ~/.karstlab/settings.json

### 4.2 Fallback Behavior

- If no profile selected: use the "generic" profile with OSM base layer, WGS84 CRS, and conservative analysis defaults
- If selected profile file is missing: fall back to generic profile, warn user
- If profile fails Pydantic validation: fall back to generic profile, show validation error

## 5. POI Source Types

### 5.1 Built-in Source Types

| Type | Description | Departmental |
|------|-------------|-------------|
| `geojson` | Static GeoJSON file bundled in `resources/data/` | No |
| `csv` | Static CSV file with lat/lon columns | No |
| `wfs` | OGC WFS service endpoint | Optional |
| `brgm_cavites` | BRGM Cavités Géorisques API (France only) | Yes |
| `spelebase` | Spélébase CAVECENTER API (France only) | Yes |

### 5.2 Departmental Filtering

POI sources with `"departmental": true` support filtering by French department code (e.g., "09" for Ariège, "46" for Lot). The Markers tab shows a department selector dropdown for these sources. Users select one or more departments to load POI data for their area of interest.

### 5.3 Adding Custom POI Sources

New POI source types can be added per land profile without code changes, as long as they use one of the supported types (geojson, csv, wfs). Country-specific types (brgm_cavites, spelebase) require adapter code in `business/poi.py`.

### 5.4 POI Source Availability & Fallback

POI sources configured in land profiles are subject to network availability. The app implements graceful degradation:

| Behavior | Description |
|----------|-------------|
| Timeout | 10-second timeout per API request |
| Cache | Fetched POI data is cached per department in the project directory |
| Cache staleness | Cached data shows fetch date; user can manually refresh |
| API failure | Warning shown in POI panel; cached data used if available |
| Offline mode | "Offline — cached data shown" or "Offline — no cached data available" |
| Non-blocking | POI fetch runs in background; UI remains fully responsive |
| No POI configured | If a land profile has no `poi_sources`, the Markers tab POI section is hidden |

POI source availability is NOT a blocker for analysis — the core terrain pipeline operates entirely offline on local DEM files.

## 6. Contributing New Profiles

### 6.1 Process

1. Fork the KarstLab repository on GitHub
2. Create a new JSON file in `resources/regions/` (e.g., `si.json` for Slovenia)
3. Fill in all required fields following the schema
4. Validate against JSON Schema: `resources/schemas/land_profile.schema.json`
5. Optionally add POI data as GeoJSON in `resources/data/`
6. Submit a Pull Request with a description of the region and its data sources

### 6.2 Requirements for Submission

- Valid JSON matching the schema (passes Pydantic validation)
- `version` field set to "1.0.0" for new profiles
- All 6 `analysis_defaults` fields present with canonical names
- At least one base map layer that works
- WMS/WMTS URLs must be publicly accessible (no authentication required)
- DEM source URLs must point to official/authoritative data providers
- Analysis defaults should be reasonable for the region's geology
- Attribution fields must be filled for all map layers

### 6.3 Review Criteria

- Pydantic schema validation passes
- Map layers load correctly
- CRS codes are valid
- DEM source URLs are reachable
- Analysis defaults are geologically reasonable
- Profile version set correctly

## 7. Generic Profile

The generic profile serves as fallback and for regions without a dedicated profile:

```json
{
  "id": "generic",
  "version": "1.0.0",
  "name": {
    "en": "Generic / Worldwide",
    "nl": "Generiek / Wereldwijd",
    "fr": "Générique / Mondial"
  },
  "default_crs": "EPSG:4326",
  "common_crs": ["EPSG:4326", "EPSG:3857"],
  "dem_sources": [],
  "map_layers": {
    "base": [
      {
        "name": "OpenStreetMap",
        "type": "tile",
        "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "© OpenStreetMap contributors"
      },
      {
        "name": "Esri World Imagery",
        "type": "tile",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attribution": "© Esri"
      }
    ],
    "overlays": []
  },
  "poi_sources": [],
  "analysis_defaults": {
    "contour_interval_m": 10.0,
    "stream_threshold_cells": 1000,
    "doline_min_depth_m": 1.0,
    "doline_max_depth_m": 200.0,
    "doline_min_area_m2": 25.0,
    "doline_max_area_m2": 100000.0
  }
}
```

## 8. Validation

### 8.1 Pydantic Model

Land profiles are validated by the `LandProfile` Pydantic model in `schemas/land_profile_schema.py`. The model enforces:
- All required fields present with correct types
- `version` is a valid semantic version string
- `default_crs` is included in `common_crs`
- All 6 `analysis_defaults` fields present with canonical names
- At least one base map layer exists
- `doline_min_depth_m` < `doline_max_depth_m`
- `doline_min_area_m2` < `doline_max_area_m2`

### 8.2 JSON Schema

A JSON Schema file (`resources/schemas/land_profile.schema.json`) is generated from the Pydantic model and shipped with the application. This enables:
- Validation in external tools and editors (VS Code, IntelliJ)
- CI validation of contributed profiles
- Documentation generation

### 8.3 Cache Invalidation

The `version` field is tracked in the project's provenance metadata. When a profile version changes (e.g., updated CRS or defaults), the pipeline knows to invalidate steps that depend on profile settings.

> The `pipeline_version` field in the project file (project.karstlab) tracks the analysis pipeline schema version. If a project is opened with a newer pipeline version than when it was last analyzed, all cached results are invalidated and re-analysis is required. Land profile `version` and `pipeline_version` are independent: profile version tracks the profile schema, pipeline version tracks the analysis engine.
