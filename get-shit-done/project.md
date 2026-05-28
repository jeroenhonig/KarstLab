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

- Phase: Phase 1 - Shared Contracts
- Objective: Define the Pydantic contracts that all later data, pipeline, GUI, and export code will import.
- Exit criteria:
  - `AnalysisParams`, `ProjectFile`, `UserSettings`, `LandProfile`, `DepressionResult`, and `PipelineResult` exist.
  - JSON Schema export works for project, settings, and land profiles.
  - Schema validation tests pass.
  - Claude Code reviews the contracts before project directory creation starts.

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

## TODO Queue

1. Ask Claude Code to verify vector I/O review fixes.
2. Start Phase 2 WhiteboxTools adapter and hydrology wrapper after Claude confirms no blockers.
3. Defer `contours_to_vector()` until contour generation exists in Phase 4.

## Blockers

- Windows packaging cannot be fully validated from the current macOS/Linux-like local environment unless a Windows runner or machine is provided.
- The default shell `python3` is Python 3.14. Use `.venv/bin/python` or activate the Python 3.12 virtual environment for development commands.

## Decisions

- 2026-05-28: Codex is the repository owner for implementation, integration, validation, and final release evidence.
- 2026-05-28: Claude Code is used for planning, architecture review, PR-style review, and isolated parallel work.
- 2026-05-28: Sequential handoffs are required for shared files and risky changes; parallel work is allowed only with explicit file ownership.
- 2026-05-28: v1.0.0 will be delivered through staged gates from v0.1.0 to v1.0.0.

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

## Next Action

Ask Claude Code to verify vector I/O review fixes before starting the Phase 2 WhiteboxTools adapter and hydrology wrapper.
