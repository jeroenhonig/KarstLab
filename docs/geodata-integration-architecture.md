# KarstLab — French Geodata Integration Architecture

**Status:** Design / research. No code is to be built from this document until each phase is picked up explicitly.
**Audience:** maintainers and Codex, to implement the features while staying faithful to the existing structure.
**Version target:** KarstLab 1.1.x → 1.2.0

---

## 0. Important correction about the stack

The request framed KarstLab as an *Electron/Leaflet* desktop app. **It is not.** KarstLab is a:

- **Python / PySide6 (Qt)** desktop application,
- whose map is **Leaflet rendered through `folium`** (Python generates a static HTML document),
- displayed inside a **`QWebEngineView`** (`src/karstlab/presentation/map_view.py`),
- with live updates injected through `page().runJavaScript(...)`.

This materially changes the integration advice versus an Electron app:

| Electron assumption | KarstLab reality |
|---|---|
| Renderer `fetch()` hits CORS; needs a *main-process proxy* | A **Python backend** already fetches remote data server-side (`src/karstlab/data/poi.py`); **no CORS, no proxy server needed** |
| Reprojection in JS (proj4js) | Reprojection in **Python** with `pyproj` + `geopandas` (already dependencies, see `src/karstlab/data/crs.py`) |
| Layers configured in JS | Layers configured in **JSON land profiles** (`src/karstlab/resources/regions/*.json`) consumed by Python |

The good news: most of the requested capability is *extending patterns that already exist*, not new infrastructure.

---

## 0b. Fit with the current flow and the analysis (read this first)

This integration must stay subordinate to KarstLab's actual job: **doline/depression detection on LiDAR DTMs**. The external French sources are **interpretive context overlays, never inputs to the detection pipeline.** That separation is a hard design rule — it keeps the analysis flow (DEM → terrain/hydrology/doline detection → result map → explore/export) unchanged and reproducible.

What this means concretely:

1. **WMS context layers fit perfectly — register and (optionally) bake.** They are tile URLs toggled client-side by the in-map `LayerControl`; they add no inline weight and need no re-analysis. This is the already-proven path (BRGM/Cadastre/BDLISA today). Adding more = JSON.

2. **WFS / queryable vector → on-demand injection is the DEFAULT; baking is the exception.** Two reasons grounded in the current flow:
   - The analysis map is **baked once at the end of the pipeline** (`render_top_depressions_map_html`). Vectors baked inline only refresh on re-analysis and re-grow the HTML we just shrank (562 MB → 0.5 MB). The new DEM-stage cache makes re-baking cheap, but it still does not match *exploration*.
   - Faults, boreholes, springs are things the user wants to **pull in and toggle while looking at an existing result**, not regenerate. So fetch on a worker thread and inject into the live map (`MapView.inject_geojson_layer`), bbox-limited to the DEM extent, cached to disk.
   - **Bake a WFS layer only** when it is a small, fixed analysis-context set the user always wants present (e.g. faults within the DEM bbox), and always behind the `_MAX_OVERLAY_FEATURES` cap + `.simplify(...)`.

3. **Relevance ranking for karst analysis (build in this order of value):**
   - **High:** BRGM faults/fractures (cave conduits follow them — overlaying on dolines is genuinely analytic); BDLISA karst/aquifer entities; BSS Eau springs / pertes / dye tracings (cave hydrology in/out points).
   - **Medium:** BRGM lithological formations; BSS boreholes (+ log link-out).
   - **Low / optional:** IGN MNT 50 cm display layer — KarstLab already computes hillshade from the *actual* analysis DEM, so an external relief layer is mostly redundant. Treat as nice-to-have, not a milestone.

4. **Known flow gap (out of scope for v1):** the map only exists *after* an analysis (before it, the empty-state). Exploring geology with **no analysis run** would need an always-on exploration base map — a larger flow change. Not now; note as future work.

---

## 1. Current codebase inventory

### 1.1 How layers are loaded and shown

