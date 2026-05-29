# Project: KarstLab v1.0.0 Delivery

## Goal

Deliver KarstLab v1.0.0 as a cross-platform desktop GIS application that reproduces the core ARIS Lidar Prospector V3d workflow with modern architecture, tested analysis output, map visualization, exports, reports, project persistence, land profiles, and macOS/Windows packaging.

## Scope

- In scope:
  - Define Codex + Claude Code orchestration.
  - Build from the existing architecture docs.
  - Use Codex as repository owner and implementation agent.
  - Use Claude Code as planner/reviewer and parallel contributor for isolated files.
  - Deliver phased v1.0.0 gates from setup through release candidate.
- Out of scope:
  - ML doline detection.
  - 3D visualization.
  - Plugin architecture.
  - Linux packaging.
  - Cloud/collaborative features.

## Current Phase

- Phase: Phase 4 - Minimal GUI review gate
- Objective: Verify the first PySide6 workflow that selects a DEM, runs the validated headless pipeline, and displays map/results.
- Exit criteria:
  - User can select DEM, run analysis, see map and Top 25 results.
  - Pipeline failure shows actionable error and log location.
  - GUI remains responsive during analysis.
  - Claude Code review clears Phase 4 before Phase 5 starts.

## Phase Checklist

- [x] Capture agent orchestration workflow.
- [x] Capture v1.0.0 release gates.
- [x] Create Python 3.12+ project skeleton.
- [x] Add shared Pydantic contracts.
- [ ] Add synthetic DEM fixture.
- [ ] Add initial tests.
- [x] Run local smoke validation.
- [x] Install/verify missing development tools (`mypy`, `PyInstaller`).
- [x] Initialize git repository.
- [x] Claude Code contract review.
- [x] Address contract review findings.
- [x] Add project directory creator.
- [x] Address project directory review blockers.
- [x] Add land profile JSON files.
- [x] Add JSON Schema resource files.
- [x] Add synthetic DEM fixture.
- [x] Add first raster I/O tests.
- [x] Add CRS detection/reprojection helpers.
- [x] Add VRT assembly tests and helpers.
- [x] Address VRT assembly review findings.
- [x] Verify WhiteboxTools on the active machine.
- [x] Add vector export/import tests and helpers.
- [x] Claude Code vector I/O review and fixes.
- [x] Add WhiteboxTools adapter.
- [x] Add first hydrology wrapper.
- [x] Run local WhiteboxTools hydrology smoke on synthetic DEM.
- [x] Address Whitebox adapter review findings.
- [x] Add scientific DEM validator.
- [x] Add terrain helpers.
- [x] Address DEM validator and terrain review blocker.
- [x] Add fill-subtract doline detector.
- [x] Add depression ranking helpers.
- [x] Add contour extraction helpers.
- [x] Address Phase 3 review findings.
- [x] Add headless `karstlab analyze` command.
- [x] Add statistics/provenance JSON export.
- [x] Add Top 25 GeoJSON/KML/GPX exports.
- [x] Add contour GeoJSON/KML exports.
- [x] Add Folium Top 25 map rendering.
- [x] Add HTML report generation with embedded Folium map iframe.
- [x] Integrate exports, map, and report into the headless pipeline.
- [x] Run Claude-style review on headless pipeline/export/map/report diff.
- [x] Run real WhiteboxTools CLI smoke on synthetic DEM.
- [x] Add PySide6 `MainWindow` shell.
- [x] Add map-centric splitter layout with sidebar.
- [x] Add Tools, Results, Layers, Markers, and Export tabs.
- [x] Add DEM picker and Analyze button.
- [x] Add `AnalysisWorker` running the headless pipeline on `QThread`.
- [x] Add `MapView` with QWebEngineView and QTextBrowser fallback.
- [x] Add Top 25 results table rendering.
- [x] Add headless GUI smoke tests.
- [x] Address Phase 4 review blockers and minor findings.

## TODO Queue

1. Ask Claude Code to verify the Phase 4 leftover/risk fixes.
2. Start Phase 5 ARIS core parity integration if review clears.
3. Keep one manual desktop click-through on the Phase 9 packaging checklist.

## Blockers

- Windows packaging cannot be fully validated from the current macOS/Linux-like local environment unless a Windows runner or machine is provided.
- The default shell `python3` is Python 3.14. Use `.venv/bin/python` or activate the Python 3.12 virtual environment for development commands.
- WhiteboxTools `FillDepressions` panics on the synthetic DEM when its working directory differs from the output directory. The adapter now runs that command with `output_path.parent` as the temporary work directory and restores the original work directory afterward.

