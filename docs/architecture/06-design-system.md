# KarstLab Design System

## 1. Brand Identity

### 1.1 Name & Tagline
- **Name:** KarstLab
- **Tagline:** "Terrain analysis for karst exploration"
- **Domain:** Desktop GIS application for speleologists, karst researchers, and cave divers

### 1.2 Logo Concept
- Stylized karst landscape silhouette (sinkhole profile)
- Clean, geometric, works at small sizes (16x16 icon through 512x512)
- Primary color: terracotta accent on dark background
- Formats needed: .icns (macOS), .ico (Windows), .png (source), .svg (vector)

## 2. Color Palette

### 2.1 Dark Mode (Primary)

| Role | Hex | Name | Usage |
|------|-----|------|-------|
| Background | `#1a1f2e` | Deep Navy | Main window, panels |
| Surface | `#242938` | Dark Slate | Cards, sidebar, dialogs |
| Surface Elevated | `#2d3348` | Medium Slate | Hover states, dropdowns |
| Border | `#3a4058` | Muted Border | Panel dividers, input borders |
| Text Primary | `#e8eaf0` | Off White | Headings, labels |
| Text Secondary | `#9ca3b8` | Cool Gray | Descriptions, secondary info |
| Text Disabled | `#5a6178` | Dim Gray | Disabled controls |
| Accent Primary | `#c75d4a` | Terracotta | Primary actions, selected items, active tab |
| Accent Secondary | `#4a90d9` | Water Blue | Links, water features, hydrology |
| Success | `#4a9e6e` | Forest Green | Success states, terrain features |
| Warning | `#d4a843` | Amber | Warnings, caution states |
| Error | `#d44a4a` | Red | Error states, validation failures |

### 2.2 Map-Specific Colors

| Feature | Color | Usage |
|---------|-------|-------|
| Dolines | `#c75d4a` (terracotta) with 50% fill | Doline polygons on map |
| Contours | `#8b6d5c` (brown) | Contour lines |
| Streams | `#4a90d9` (water blue) | Stream network |
| Hillshade | Grayscale | Terrain shading overlay |
| Slope | Yellow→Red gradient | Slope visualization |
| Selected feature | `#f0c040` (gold) | Highlighted/selected item |
| Depression labels | White on `#c75d4a` circle | Numbered markers (Top 25) |
| Tile grid | `#9ca3b8` (cool gray) dashed | Tile boundary overlay |

## 3. Typography

### 3.1 Font Stack
- **Primary:** Geist Sans (bundled with app)
- **Fallback:** -apple-system, "Segoe UI", Roboto, sans-serif
- **Monospace:** Geist Mono, "SF Mono", "Cascadia Code", monospace

### 3.2 Type Scale

| Role | Size | Weight | Usage |
|------|------|--------|-------|
| H1 | 20px | 600 (Semi-bold) | Window title, section headers |
| H2 | 16px | 600 | Panel headers, tab labels |
| H3 | 14px | 500 (Medium) | Group headers, field labels |
| Body | 13px | 400 (Regular) | Primary text, descriptions |
| Small | 11px | 400 | Status bar, metadata, coordinates |
| Mono | 12px | 400 | CRS codes, coordinates, file paths |

## 4. Layout

### 4.1 Main Window Structure