The analysis map is assembled in **`src/karstlab/presentation/map_builder.py`** with `folium`, then rendered to a standalone HTML string by `render_top_depressions_map_html(...)` and written to disk; `MapView.load_file(...)` loads it into `QWebEngineView`.

Layer primitives in use (all `folium`):

| Layer kind | folium primitive | Builder helper | Spec dataclass |
|---|---|---|---|
| Base raster (OSM/Esri/IGN) | `folium.TileLayer` | `_add_basemaps`, http branch in `build_top_depressions_map` | `TileLayerSpec` |
| WMS overlay | `folium.raster_layers.WmsTileLayer` | `_add_wms_overlays` | `WmsLayerSpec` |
| Vector overlay (GeoJSON) | `folium.GeoJson` | `_add_overlay_layers` | `MapLayerSpec` |
| Raster image overlay (hillshade, streams) | `folium.raster_layers.ImageOverlay` | `_add_image_layers` | `ImageLayerSpec` |
| Layer toggle UI (in map) | `folium.LayerControl(collapsed=False)` | end of `build_top_depressions_map` | — |

Defence-in-depth already present in `map_builder.py`:
- `_MAX_OVERLAY_FEATURES = 50_000` — oversized vector layers are **dropped** (`_add_overlay_layers` / `_feature_count`) so the inline GeoJSON cannot blank the map.
- `_MAP_MIN_ZOOM = 5` — prevents the whole-world fallback view.
- Image overlays are stride-decimated to `≤ 2048 px`; streams are rasterised, not vectorised, to bound size.

### 1.2 The layer registry (this is the key existing extension point)

Layers are **data, not code**. Each region is a JSON land profile in `src/karstlab/resources/regions/*.json`, validated by `LandProfile` in `src/karstlab/data/schemas.py` and loaded by `src/karstlab/data/land_profiles.py`.

Relevant schema (already present):

```
LayerType        = tile | wmts | wms                         # schemas.py
LayerConfig      = {name, type, url, layer?, opacity?, attribution?}
MapLayers        = {base: [LayerConfig], overlays: [LayerConfig]}
PoiSourceType    = geojson | csv | wfs | brgm_cavites | spelebase   # NOTE: wfs already declared
PoiSource        = {name, type, path?, url?, layer?, departmental}
```

`fr.json` already registers BRGM geology (WMS `SCAN_H_GEOL50`), Cadastre PCI (WMS), and BDLISA `EntiteKarst` (WMS) under `map_layers.overlays`. The mapping profile → folium happens in `pipeline.py`:
- `_profile_wms_layers()` → `WmsLayerSpec[]` (filters `overlays` where `type == wms`),
- `_profile_extra_tile_layers()` → `TileLayerSpec[]`,
- `_profile_tile_url()` / `_profile_tile_attribution()` → base map.

**Consequence: adding a new WMS overlay today is a one-line JSON edit — no Python.** This is the spine of the extensible design below.

### 1.3 Server-side fetch + cache pattern (the "proxy")

`src/karstlab/data/poi.py` `fetch_brgm_cavites(department, cache_dir=...)`:
- fetches over `urllib.request` on the Python side (no CORS),
- **never raises** (returns `[]` on failure, falls back to disk cache),
- caches JSON to `cache_dir`.

POI results reach the live map via `MapView.inject_poi_layer(geojson_str, ...)` (`_INJECT_POI_JS`), and the baked map via `_imported_marker_layers` / overlay layers. This is exactly the model for queryable WFS data — generalise it.

### 1.4 KML / GPX import

- Parsers: `src/karstlab/data/vector_io.py` → `read_kml_geometries`, `read_kml_points`, `read_gpx_waypoints` → return `geopandas.GeoDataFrame` (WGS84).
- UI: `presentation/markers_tab.py` import buttons → paths stored on the tab → `markers_changed` signal.
- Baked map: `pipeline._imported_marker_layers(project, marker_colors=...)` → one `MapLayerSpec` per file, deterministic/overridable colour (`marker_manager.imported_marker_color`).
- Live map: `main_window._imported_markers_geojson()` tags each feature with `_kl_color` → `MapView.set_imported_markers()` (`_IMPORTED_MARKERS_JS`).