## Decisions

- 2026-05-28: Codex is the repository owner for implementation, integration, validation, and final release evidence.
- 2026-05-28: Claude Code is used for planning, architecture review, PR-style review, and isolated parallel work.
- 2026-05-28: Sequential handoffs are required for shared files and risky changes; parallel work is allowed only with explicit file ownership.
- 2026-05-28: v1.0.0 will be delivered through staged gates from v0.1.0 to v1.0.0.
- 2026-05-28: Phase 2 hydrology uses `BreachDepressionsLeastCost` as the default DEM preconditioning command because it matches the architecture decision and succeeds on the synthetic DEM where `FillDepressions` panics.
- 2026-05-29: Doline detection uses a separate `FillDepressions` raster for fill-subtract depth while hydrology keeps `BreachDepressionsLeastCost` for flow products.

## Checkpoints

- 2026-05-28T00:00:00+02:00 | Orchestration setup | Added agent workflow and v1.0.0 release plan documentation | Validation: documentation files created; no code tests applicable.
- 2026-05-28T12:15:00+02:00 | Phase 0 | Added Python package skeleton, CLI doctor command, GUI packaging spike entrypoint, Makefile, pyproject, smoke tests, README, gitignore, and PyInstaller spec stub | Validation: `make test` pass (2 tests); `make lint` pass; `make doctor` pass; `make typecheck` blocked by missing mypy; `make package` blocked by missing PyInstaller.
- 2026-05-28T12:35:00+02:00 | Phase 0 review fixes | Applied Claude review feedback: Python 3.12 venv, dynamic version, contextily dependency, PyInstaller spec path fix, repo-local PyInstaller cache, typed pytest fixture, `py.typed`, README target docs, UPX disabled, git initialized | Validation: `.venv/bin/python -m pip install -e ".[dev,package]"` pass; `make PYTHON=.venv/bin/python test` pass (2 tests); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass; `make PYTHON=.venv/bin/python doctor` pass; `make PYTHON=.venv/bin/python package` pass.
- 2026-05-28T12:40:00+02:00 | Phase 0 commit | Created initial repository commit `1e63253` for v0.1.0 skeleton and documentation after purging third-party binary/PDF assets from git history | Validation: `git filter-branch` removed `ARIS Lidar Prospector - Documentation v3a.pdf` from all commits; `git rev-list --objects --all` shows no PDF/EXE assets; `find . -maxdepth 2 -name "*.pdf" -o -name "*.exe"` shows no PDF/EXE assets.
- 2026-05-28T13:20:00+02:00 | Phase 1 contracts | Added shared Pydantic v2 contracts in `src/karstlab/data/schemas.py`, exported data-layer model imports, schema validation tests, and `.pyinstaller/` clean target | Validation: `make PYTHON=.venv/bin/python test` pass (14 tests); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass.
- 2026-05-28T13:45:00+02:00 | Phase 1 contract review fixes | Aligned persisted contract field names with architecture docs, switched schema versions to `1.0.0`, added pipeline version/CRS/timestamp/status/warning fields, removed unused GeoJSON alias, and added strict/round-trip/edge-case tests | Validation: `make PYTHON=.venv/bin/python test` pass (22 tests); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass.
- 2026-05-28T14:05:00+02:00 | Phase 1 project I/O | Added project slugging, canonical directory/path constants, project creation, atomic project save/load, and canonical output filenames | Validation: `make PYTHON=.venv/bin/python test` pass (30 tests); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass.
- 2026-05-28T14:25:00+02:00 | Phase 1 project I/O review fixes | Moved exports to `output/export`, added `output/rasters` and `output/vectors`, changed map output to `map/index.html`, renamed statistics output to `statistics.json`, persisted `logs_dir`, expanded canonical filename coverage, and added overwrite/load-error/path tests | Validation: `make PYTHON=.venv/bin/python test` pass (33 tests); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass.
- 2026-05-28T14:45:00+02:00 | Phase 1 land profiles | Added bundled `fr`, `nl`, `be`, and `generic` land profile JSON files, land profile loader/fallback helpers, and generated JSON Schema resources for land profile, project, and user settings | Validation: `make PYTHON=.venv/bin/python test` pass (41 tests); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass.
- 2026-05-28T15:05:00+02:00 | Phase 1 raster I/O start | Added synthetic 100x100 DEM fixture with three known depressions, GeoTIFF read/write helpers, raster metadata contracts, raster I/O tests, and mypy config for geospatial packages without stubs | Validation: `make PYTHON=.venv/bin/python test` pass (44 tests); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass; `make PYTHON=.venv/bin/python check-schemas` pass.
- 2026-05-28T15:25:00+02:00 | Phase 1 CRS helpers | Added CRS detection, metric CRS checks, raster reprojection to metric CRS and WGS84, and tests covering missing CRS and synthetic DEM reprojection | Validation: `make PYTHON=.venv/bin/python test` pass (50 tests, one expected rasterio NotGeoreferencedWarning in missing-CRS fixture); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass; `make PYTHON=.venv/bin/python check-schemas` pass.
- 2026-05-28T15:45:00+02:00 | Phase 1 VRT assembly | Added GDAL VRT XML builder for north-up single-band DEM tiles, optional GeoTIFF export from VRT, and tests for two-tile mosaics, GeoTIFF export, empty input, and CRS mismatch | Validation: `make PYTHON=.venv/bin/python test` pass (55 tests, one expected rasterio NotGeoreferencedWarning in missing-CRS fixture); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass; `make PYTHON=.venv/bin/python check-schemas` pass.
- 2026-05-28T16:20:00+02:00 | Phase 1 VRT review fixes | Added grid-alignment tolerance validation, safe dataset open/close handling, and VRT source paths that work for tiles outside the VRT directory | Validation: `make PYTHON=.venv/bin/python test` pass (57 tests, one expected rasterio NotGeoreferencedWarning in missing-CRS fixture); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass.
- 2026-05-28T16:30:00+02:00 | Phase 1 WhiteboxTools verification | Verified the Python wrapper can download and run the platform WhiteboxTools binary in the active Python 3.12 venv | Validation: `.venv/bin/python -c "from whitebox.whitebox_tools import WhiteboxTools; wbt=WhiteboxTools(); print(wbt.version())"` reports `WhiteboxTools v2.4.0`.
- 2026-05-28T16:40:00+02:00 | Phase 1 vector I/O | Added WGS84 GeoJSON export, KML export for points/lines/polygons, GPX waypoint export, GPX waypoint import, and KML point import helpers | Validation: `make PYTHON=.venv/bin/python test` pass (61 tests, one expected rasterio NotGeoreferencedWarning in missing-CRS fixture); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass; `make PYTHON=.venv/bin/python check-schemas` pass.
- 2026-05-28T16:47:00+02:00 | Phase 1 vector I/O review fixes | Fixed non-mutating KML description generation, replaced fragile CRS string comparison with semantic pyproj CRS equality, and validated GPX geometry type before writing | Validation: `make PYTHON=.venv/bin/python test` pass (64 tests, one expected rasterio NotGeoreferencedWarning in missing-CRS fixture); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass; `make PYTHON=.venv/bin/python check-schemas` pass.
- 2026-05-28T22:10:00+02:00 | Phase 2 Whitebox adapter start | Added `WhiteboxAdapter` with executable/version access, command forwarding, output/error checks, and `HydrologyAnalyzer` for breach/fill, D8 pointer, flow accumulation, and stream extraction | Validation: `make PYTHON=.venv/bin/python test` pass (70 tests, one expected rasterio NotGeoreferencedWarning in missing-CRS fixture); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass; `make PYTHON=.venv/bin/python check-schemas` pass; real WhiteboxTools smoke on synthetic DEM creates `dem_filled.tif`, `d8_pointer.tif`, `flow_accum.tif`, and `streams.tif`.
- 2026-05-29T09:41:00+02:00 | Phase 2 adapter review fixes | Added callback parameters and forwarding across Whitebox adapter and hydrology wrapper methods, introduced a business-layer `HydrologyBackend` protocol, and removed the business layer's concrete dependency on infrastructure | Validation: `make PYTHON=.venv/bin/python test` pass (72 tests, one expected rasterio NotGeoreferencedWarning in missing-CRS fixture); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass; `make PYTHON=.venv/bin/python check-schemas` pass.
- 2026-05-29T09:51:00+02:00 | Phase 2 parallel validator and terrain | Parallel agent session added the scientific DEM validator and terrain helpers for hillshade, slope, and curvature, with business-layer exports | Validation: `make PYTHON=.venv/bin/python test` pass (90 tests, one expected rasterio NotGeoreferencedWarning in missing-CRS fixture); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass; `make PYTHON=.venv/bin/python check-schemas` pass.
- 2026-05-29T10:09:00+02:00 | Phase 2 validator and terrain review fixes | Fixed NaN NoData masking in DEM validation, added minimum 2x2 terrain-array guard, exported `CellSize`, and expanded validator/terrain tests for NaN NoData, multi-band rasters, rectangular cell sizes, and negative tuple cell size | Validation: `make PYTHON=.venv/bin/python test` pass (94 tests, one expected rasterio NotGeoreferencedWarning in missing-CRS fixture); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass; `make PYTHON=.venv/bin/python check-schemas` pass.
- 2026-05-29T10:13:00+02:00 | Phase 3 parallel dolines/ranking/contours | Parallel agent session added fill-subtract doline detection, deterministic depression ranking, and contour extraction as GeoDataFrame LineStrings | Validation: `make PYTHON=.venv/bin/python test` pass (110 tests, one expected rasterio NotGeoreferencedWarning in missing-CRS fixture); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass; `make PYTHON=.venv/bin/python check-schemas` pass.
- 2026-05-29T13:37:00+02:00 | Phase 3 review fixes | Exported doline detector symbols, standardized doline centroids and geometries to WGS84, added required-CRS validation, cached CRS transformers per detection run, switched pixel area to affine determinant, documented depth confidence thresholds, and filled Phase 3 test gaps | Validation: `make PYTHON=.venv/bin/python test` pass (117 tests, one expected rasterio NotGeoreferencedWarning in missing-CRS fixture); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass; `make PYTHON=.venv/bin/python check-schemas` pass.
- 2026-05-29T15:10:00+02:00 | Headless analyze/export/map/report integration | Added `karstlab analyze`, headless pipeline orchestration, statistics/provenance JSON, Top 25 GeoJSON/KML/GPX, contour GeoJSON/KML, Folium map HTML, report HTML with embedded map iframe, and Whitebox `FillDepressions` work-dir handling | Validation: `make PYTHON=.venv/bin/python test` pass (134 tests, one expected rasterio NotGeoreferencedWarning in missing-CRS fixture); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass; `.venv/bin/python -m karstlab.cli.main analyze /private/tmp/karstlab_cli_smoke/dem.tif --project-dir /private/tmp/karstlab_cli_smoke/projects --name "Synthetic Smoke" --profile generic --overwrite` pass, detected 3 Top depressions and wrote pipeline result, statistics, map, report, GPX/KML/GeoJSON exports.
- 2026-05-29T15:40:00+02:00 | Phase 4 minimal GUI shell | Added PySide6 `MainWindow`, map/sidebar splitter, Tools/Results/Layers/Markers/Export tabs, DEM path selection, Analyze button, `QThread` analysis worker, QWebEngine map view with QTextBrowser fallback, Top 25 results table rendering, and headless GUI smoke tests | Validation: `make PYTHON=.venv/bin/python test` pass (141 tests, one expected rasterio NotGeoreferencedWarning in missing-CRS fixture); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass; `QT_QPA_PLATFORM=offscreen .venv/bin/python -c "from karstlab.presentation.app import MainWindow; from PySide6.QtWidgets import QApplication; app=QApplication.instance() or QApplication([]); window=MainWindow(); print(window.windowTitle()); print(window.sidebar.count()); window.close()"` pass, prints `KarstLab 0.1.0` and `5`.
- 2026-05-29T16:05:00+02:00 | Phase 4 review fixes | Added close guards for running analysis, cooperative cancel request, traceback logging with log-file path in failure dialogs, fuller dark-theme QSS, project output folder selection, export button handlers, map-missing fallback, progress value updates from callback messages, and regression tests for close/error-log behavior | Validation: `make PYTHON=.venv/bin/python test` pass (143 tests, one expected rasterio NotGeoreferencedWarning in missing-CRS fixture); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass; GUI import smoke with `QT_QPA_PLATFORM=offscreen` pass, prints `KarstLab 0.1.0` and `5`.
- 2026-05-29T16:35:00+02:00 | Phase 4 leftover/risk fixes | Hardened percent parsing for malformed callback messages, added QSS hover/title polish, made layer controls persist visible/opacity state, wired marker GPX/KML import buttons to selected files, and ran a native macOS window show/close smoke without offscreen mode | Validation: `make PYTHON=.venv/bin/python test` pass (147 tests, one expected rasterio NotGeoreferencedWarning in missing-CRS fixture); `make PYTHON=.venv/bin/python lint` pass; `make PYTHON=.venv/bin/python typecheck` pass; native `.venv/bin/python -c` GUI smoke pass, prints `KarstLab 0.1.0` and `5`.

## Next Action

Ask Claude Code to verify the Phase 4 leftover/risk fixes before Phase 5.
