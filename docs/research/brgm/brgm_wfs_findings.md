# BRGM / IGN WFS endpoint verification — findings (study area: Doubs, dept. 25)

**Method:** live `curl` from a local network (the sandbox blocked BRGM hosts; this run did not). All GetCapabilities and GetFeature responses are saved as raw files in this directory (`*.xml`, `*.json`, `*.gml`). Tests used the Doubs/Jura karst area, EPSG:2154 bbox `920000,6650000,1010000,6740000` (and a narrower DEM-scale bbox `948000,6698000,955000,6705000`). Verification date: 2026-06-01.

> Facts only. Where a call failed it is reported as a failure, not guessed.

---

## 1. Endpoint status table

| Endpoint | Works | WFS version | GeoJSON | # layers | Covers Doubs | Note |
|---|---|---|---|---|---|---|
| `infoterre.brgm.fr/geoserver/ows` | ✅ 200 | 1.0.0 / 1.1.0 / **2.0.0** | ✅ `application/json`, `application/geo+json` | 10 (BRGM + RGF workspaces) | ✅ (BRGM:c50_*) | real GeoServer; also GML/KML/CSV |
| `geoservices.brgm.fr/geologie` | ✅ 200 | 2.0.0 (MapServer) | ❌ **GML only** | ~17 (maps, lithology 1/1M, **BSS**, **BSS_EAU**) | ✅ (BSS_EAU) | no faults; coarse geology |
| `mapsref.brgm.fr/wxs/maps/sigeol` | ❌ **broken** | — | — | — | — | MapServer error: `Unable to access /carto/wxs/maps/sigeol.map` |
| `data.geopf.fr/wfs/ows` (Géoplateforme) | ✅ 200 | 2.0.0 | ✅ (1 advertised) | huge (IGN) | n/a | **no** BRGM geology / faille / charm / structural FeatureTypes |

---

## 2. Faults (failles) verdict for Doubs

**There is no live, queryable WFS fault-line layer that covers the Doubs.** Evidence:

- `geoservices.brgm.fr/geologie` (WFS): no `faille`/`structural` FeatureType in capabilities.
- `data.geopf.fr` (WFS): no BRGM structural/`charm`/`faille` FeatureType.
- `infoterre` GeoServer publishes only `BRGM:c50_l_divers`, `c50_l_isoval`, `c50_p_divers`, `c50_p_struct` (+ RGF Pyrenees set). **None are faults:**
  - `c50_l_divers` = miscellaneous lines. Decoded `code` legend from sampled `attr` text: `1`=quarry face, `3`=metamorphic isograde, `7`=biozone limit, `8`=**Dolines**, `10`=alluvial fans, `11`=old channels, `13`=quarry, `55`=slide décollement. No fault code observed.
  - `c50_p_struct` = structural **points** = dip/azimuth measurements (`pendage`/`azimut`), not fault lines.
  - The 591 `attr LIKE '%aille%'` hits were *"front de **taille**"* (quarry faces), false positives — **not failles**.
- `RGF:RGF-CAGEPYR-Strutural` (infoterre): **doubly unusable** — (a) HTTP 400, server-side missing file `…/RGF_CAGEPYR/L_STRUCT_250K.shp`; (b) RGF-CAGEPYR is the **Pyrenees** 1/250k dataset, geographically irrelevant to the Doubs.

**Available paths for faults instead:**
1. **WMS raster (display-only):** `geoservices.brgm.fr/geologie` layer `SCAN_H_GEOL50` (already in `fr.json`) — harmonised 1/50k with faults *drawn in*, not vector/queryable.
2. **BDCharm50 vector download (offline):** dataset **"Cartes géologiques départementales à 1/50 000 (Bd Charm-50)"** — `https://www.data.gouv.fr/datasets/cartes-geologiques-departementales-a-1-50-000-bd-charm-50` (per-department package; contains linear structural elements / failles as shapefile). Coverage is sheet-by-sheet; **verify the Doubs/dept-25 package contents before relying on it.**

→ For faults: **use the existing WMS for display; if vector faults are required, add a downloaded BDCharm50 dept-25 shapefile as a local layer.** No engine WFS path yields Doubs faults.

---

## 3. Springs / water points verdict (BSS Eau)

**Confirmed and rich, covers Doubs.**