### 1.5 Layer-selection UI (the top-right checkbox list)

Two distinct controls — do not confuse them:

1. **In-map `folium.LayerControl`** — the checkbox list in the screenshot (Base map / Esri / Geological Map / Cadastre / Karst Zones / Hillshade / Streams / Contours). Generated inside the HTML from whatever layers were added at build time. New profile overlays appear here **automatically**.
2. **Qt `presentation/layers_tab.py` (`LayersTab`)** — controls opacity/visibility of the *analysis* layers via `MapView.set_layer_visible/set_layer_opacity` (JS that walks the Leaflet layer tree by name substring). Opacity changes are debounced (120 ms).

### 1.6 Reprojection helpers

`src/karstlab/data/crs.py`: `project_geometry`, `unproject_geometry` (4326↔CRS via `pyproj.Transformer`), `reproject_raster`, `to_wgs84`. `geopandas` `.to_crs("EPSG:4326")` is available for vector frames. Lambert-93 is `EPSG:2154`; Leaflet consumes WGS84 (`EPSG:4326`) GeoJSON and Web-Mercator (`EPSG:3857`) tiles.

---

## 2. Data source research

> Endpoints below reflect current public knowledge. **Every WFS `typename` and WMS `layer` MUST be confirmed against the live `GetCapabilities`** before wiring (capabilities drift). Where unsure it is marked *(verify)*. CRS column = native service CRS; "WMS reprojects" means the OGC WMS can serve `EPSG:3857`/`4326` directly so no client reprojection is needed for display.

### 2.1 BRGM Géologie 1:50 000 (faults + lithological formations)

- **Display (WMS):** `https://geoservices.brgm.fr/geologie`
  - `SCAN_H_GEOL50` — scanned harmonised 1/50k (already in `fr.json`).
  - Vector themes from **BDCharm50** (harmonised geology): faults and formation polygons exposed as WMS layers, e.g. `GEOLOGIE:FAILLE` / `GEOLOGIE:FORMATION_GEOLOGIQUE` *(verify exact names via GetCapabilities)*.
  - WMS 1.3.0 → request `CRS=EPSG:3857`; **server reprojects**, no client work.
- **Queryable (WFS):** `https://geoservices.brgm.fr/geologie` `SERVICE=WFS` (2.0.0)
  - faults / formations typenames from BDCharm50 *(verify)*. Native `EPSG:2154`; request `srsName=EPSG:4326` if advertised, else reproject in Python.
- **Recommended path:** WMS for the visual layer (Phase 1 PoC). WFS bbox-filtered for queryable faults near the DEM (Phase 2–3).
- **License:** Licence Ouverte / Etalab 2.0 (attribution "© BRGM").

### 2.2 BRGM BSS — boreholes / sub-surface logs (Banque du Sous-Sol)

- **Display/query:** BSS points via BRGM Géoservices / InfoTerre WMS+WFS, and the modern **BSS API** (`https://api.bss.brgm.fr` / data.geoscience.fr) *(verify base + path)*.
- The **logs** themselves are per-borehole documents → not a layer; surface them as a **link-out** in the feature popup (borehole id → BSS web page).
- **Recommended path:** WFS (or BSS REST) **bbox query → points**, server-side fetch + cache (POI pattern), reproject to 4326, inject as a clickable point layer.
- **CRS:** `EPSG:2154`. **License:** Etalab 2.0.

### 2.3 BDLISA — hydrogeological aquifer delineation

- **Service:** GeoServer at `https://bdlisa.eaufrance.fr/geoserver/` → `/wms` and `/wfs`.
  - WMS already used: `bdlisa:EntiteKarst` (karst zones).
  - Other useful typenames: aquifer entities / hydrogeological layers under the `bdlisa:` workspace *(enumerate via GetCapabilities)*.
- **Recommended path:** WMS for area display (done); WFS for queryable aquifer polygons (attributes: entity code, lithology, type).
- **CRS:** `EPSG:2154` (GeoServer can reproject on request). **License:** Licence Ouverte (BRGM / Eaufrance).

