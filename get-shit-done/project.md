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

- Phase: Phase 3 - Dolines, Ranking & Contours
- Objective: Detect depressions from fill-subtract rasters, rank top depressions, and extract contour vectors.
- Exit criteria:
  - Doline detection finds known synthetic depressions.
  - Depth and area filtering work with configured thresholds.
  - Quality flags cover edge proximity, NoData adjacency, depth confidence, shape regularity, and nested placeholders.
  - Ranking returns deterministic Top 25 results with sequential rank IDs.
  - Contour extraction returns valid GeoDataFrame LineStrings.

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

## TODO Queue

1. Ask Claude Code to review Phase 3 doline detection, ranking, and contours.
2. Address Claude Code findings on doline detection/ranking/contours.
3. Start Phase 4 exporter, provenance, and statistics after Phase 3 review is clear.

## Blockers

- Windows packaging cannot be fully validated from the current macOS/Linux-like local environment unless a Windows runner or machine is provided.
- The default shell `python3` is Python 3.14. Use `.venv/bin/python` or activate the Python 3.12 virtual environment for development commands.
- WhiteboxTools `FillDepressions` panicked on the synthetic DEM with NoData during manual smoke. `BreachDepressionsLeastCost` works on the same DEM and remains the default fill/preconditioning path.

## Decisions

- 2026-05-28: Codex is the repository owner for implementation, integration, validation, and final release evidence.
- 2026-05-28: Claude Code is used for planning, architecture review, PR-style review, and isolated parallel work.
- 2026-05-28: Sequential handoffs are required for shared files and risky changes; parallel work is allowed only with explicit file ownership.
- 2026-05-28: v1.0.0 will be delivered through staged gates from v0.1.0 to v1.0.0.
- 2026-05-28: Phase 2 hydrology uses `BreachDepressionsLeastCost` as the default DEM preconditioning command because it matches the architecture decision and succeeds on the synthetic DEM where `FillDepressions` panics.

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

## Next Action

Ask Claude Code to review Phase 3 doline detection, ranking, and contours.