```
┌──────────────────────────────────────────────────────────────┐
│  [Update Banner - dismissible]                          [×]  │
├──────────────────────────────────┬───────────────────────────┤
│                                  │  ◀ Sidebar                │
│                                  │ ┌─────────────────────┐   │
│                                  │ │ Layers │ Results │   │   │
│                                  │ │ Tools  │ Markers │   │   │
│                                  │ │ Export │         │   │   │
│                                  │ └─────────────────────┘   │
│          Interactive Map         │                           │
│          (~70% width)            │  Tab Content              │
│                                  │  (~30% width)             │
│                                  │                           │
│  ┌────────────────────────────┐  │                           │
│  │ [Guided Workflow - optional │  │                           │
│  │  collapsible panel]        │  │                           │
│  └────────────────────────────┘  │                           │
├──────────────────────────────────┴───────────────────────────┤
│  Status: Ready  │  CRS: EPSG:28992  │  Zoom: 14  │  NL     │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Sidebar Tabs (5 tabs)

**Layers Tab (Lagen)**
- Toggle switches for each map layer with opacity sliders for overlays
- Grouped:
  - Base layers (from land profile: Plan IGN, OSM, Esri Imagery, etc.)
  - Analysis layers (hillshade, slope, contours, streams, dolines)
  - Reference layers (geological map, cadastre, karst zones — per land profile)
  - Data layers (tile boundary grid, imported KML/GPX)

**Results Tab (Resultaten)**
- Top 25 deepest depressions panel (ranked table):
  - Each row: rank number, depth (m), area (m²), lat/lon
  - Click row → map zooms to and highlights depression
  - Quality flag indicators per depression (icons: edge, nodata, confidence, shape, nested)
- Full scrollable doline list below Top 25
- Summary statistics at top: total count, avg depth, max depth, total area
- Sort options: by depth, area, or location

**Tools Tab (Analyse)**
- Project management: New, Open, Recent projects
- DEM file selection (file picker or drag-and-drop)
- Analysis parameters (6 canonical params):
  - Contour interval (m) — `contour_interval_m`
  - Doline depth min (m) — `doline_min_depth_m`
  - Doline depth max (m) — `doline_max_depth_m`
  - Doline area min (m²) — `doline_min_area_m2`
  - Doline area max (m²) — `doline_max_area_m2`
  - Stream threshold (cells) — `stream_threshold_cells`
- "Analyze" button (prominent, terracotta accent)
- Land profile selector

**Markers Tab (Markers)**
- Marker list showing all project markers (name, lat, lon)
- Manual marker placement toggle (click on map)
- GPS coordinate entry (lat/lon fields)
- POI panel:
  - BRGM Cavités Géorisques — department selector
  - Spélébase CAVECENTER — department selector
- Import buttons: GPX, KML
- Export markers to GPX button

**Export Tab (Exporteer)**
- Export buttons: KML, GeoJSON, GPX (top depressions)
- Report generation button (HTML with static map)
- Statistics JSON export
- Quick actions with icons

### 4.3 Guided Workflow Panel

Optional collapsible panel overlaying the bottom of the map area (for beginners):

```
┌──────────────────────────────────────────────────────────────┐
│  Guided Workflow                                     [▼ Hide]│
│  ① Download DEM  ② Import tiles  ③ Assemble  ④ Configure    │
│  ⑤ Analyze  ⑥ View results                                  │
│  ───────────                                                 │
│  Current: Step 2 — Import DEM tiles into project directory   │
│  [Select DEM files...]                                       │
└──────────────────────────────────────────────────────────────┘
```

### 4.4 Spacing System
- Base unit: 4px
- XS: 4px
- S: 8px
- M: 12px
- L: 16px
- XL: 24px
- XXL: 32px
- Panel padding: 16px
- Element gap: 8px
- Section gap: 24px

## 5. Components

### 5.1 Buttons

| Type | Style | Usage |
|------|-------|-------|
| Primary | Solid terracotta (#c75d4a), white text | "Analyze", primary actions |
| Secondary | Outlined, border #3a4058, text #e8eaf0 | Export, secondary actions |
| Ghost | No border, text #9ca3b8 | Toolbar items, subtle actions |
| Danger | Solid #d44a4a, white text | Delete, destructive actions |

Border radius: 6px for all buttons.

### 5.2 Input Fields
- Background: #242938
- Border: #3a4058 (1px)
- Focus border: #4a90d9 (2px)
- Text: #e8eaf0
- Placeholder: #5a6178
- Border radius: 6px
- Height: 32px

### 5.3 Toggle Switches (Layer controls)
- Track: #3a4058 (off), #c75d4a (on)
- Thumb: #e8eaf0
- Width: 36px, Height: 20px

### 5.4 Opacity Sliders
- Track: #3a4058
- Fill: gradient from #3a4058 to #c75d4a
- Thumb: #e8eaf0
- Width: 100%, Height: 4px
- Shown next to overlay layer toggles

### 5.5 Progress Bar
- Track: #242938
- Fill: gradient from #c75d4a to #4a90d9
- Height: 4px (inline), 8px (dialog)
- Border radius: 4px
- DAG step indicator: numbered steps with checkmarks (completed), spinner (active), gray (pending)

### 5.6 Cards (Results list items)
- Background: #242938
- Hover: #2d3348
- Selected: border-left 3px #c75d4a
- Border radius: 8px
- Padding: 12px

**Top 25 Depression Card:**
```
┌──────────────────────────────────┐
│ ① ┃ Depth: 12.4 m               │
│   ┃ Area: 850 m²                 │
│   ┃ 44.812° N, 0.987° E         │
│   ┃ ⚑ high_confidence            │
└──────────────────────────────────┘
```

### 5.7 Quality Flag Icons

| Flag | Icon | Color | Tooltip |
|------|------|-------|---------|
| `edge_proximity` | ⚠ | `#d4a843` (amber) | "Near raster edge — may be incomplete" |
| `nodata_adjacent` | ◌ | `#d4a843` (amber) | "Adjacent to NoData area" |
| `depth_confidence` high | ⚑ | `#4a9e6e` (green) | "High confidence" |
| `depth_confidence` medium | ⚑ | `#d4a843` (amber) | "Medium confidence" |
| `depth_confidence` low | ⚑ | `#d44a4a` (red) | "Low confidence" |
| `shape_regularity` low | ◇ | `#d4a843` (amber) | "Irregular shape — possible artifact" |
| `nested` | ⊂ | `#9ca3b8` (gray) | "Nested within larger depression" |