### 2.4 BSS Eau — springs, swallow-holes (pertes), dye tracings

- **Springs / swallow-holes:** available through Eaufrance / **Sandre** geo services (`https://services.sandre.eaufrance.fr/geo/...` WFS) and **Hub'Eau** REST APIs (`https://hubeau.eaufrance.fr/api/...`). Map `perte` / `resurgence` to the existing `PoiType` enum.
- **Dye tracings (traçages):** there is **no single clean national public layer**; tracing campaigns live in specialised/partly-restricted datasets. Treat as *best-effort / future* — likely a curated local GeoJSON (`poi_sources` `geojson` type already supports this) rather than a live service.
- **Recommended path:** Hub'Eau/Sandre REST or WFS, server-side fetch + cache (POI pattern); tracings as bundled GeoJSON until a public service is confirmed.
- **CRS:** `EPSG:2154` / WGS84 depending on API. **License:** Etalab 2.0.

### 2.5 IGN LiDAR HD / RGE ALTI derived products (MNT 50 cm)

- **Source DEM (analysis input):** already handled — `dem_sources` in the profile point to IGN LiDAR HD / RGE ALTI; tiles are downloaded and fed to the pipeline. **No change needed** for analysis.
- **Display overlay (Géoplateforme):** `https://data.geopf.fr/wms-r/wms` (WMS-raster) and `https://data.geopf.fr/wmts` (WMTS). Useful layers: elevation / shaded-relief (`ELEVATION.*`) and orthophoto. *(verify layer identifiers via Capabilities.)*
- **Recommended path:** add as a **WMS/WMTS base or overlay** in the profile (display only); the analysis hillshade we already compute locally stays the primary relief.
- **CRS:** Web-Mercator tiles served directly. **License:** Etalab / open (IGN Géoplateforme).

### Summary table

| Source | Best path | Service URL (verify) | Layer / typename (verify) | Native CRS | License |
|---|---|---|---|---|---|
| BRGM geology 1/50k raster | WMS | `geoservices.brgm.fr/geologie` | `SCAN_H_GEOL50` | reprojects | Etalab 2.0 |
| BRGM faults / formations | WMS + WFS | `geoservices.brgm.fr/geologie` | `GEOLOGIE:FAILLE`, `…:FORMATION_GEOLOGIQUE` | 2154 | Etalab 2.0 |
| BRGM BSS boreholes | WFS / BSS REST | `api.bss.brgm.fr` / geoservices | BSS points | 2154 | Etalab 2.0 |
| BDLISA aquifers/karst | WMS + WFS | `bdlisa.eaufrance.fr/geoserver` | `bdlisa:EntiteKarst`, … | 2154 | Licence Ouverte |
| BSS Eau springs/pertes | WFS / Hub'Eau REST | `services.sandre.eaufrance.fr/geo`, `hubeau.eaufrance.fr` | per dataset | 2154/4326 | Etalab 2.0 |
| Dye tracings | bundled GeoJSON (future) | — | — | — | dataset-specific |
| IGN MNT 50 cm display | WMS / WMTS | `data.geopf.fr/wms-r/wms`, `/wmts` | `ELEVATION.*` | reprojects | Etalab / open |

---

## 3. Technical challenges and decisions

### 3.1 CORS
- **WMS/WMTS tiles:** loaded as image requests by Leaflet inside `QWebEngineView`; **not subject to CORS**. Already proven (BRGM/Cadastre/BDLISA WMS render today). No action.
- **WFS / REST JSON:** if fetched from page JS it *would* hit CORS. **Decision: never fetch vector data from the renderer.** Fetch in Python (the `poi.py` model), reproject, and inject as ready GeoJSON / bake into the map. No proxy server, no CORS.

### 3.2 Reprojection (EPSG:2154 → Leaflet)
- **WMS:** request `EPSG:3857` (or `4326`); the server reprojects. No client work.
- **WFS:** request `srsName=EPSG:4326` when advertised; otherwise fetch native `2154` and reproject with `geopandas` `.to_crs("EPSG:4326")` (consistent with `crs.py`). Always hand Leaflet WGS84 GeoJSON.
- Validate axis order (WFS 2.0 + EPSG:4326 can return lat/lon); normalise to lon/lat for GeoJSON.

