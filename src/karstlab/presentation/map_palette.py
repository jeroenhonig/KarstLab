"""Central colour palette for interactive-map layers (single source of truth).

Hues are assigned by semantic role so stacked layers stay distinguishable:

- **Elevation** (contours) → topographic brown.
- **Hydrology** (streams) → cyan.
- **Structure** (faults) → purple.
- **Doline → nearest-fault distance** → a sequential red → blue ramp (the primary
  analytic legend; deliberately spans warm-to-cool and owns yellow + the muted
  blue, so other layers must avoid those hues).
- **Survey / imported markers** → magenta family (see
  ``business.marker_manager._MARKER_PALETTE``; that lives in the business layer,
  which cannot import this presentation module).
- **Interactive tools** (measure / profile) → amber.

Collision rule: contours and streams must not reuse the doline-ramp yellow
(``#ffd400``) or muted blue (``#2b6fb3``) — that ambiguity is exactly what this
module exists to prevent. ``tests/test_map_palette.py`` enforces it.
"""

from __future__ import annotations

# ─── Elevation ───────────────────────────────────────────────────────────────
# Topographic brown for contour lines — the cartographic convention for relief
# and collision-free against the doline ramp (previously a yellow that clashed
# with the ≤250 m doline class).
CONTOURS = "#8c510a"

# ─── Hydrology ───────────────────────────────────────────────────────────────
# Cyan for streams: stays in the intuitive "water = blue" family while reading
# clearly apart from the muted ``>250m`` doline blue. The RGBA form (~0.78 alpha)
# is used because streams render as a raster overlay, not a vector line; the hex
# form drives the legend swatch so the two cannot drift apart.
STREAMS = "#17a2e0"
STREAMS_RGBA: tuple[int, int, int, int] = (0x17, 0xA2, 0xE0, 200)

# ─── Structure ───────────────────────────────────────────────────────────────
FAULTS = "#6a1b9a"  # purple; observed solid, supposed dashed (dash set by caller)

# ─── Predicted conduit (Plan F corridor) ───────────────────────────────────────
# Vivid magenta-pink for the predicted-continuation corridor: high contrast on
# both the green basemap and the grey hillshade, and not part of the doline ramp.
# Isolines render thicker for higher relative-likelihood; candidate dolines use
# the same hue so the "predicted conduit" story reads as one colour family.
CONDUIT_CORRIDOR = "#e6007e"

# ─── Doline → nearest-fault distance ramp (sequential, primary legend) ─────────
# Matches faults.FAULT_DISTANCE_CLASSES thresholds. High-saturation, well-spaced
# hues so the classes read clearly over hillshade/basemap.
FAULT_DISTANCE_COLORS: dict[str, str] = {
    "<=50m": "#e60000",   # bright red — on/at a structure
    "<=100m": "#ff8c00",  # dark orange
    "<=250m": "#ffd400",  # vivid yellow
    ">250m": "#2b6fb3",   # blue — far from any mapped fault
    "none": "#14b8a6",    # teal — no fault dataset
}

# ─── Depression footprints & markers ───────────────────────────────────────────
DEPRESSION_PLAIN_LINE = "#0f766e"   # dark teal outline (no fault data)
DEPRESSION_PLAIN_FILL = "#14b8a6"   # teal fill (no fault data)
TOP25_FOOTPRINT_LINE = "#9a3412"    # dark orange-brown outline
TOP25_FOOTPRINT_FILL = "#ea8a4e"    # orange fill
TOP25_MARKER_BG = "#0f766e"         # numbered pin background (dark teal)
PARALLEL_OUTLINE = "#000000"        # bold outline: doline on a cave-parallel fault
DEFAULT_OUTLINE = "#ffffff"         # default doline outline for fill contrast

# ─── Survey / imported markers ─────────────────────────────────────────────────
# Imported files get a per-file colour from business.marker_manager._MARKER_PALETTE
# (a hash of the file name), so there is no single true colour. This magenta is a
# representative swatch for the legend only — a member of that palette and clear
# of every analysis-layer hue above.
SURVEY_REPRESENTATIVE = "#db2777"

# ─── Optional external overlays & tools ────────────────────────────────────────
VECTOR_OVERLAY_DEFAULT = "#16a34a"  # green — WFS/profile vector overlay fallback
POI_DEFAULT = "#dc2626"             # red — POI / BRGM cavités points
GEOJSON_DEFAULT = "#2563eb"         # blue — injected GeoJSON fallback
TOOL_HIGHLIGHT = "#f59e0b"          # amber — measure-distance / elevation-profile tools