### 5.8 Tabs (Sidebar)
- Inactive: text #9ca3b8, no background
- Active: text #e8eaf0, bottom border 2px #c75d4a
- Hover: text #e8eaf0, background #2d3348
- 5 tabs arranged in a single row (wraps to 2 rows if sidebar narrow)

### 5.9 Update Banner
- Background: #2d3348
- Left accent border: 3px #4a90d9
- Text: "KarstLab X.Y available" + Download link
- Dismiss button: × in top-right

### 5.10 Error Dialog
- Background: #242938
- Header: icon + "Analysis Error" in #d44a4a
- Body: which DAG step failed and why, in #e8eaf0
- Completed steps shown with green checkmarks
- Actions: "Rerun from failed step", "View Log", "Copy Log", "Close"

### 5.11 Numbered Map Markers

Depression markers on the interactive map corresponding to Top 25 ranks:

- Circle: 24px diameter, `#c75d4a` fill, 2px white border
- Number: white text, Geist Sans 11px bold, centered
- Hover: scale 1.2×, show tooltip with depth + area
- Click: opens popup with full depression details + quality flags

## 6. Iconography
- Style: Outlined, 1.5px stroke, rounded caps
- Size: 16px (toolbar), 20px (sidebar), 24px (dialog)
- Color: inherits text color (primary or secondary)
- Source: Lucide Icons (open source, MIT license) or custom SVG

## 7. Animation & Transitions
- Duration: 150ms for hover, 250ms for panel transitions
- Easing: ease-out for most, ease-in-out for sidebar collapse
- Sidebar collapse: 250ms width transition
- Progress bar: smooth fill animation
- Guided workflow step transition: 200ms slide
- No decorative animations — keep it professional

## 8. Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+N | New project |
| Ctrl+O | Open project |
| Ctrl+R | Run analysis |
| Ctrl+E | Export all |
| Ctrl+1 | Switch to Layers tab |
| Ctrl+2 | Switch to Results tab |
| Ctrl+3 | Switch to Tools tab |
| Ctrl+4 | Switch to Markers tab |
| Ctrl+5 | Switch to Export tab |
| Ctrl+\\ | Toggle sidebar |
| Ctrl+G | Toggle guided workflow panel |
| Ctrl+? | Show shortcuts dialog |
| Escape | Cancel current operation / close dialog |

## 9. Responsive Behavior
- Minimum window size: 1024×768
- Sidebar collapses to icon-only at narrow widths (< 1200px)
- Map always fills remaining space
- Dialog windows are centered and sized to content (max 600px wide)
- Guided workflow panel collapses to single-line summary at narrow heights
- Tab bar wraps to 2 rows if sidebar < 300px wide