### 3.3 Performance of large WFS layers
- **BBOX filter** to the analysis DEM extent (reproject DEM bounds → service CRS, pass `BBOX=`). This is the single biggest lever.
- **`count` / `maxFeatures` pagination** with a sane cap; `log()` when truncated (never silently drop — mirror the codebase convention).
- Reuse the existing guards in `map_builder`: `_MAX_OVERLAY_FEATURES` (drop), geometry `.simplify(...)` for display, feature cap.
- **Disk cache** per (typename, bbox) like `poi.py`; never raise on network failure.

---

## 4. Architecture design

### 4.1 Generic, extensible layer registration

Keep "layers are JSON data". Extend the existing schema minimally — **additive, backward-compatible**.

**4.1.1 Display overlays (WMS/WMTS) — already supported.** Adding a source = add a `LayerConfig` to `map_layers.overlays`. To make WMS first-class for new sources, optionally extend `LayerConfig` with:
- `crs` (default `EPSG:3857`), `format` (default `image/png`), `version` (default `1.3.0`), `transparent` (default `true`), `queryable` (bool, enables GetFeatureInfo later).

These map straight onto the existing `WmsLayerSpec` (which already has `fmt`, `transparent`, `version`, `opacity`).

**4.1.2 Queryable vector overlays (WFS) — new, but scaffolded.** `PoiSourceType.WFS` already exists. Introduce a **generic vector-overlay concept** rather than overloading POI. Recommended: add `vector_overlays: list[VectorLayerConfig]` to `MapLayers` (additive; default empty):

```
VectorLayerConfig = {
  name, url, typename,
  service: "wfs" (default),
  srs: "EPSG:2154" (native; request reprojection where possible),
  bbox_filter: true,         # restrict to DEM extent
  max_features: 5000,
  style?: {color, weight, fillOpacity},
  queryable: true,           # expose attributes in popup
  bake: false,               # DEFAULT on-demand; true = bake into analysis map (small fixed sets only)
  attribution
}
```

**4.1.3 New Python service module** `src/karstlab/data/geodata_service.py` — generalises `poi.py`:

```
def fetch_wfs_geojson(
    *, url, typename, bbox_2154=None, srs="EPSG:2154",
    max_features=5000, cache_dir=None, timeout=15.0
) -> dict | None        # GeoJSON FeatureCollection in EPSG:4326, or None
```
- builds the WFS 2.0 GetFeature request (`outputFormat=application/json` where supported, else GML→parse),
- applies `BBOX` (in service CRS),
- reprojects to 4326 (`geopandas`),
- caches to disk; **never raises**.

A thin `WmsFeatureInfo` helper (later) issues `GetFeatureInfo` for queryable WMS layers via the same server-side fetch.

**4.1.4 Wiring into the map** (faithful to current flow).

