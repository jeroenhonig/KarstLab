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

- Phase: Phase 0 - Setup And Packaging Spike
- Objective: Turn the documentation-only repository into a Python application skeleton with early dependency and packaging validation.
- Exit criteria:
  - Python package skeleton exists.
  - Tests/lint commands exist.
  - Synthetic DEM fixture exists.
  - WhiteboxTools and GDAL/PROJ packaging risks are verified or documented.

## Phase Checklist

- [x] Capture agent orchestration workflow.
- [x] Capture v1.0.0 release gates.
- [x] Create Python 3.12+ project skeleton.
- [ ] Add shared Pydantic contracts.
- [ ] Add synthetic DEM fixture.
- [ ] Add initial tests.
- [x] Run local smoke validation.
- [x] Install/verify missing development tools (`mypy`, `PyInstaller`).
- [x] Initialize git repository.

## TODO Queue

1. Ask Claude Code for a short follow-up review of the v0.1.0 review fixes.
2. Add Pydantic schemas for shared contracts.
3. Add synthetic DEM fixture and first raster I/O tests.
4. Add raster I/O implementation.
5. Verify GDAL/PROJ and WhiteboxTools on the active machine.
6. Expand packaging spike to include GDAL/PROJ and WhiteboxTools.

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

## Next Action

Ask Claude Code for a short follow-up review of the v0.1.0 review fixes before moving to Phase 1 shared contracts.
