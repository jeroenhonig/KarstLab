# CLAUDE.md

> Project conventions for KarstLab, derived from the existing codebase. These are
> the rules to follow. Where the codebase does not yet match a rule, the gap is
> tracked as a follow-up code task (see the project tracker) — the rule is
> authoritative, the current code is not.

KarstLab is a cross-platform desktop GIS application for karst terrain analysis
(PySide6 GUI + CLI), Python 3.12.

---

## 1. Architecture & layering

Four layers under `src/karstlab/`, with a strict one-way dependency direction:

```
presentation/  (PySide6 GUI)  ─┐
cli/           (argparse)      ─┤──> business/ ──> data/ ──> infrastructure/
                                │         └─────────────────────^
                                └──> (GUI/CLI may import business AND data)
```

- **`data/`** — IO, schemas, persistence. Pydantic models, raster/vector IO, CRS,
  project files. Imports nothing from `business`/`presentation`.
- **`business/`** — pure analysis logic (contours, dolines, hydrology, terrain,
  conduit, pipeline). Imports `data/` and `infrastructure/`, never `presentation/`.
- **`infrastructure/`** — external-tool adapters (`whitebox_adapter.py`).
- **`presentation/`** — Qt widgets, the analysis worker thread, map rendering.
- **`cli/`** — `argparse` entrypoint, calls `business.pipeline` directly.

**Rule:** dependencies point downward only. `data/` never imports `business/`.

### Circular-dependency escape hatch
`business/pipeline.py` uses **lazy imports inside functions** (e.g.
`pipeline.py:831` imports `LayerType` locally) to avoid import cycles. Module-level
imports are the default; lazy imports are the documented exception, not a style choice.

---

## 2. Naming

| Thing | Convention | Example |
|-------|-----------|---------|
| Modules | `snake_case.py` | `marker_manager.py`, `raster_io.py` |
| Functions | `snake_case`, verb-first | `extract_contours`, `detect_dolines`, `read_dem` |
| Private helpers | leading `_` | `_validate_2d`, `_effective_interval` |
| Classes | `PascalCase` | `DolineDetector`, `DemData` |
| Constants | `UPPER_CASE` (module-level); `_` prefix if internal | `PROJECT_FILENAME`, `_CONTOUR_MAX_GRID_PX` |
| Qt signals | `snake_case`, verb phrase | `analyze_requested`, `layer_visibility_changed` |
| Qt slots | `_on_<event>` | `_on_progress`, `_on_visibility_changed` |
| Workers | `<Purpose>Worker`; `_` prefix if module-internal | `AnalysisWorker`, `_BrgmOverlayWorker` |

**GUI methods/attributes use `snake_case`, NOT Qt camelCase.** Keep it that way.

**`_`-prefix means "non-public API"** — it marks the symbol as not part of any
module's intended public surface, independent of `__all__`. A symbol with at least
one cross-module caller is public and carries no prefix; a symbol used only within
its defining module is private and carries `_`. `is_metric_crs` (`data/crs.py:24`)
is public (imported by `business/conduit.py:187`, exported in `data/__init__.py`
`__all__`) and correctly unprefixed. Audit any other prefix-less module-level
helper the same way: add `_` if no cross-module caller exists, otherwise confirm
public.

---

## 3. Type hints & signatures

- **Comprehensive type hints are mandatory.** `mypy --strict` is enabled
  (`pyproject.toml`); every signature has param + return types.
- Modern union syntax: `CRS | str | None`, not `Optional[...]`.
- `from __future__ import annotations` is the first line of every real module.
- **Keyword-only public APIs:** non-trivial functions force `*` then keyword args:
  `extract_contours(array, *, transform, interval_m, crs=None)` (`contours.py:33`).
- **Progress callbacks** are consistently typed `Callable[[str], None] | None = None`
  on orchestrator functions (`contours.py:42`, `dolines.py:46`, `pipeline.py:112`).

---