**Primary path — on-demand injection (default for WFS / queryable):**
- Add a Qt "Data layers" control (a new small section, or extend `markers_tab`) listing the profile's vector overlays with a fetch toggle, analogous to the existing BRGM "Fetch" button.
- On toggle: run `geodata_service.fetch_wfs_geojson(...)` on a **worker thread** (reuse the `_BrgmOverlayWorker` pattern in `main_window.py`), bbox = current DEM/result extent, then inject via a generalised `MapView.inject_geojson_layer(name, geojson, style)` (promote today's `inject_poi_layer`).
- Keeps the baked map small, decouples exploration from re-analysis, and lets the user pull layers in/out of an existing result.

**Secondary path — baking (only for a small fixed analysis-context set):**
- `pipeline.py`: `_profile_vector_overlays(profile, dem_bounds, cache_dir)` → fetch the few overlays marked `bake: true` (bbox = DEM extent) → `MapLayerSpec[]` → pass via the existing `vector_layers=` parameter of `render_top_depressions_map_html` (already plumbed through `_add_overlay_layers`, feature cap, simplify). **No new rendering code.** Default `bake: false`.

### 4.2 Layer-selection UI changes
- **In-map `LayerControl`:** new overlays appear automatically — no work.
- **`LayersTab` (Qt):** today it lists a fixed analysis-layer set. Make it **data-driven**: build its rows from the active profile's overlays + the analysis layers, so opacity/visibility toggles cover new sources. Keep the existing debounced opacity + name-substring JS toggling.
- **Queryable layers:** clicking a feature shows a popup of attributes (WFS: from feature properties; WMS: from `GetFeatureInfo`). For boreholes, include a "open BSS record" link-out.

### 4.3 Module boundaries (respect the existing layering)
```
resources/regions/*.json     ← layer registry (data)
data/schemas.py              ← LayerConfig (+ optional fields), VectorLayerConfig (new)
data/geodata_service.py      ← NEW: server-side WFS/GetFeatureInfo fetch + reproject + cache (generalises poi.py)
data/crs.py                  ← reprojection (reuse)
business/pipeline.py         ← _profile_* mappers (extend), bbox plumbing
presentation/map_builder.py  ← UNCHANGED rendering primitives (reuse WmsLayerSpec / MapLayerSpec)
presentation/map_view.py     ← generalise inject_poi_layer → inject_geojson_layer
presentation/layers_tab.py   ← data-driven rows
presentation/main_window.py  ← worker-thread fetch (reuse _BrgmOverlayWorker pattern)
```

---

## 5. Phased implementation plan (small iterations)

Each phase is independently shippable, test-covered, and faithful to the patterns above. **Do not start a phase until asked.**

- **Phase 1 — WMS proof of concept (JSON only).** Add BRGM faults as a WMS overlay entry in `fr.json` `map_layers.overlays` (after confirming the layer name via GetCapabilities). Verify it renders and toggles in the in-map LayerControl. *Risk: trivial. No Python.*

- **Phase 2 — Optional `LayerConfig` fields + data-driven `LayersTab`.** Add `crs/format/version/transparent/queryable` to `LayerConfig` (defaults preserve current behaviour). Make `LayersTab` build rows from the profile. Tests for schema defaults + UI list.

- **Phase 3 — Generic WFS fetch service + first layer.** *(engine + baked first layer shipped; on-demand GUI injection still pending.)* Implemented: `data/geodata_service.py` (`fetch_wfs_geojson`: WFS 2.0/1.x, GeoJSON+GML via geopandas/pyogrio, reproject→4326, bbox folded into CQL when both present, disk cache, never-raise); `VectorLayerConfig` + `MapLayers.vector_overlays`; `fr.json` "BRGM Dolines (BDCharm50)" (`BRGM:c50_l_divers` `code=8`, infoterre, GeoJSON); `pipeline._profile_vector_overlays` bakes bakeable overlays into the analysis map (best-effort, never blocks). Verified live against infoterre (Doubs bbox → 50 LineStrings reprojected to WGS84). Faults confirmed *not* available as WFS (see `docs/research/brgm/brgm_wfs_findings.md`). **Still TODO:** on-demand worker-thread injection + `MapView.inject_geojson_layer` (make this the default for non-baked layers). Implement `data/geodata_service.py` (`fetch_wfs_geojson`) with bbox filter, reprojection, disk cache, never-raises. Add `VectorLayerConfig` to schema. Generalise `MapView.inject_poi_layer` → `inject_geojson_layer`. Add the Qt "Data layers" fetch control + `_BrgmOverlayWorker`-style worker. Ship **one** high-value WFS layer (BRGM faults *or* BDLISA aquifers) injected on demand, bbox-limited. Unit tests with a recorded WFS fixture (offline). *Baking (`bake: true`) is deferred — not needed to prove value.*

- **Phase 4 — Queryability.** Feature popups for WFS layers (attributes); `GetFeatureInfo` for queryable WMS layers; BSS borehole link-out. *(On-demand layers already render attribute popups via `inject_geojson_layer`.)*

- **Phase 3b — On-demand injection + BSS Eau (shipped).** `MapView.inject_geojson_layer` (points/lines/polys, attribute popups, named-replace); worker-thread fetch (`_GeodataLayerWorker`) using the union DEM bbox; markers-tab "Geodata layers (on demand)" chooser + `geodata_layer_requested` signal; `fr.json` "BSS Eau (springs/boreholes)" (`BSS_EAU_POINT`, geoservices, **GML2**, `bake:false`). Verified: **24 features in the Fourbanne/Grosbois analysis bbox** incl. "Affleurement d'eau" and "GROTTE DE GROSBOIS", with ADES/BSS link-outs.

- **Phase 5a — BDCharm50 faults + distance-to-fault (SHIPPED — the core analysis goal).** Implemented: `business/faults.py` (`load_fault_lines` for .shp/dir/.zip → `L_STRUCT`; `annotate_fault_distances` vectorised nearest-fault in EPSG:2154; `download_bdcharm_faults` per-dept, cached, never-raise); `DepressionResult.distance_to_fault_m` + `nearest_fault_type`; `ProjectFile.fault_lines_path`; pipeline `_annotate_fault_distances` (best-effort, before ranking); Tools-tab "Faults…" picker; results table sortable **Fault m** column + list/popup/tooltip distance. Verified live on dept-25 (4132 fault lines; Doubs dolines annotated at 117/382/219 m with fault type). Reference (unchanged):
  - **Faults source (verified, has data on site):** no live WFS; download the per-department BDCharm50 package `http://data.cquest.org/brgm/bd_charm_50/2019/GEO050K_HARM_<DDD>.zip` (dept 25 = `GEO050K_HARM_025.zip`, 23 MB, EPSG:2154, Licence Ouverte). Fault lines are the **`*_L_STRUCT_2154.shp`** layer (dept 25: 4132 lines; **48 intersect the analysis bbox**, `DESCR` = "Faille observée…" / "Faille supposée…"). Load with `geopandas` (shapefile driver already available).
  - **Distance-to-fault analysis:** in projected CRS (EPSG:2154), for each detected doline compute the distance from its centroid (and/or footprint) to the nearest fault line (`geopandas.sjoin_nearest` or shapely STRtree). Add `distance_to_fault_m` (+ optional `nearest_fault_type`) to `DepressionResult`.
  - **Expose for analysis:** new sortable/filterable column in the results table + the full list; show in popup/tooltip; allow ranking/filtering dolines by proximity to structure. Optionally weight observed vs supposed faults.
  - **Integration:** the fault dataset is a user-provided/downloaded local file (configured per project), reprojected once; the distance computation runs in the pipeline (vectorised, fast) and is cached with the DEM-stage cache where it depends only on DEM+faults.

- **Phase 5 — More sources (by analysis value).** High first: BRGM faults (if not already in P3), BSS Eau springs/pertes & dye tracings (POI types `perte`/`resurgence`; tracings as bundled GeoJSON until a public service is confirmed). Then medium: BRGM formations, BSS boreholes. **IGN MNT 50 cm display is low priority / optional** — local hillshade already covers relief; do it only if explicitly wanted.

### Cross-cutting rules for every phase
- Server-side fetch only; never raise on network failure; cache to disk.
- Always hand Leaflet WGS84 GeoJSON / Web-Mercator tiles.
- Respect `_MAX_OVERLAY_FEATURES`, geometry simplification, and bbox limiting; `log()` any truncation.
- New behaviour is additive and backward-compatible; existing profiles keep working unchanged.
- Confirm every WMS layer / WFS typename against live `GetCapabilities` before committing it to a profile.

---

## 6. Open questions to confirm before building
1. Exact BRGM BDCharm50 WFS typenames for faults and formations.
2. BSS borehole service of record (geoservices WFS vs `api.bss.brgm.fr`) and its bbox query contract.
3. Whether any public service exposes dye-tracing campaigns, or whether these stay a curated local dataset.
4. **Resolved:** vector overlays are **on-demand by default** (`bake: false`); baking is reserved for a small fixed analysis-context set (e.g. faults in the DEM bbox) and is deferred past the PoC. See §0b.
