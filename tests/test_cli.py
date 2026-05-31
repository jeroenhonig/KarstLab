from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from karstlab.cli.main import build_parser, run_analyze
from karstlab.data.project_io import load_project


def test_analyze_parser_accepts_multiple_dem_paths() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "analyze",
            "left.tif",
            "right.tif",
            "--project-dir",
            "projects",
        ]
    )

    assert args.dem == [Path("left.tif"), Path("right.tif")]


def test_run_analyze_persists_multiple_dem_paths(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    left = tmp_path / "left.tif"
    right = tmp_path / "right.tif"
    left.write_text("left", encoding="utf-8")
    right.write_text("right", encoding="utf-8")
    captured_dem_paths: list[Path] = []

    def fake_run_headless_analysis(project: Any, **_kwargs: Any) -> Any:
        captured_dem_paths.extend(project.dem_paths)
        return SimpleNamespace(top_depressions=[])

    monkeypatch.setattr("karstlab.cli.main.run_headless_analysis", fake_run_headless_analysis)
    monkeypatch.setattr("karstlab.cli.main.WhiteboxAdapter.create", lambda **_kwargs: object())

    exit_code = run_analyze(
        argparse.Namespace(
            dem=[left, right],
            project_dir=tmp_path / "projects",
            name="CLI Multi",
            profile="generic",
            overwrite=True,
        )
    )

    project = load_project(tmp_path / "projects" / "cli-multi" / "project.karstlab")
    assert exit_code == 0
    assert captured_dem_paths == [left.resolve(), right.resolve()]
    assert project.dem_paths == [left.resolve(), right.resolve()]