## 4. Data structures

Three tools, chosen by purpose:

- **Pydantic models** — anything persisted / serialized to JSON. All centralized in
  `data/schemas.py`. Base class `StrictModel` sets
  `ConfigDict(extra="forbid", validate_assignment=True)` (`schemas.py:14`).
  Validators via `@field_validator` / `@model_validator`. Enums via `StrEnum`.
  Examples: `ProjectFile`, `UserSettings`, `AnalysisParams`, `DepressionResult`.
- **Frozen dataclasses** — in-memory parameter/result objects in `business/`/`data/`,
  `@dataclass(frozen=True)`. Examples: `DolineDetectionParams`, `DemData`,
  `HydrologyOutputs`. Immutable, matching the global immutability rule.
- **`TypedDict` for GeoJSON geometry** — geometry is a typed dict, not a bare
  `dict[str, Any]` / `dict[str, object]`. A single `GeoJsonGeometry(TypedDict)`
  defines the shape so geometry serializes directly to `json.dumps`/folium/shapely
  at zero runtime cost while staying statically typed. Do not reintroduce
  `GeoJsonGeometry = dict[str, Any]`.

`NamedTuple` is not used.

---

## 5. Error handling

### Exceptions
- **Mostly stdlib exceptions** raised at validation points: `ValueError` for bad
  params (`contours.py:56`), `FileExistsError` for IO conflicts (`project_io.py:146`).
- **Custom exceptions** subclass the closest stdlib base, located beside the code
  that raises them (no central hierarchy required):
  - `WhiteboxRunError(RuntimeError)` — `infrastructure/whitebox_adapter.py:85`
  - `LandProfileError(ValueError)` — `data/land_profiles.py:36`
  - `AnalysisCancelled(BaseException)` — `presentation/analysis_worker.py:19`
    (intentionally `BaseException` so a broad `except Exception` will not swallow a
    user cancel).
- Use exception chaining (`raise ... from e`) whenever re-raising inside an
  `except` block (`marker_manager.py:110`).

### Error policy (fail-loud by default)
- **`business/` never swallows errors.** Validation and computation failures raise;
  they do not return `None`/sentinels and are not caught-and-ignored.
- **`pipeline.py` may degrade only for optional stages.** A degradable stage must
  `logger.warning(...)` with the exception context (`exc_info=True` or the exception
  in the message) — **never a silent `pass`**. Each `except` that continues must
  carry a `# why:` comment explaining why that stage is optional. Non-optional stage
  failures re-raise.

### Logging
- Every module declares `logger = logging.getLogger(__name__)`.
- **INFO** at pipeline stage boundaries; **WARNING** for degraded/skipped optional
  stages (with exception context); **DEBUG** for adapter calls (e.g. Whitebox).
- Logging is the diagnostic channel; exceptions are the control-flow channel. Do not
  conflate them (no logging in place of raising, no raising in place of a warning for
  an optional stage).

### GUI error surfacing
Severity maps to exactly one channel:

| Channel | Use for |
|---------|---------|
| `QMessageBox.critical` | Action-aborting failure (the operation cannot complete). Worker `failed` signals route here. |
| `QMessageBox.warning` | Fixable bad input / precondition (user can correct and retry). |
| `statusBar().showMessage` | Transient info and progress only. |
| `QMessageBox.question` | Destructive-action confirmation only (e.g. close while analysis running). |

Worker errors travel as signal payloads (`failed = Signal(str)`) → handler →
`QMessageBox.critical` (`analysis_worker.py:107` → `main_window.py:640`).

---

## 6. PySide6 patterns

- **Threading: `QThread` + worker `QObject`.** Worker has a no-arg `run()`, emits
  `progress`/`finished`/`failed`/`cancelled` signals, is `moveToThread`'d; thread +
  worker are stored as instance vars and cleaned via `deleteLater` on
  `thread.finished` (`main_window.py:552-602`, `analysis_worker.py`).