- Endpoint: `geoservices.brgm.fr/geologie`, typename **`BSS_EAU_POINT`**, WFS 2.0.0, **GML only** (no GeoJSON).
- Doubs DEM-scale bbox test: **5 features returned** (Point, EPSG:2154). Jura karst → many spring/water points as expected.
- Attributes (high value): `nature_pe` / `nature_pe_code` (point type), `type_point_eau`, `num_departement`, `latitude`/`longitude`, `liste_bdlisa` (aquifer link), and **link-outs** `lien_bsseau`, `lien_ades`, `lien_infoterre`, `liste_producteur`, plus measurement counts (`nb_mesures_piezo`, `nb_mesures_qualito`).
- Related types on the same endpoint: `BSS_TOTAL_AVEC_LABEL` (boreholes), `BSS_EAU_QT_POINT` (points with water-level measurements).

---

## 4. Bonus high-value finding — BRGM-mapped dolines (queryable, GeoJSON, Doubs)

`infoterre` `BRGM:c50_l_divers` filtered `code=8` = **"Dolines"** (confirmed via `attr`). In the wide Doubs bbox this layer matched **396 features** (LineString, EPSG:2154), available as **GeoJSON**. This is a direct **cross-validation layer**: BRGM-mapped dolines vs KarstLab-detected depressions. GeoServer **CQL_FILTER** works (`code=8 AND attr IS NOT NULL`), so the doline subset is a clean server-side query.

---

## 5. Engine requirements (`geodata_service.py`) — evidence-based

The generic WFS service must support, to cover the confirmed layers:

- **Two WFS dialects:** 2.0.0 (`count`, `typeNames`, `startIndex`) **and** 1.0.0/1.1.0 (`maxFeatures`, `typeName`). infoterre advertises all three; geoservices answers 2.0.0.
- **Two output formats:** request `application/json` (infoterre) and **fall back to GML** (geoservices `BSS_EAU_POINT` is GML-only). **Parsing is solved:** `geopandas` + `pyogrio`/GDAL (already installed) read GML, GeoJSON **and** Shapefile (`rw`); the real BSS GML parsed to 5 Points/EPSG:2154 and the GeoJSON to 50 LineStrings.
- **CRS:** request `srsName=EPSG:2154` (native) or `EPSG:4326`; reproject to WGS84 with `geopandas.to_crs` for Leaflet. (axis order: EPSG:2154 is easting/northing — unambiguous; only watch lat/lon flip if ever requesting 4326 from a 2.0.0 server.)
- **BBOX filter:** `bbox=xmin,ymin,xmax,ymax,EPSG:2154` — essential; national layers are huge.
- **CQL_FILTER** (GeoServer/infoterre): to subset attribute classes (e.g. dolines `code=8`). Not available on the MapServer endpoint — keep optional.
- **Pagination:** `count` + `startIndex` (2.0.0). Cap + log truncation.
- **Robustness:** server-side fetch, disk cache, never-raise (mirror `data/poi.py`).
- **Shapefile loader:** needed only if BDCharm50 faults are added as a downloaded local layer — already supported by geopandas, no new dependency.

---

## 6. Recommendation — first concrete layer

**Build the generic WFS engine, ship BRGM-mapped dolines (`infoterre` `BRGM:c50_l_divers`, `code=8`) as the first layer**, then add BSS Eau springs second.

Rationale, grounded in the tests:
- **Simplest engine path first:** dolines come as **GeoJSON** from a real GeoServer → proves the whole chain (capabilities → bbox → CQL → reproject → inject) without needing GML yet.
- **Direct analytic value:** overlaying BRGM-mapped dolines on KarstLab-detected depressions is immediate cross-validation of the core analysis — the highest-leverage first overlay for the Doubs.
- **Sequenced complexity:** add **BSS Eau springs** second — this is where the **GML fallback** earns its place (GML-only endpoint), plus the rich link-outs (ADES/BSS Eau) for hydrology.
- **Faults are not a v1 WFS layer:** keep the WMS raster for display; defer vector faults to an optional BDCharm50 dept-25 shapefile import.

Suggested order: (1) engine + BRGM dolines (GeoJSON) → (2) BSS Eau springs (GML) → (3) optional BDCharm50 fault shapefile → (4) queryability/popups + borehole link-outs.

---

## 7. Raw response files in this directory
- `infoterre_caps.xml`, `geologie_caps.xml`, `sigeol_caps.xml`, `geopf_caps.xml` — GetCapabilities.
- `it_c50_l_divers.json` (narrow bbox, 0), `c50_l_divers_wide.json` (396), `c50_l_divers_doubs50.json`, `c50_sample300.json`, `c50_faille_cql.json`, `c50_code8.json` — c50 line tests.
- `it_c50_p_struct.json` — structural points (dips).
- `bss_eau_point.gml` — BSS Eau springs GML (Doubs).
- `rgf_strutural_doubs.json` — RGF structural error (missing shapefile).