- **Cancellation** via `QThread.currentThread().isInterruptionRequested()` checked in
  the progress callback, raising `AnalysisCancelled` (`analysis_worker.py:112`).
- **Composition:** tab widgets each live in their own module (`tools_tab.py`,
  `layers_tab.py`, ...); `MainWindow` composes them and bridges their signals to
  handler slots.
- **WebEngine fallback:** check `QT_QPA_PLATFORM == "offscreen"` and fall back to
  `QTextBrowser` (`map_view.py:320`); custom `karstlab://` URL scheme intercepted via
  a `QWebEnginePage` subclass.

### File-size guideline & the `MainWindow` exception
Files stay under **800 lines** (coding-style rule). `MainWindow` (~1000 lines) is a
**recorded accepted exception**: when you touch it, **extract handler groups** into
separate modules/mixins and **add no new responsibilities**. New GUI features get
their own module rather than growing `MainWindow`.

---

## 7. Styling

- Single source of truth: `presentation/_styles.py` exposes `_stylesheet() -> str`
  (one QSS string), applied once via `self.setStyleSheet(_stylesheet())`
  (`main_window.py:137`).
- Per-widget targeting via `setObjectName("primaryButton")` + QSS selector.
- Dark theme palette (`#1a1f2e` bg, `#e8eaf0` text, `#c75d4a` accent). No scattered
  inline Qt stylesheets. (Inline HTML/CSS exists only inside the Leaflet/JS map
  strings, a different layer.)

---

## 8. Docstrings & comments

- **Module docstrings** on all modules.
- **Google-style** docstrings on public functions/classes; density is higher in
  `business/` (algorithm-heavy) and lighter in `data/` (relies on type hints).
- Inline comments explain *why* / algorithm choices, not *what*.
- Section dividers `# ─── Section ───` in large GUI files (`main_window.py`).
- Document private methods when their behavior is non-obvious; trivial private
  helpers may rely on name + type hints.

---

## 9. Testing

- **pytest**, files `test_*.py`, functions `test_*`. Group with `TestThing` classes
  when a unit has several related cases (`test_marker_manager.py`); flat functions
  are fine for small modules.
- **Assertions:** plain `assert`, `pytest.approx` / `np.testing.assert_allclose` for
  floats/arrays, `pytest.raises(..., match=...)` for errors.
- **Network tests** must carry `@pytest.mark.network` (skipped by default;
  `addopts = "-ra -m 'not network'"`).
- Coverage target: **80%+**.

### Test-double policy
- **Fakes are the default** for heavy/external tool dependencies — hand-rolled fake
  classes (`FakeHydrologyBackend`, `FakeWhiteboxAdapter`), not mocks.
- **`@patch` only for stdlib / IO seams.**
- **Real dependencies for pip-installable libs** (`rasterio`, `geopandas`) — run them
  for real against `tmp_path` files.
- **Fakes for binary/network deps** (`whitebox`, HTTP endpoints).

### Fixtures
- A `conftest.py` hoists the **shared `QApplication`** singleton and the
  **`synthetic_dem`** fixtures so they are discoverable without imports.
- File-specific fixtures stay local to their test module.
- GUI tests run with `QT_QPA_PLATFORM=offscreen` and block the WebEngine import
  (`test_gui_app.py`). No `pytest-qt`/`qtbot`.

---

## 10. Tooling & commands

- `make check` = `lint` + `typecheck` + `test`.
- `make lint` → `ruff check` (rules `E,F,I,B,UP,SIM`, line-length 100).
- `make typecheck` → `mypy --strict`.
- `make test` → `pytest`.
- `make doctor` → environment diagnostic CLI.
- `make schemas` / `check-schemas` → regenerate/verify JSON schemas from Pydantic.
- Build via `hatchling`; package via PyInstaller (`make package-macos` etc.).
- **Python 3.12** for dev/packaging (geospatial C-extension wheels); metadata allows
  3.12–3.14.
