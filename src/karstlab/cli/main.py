"""KarstLab command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path

from karstlab.business.pipeline import run_headless_analysis
from karstlab.data.land_profiles import load_land_profile
from karstlab.data.project_io import create_project, save_project, slugify_project_name
from karstlab.infrastructure.whitebox_adapter import WhiteboxAdapter
from karstlab.version import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="karstlab",
        description="KarstLab terrain analysis toolkit.",
    )
    parser.add_argument("--version", action="version", version=f"KarstLab {__version__}")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("doctor", help="Check the local KarstLab runtime environment.")
    analyze = subparsers.add_parser("analyze", help="Run headless DEM analysis.")
    analyze.add_argument("dem", type=Path, help="Input GeoTIFF DEM path.")
    analyze.add_argument(
        "--project-dir",
        type=Path,
        required=True,
        help="Directory where the KarstLab project directory will be created.",
    )
    analyze.add_argument("--name", default=None, help="Project name. Defaults to the DEM stem.")
    analyze.add_argument("--profile", default="generic", help="Bundled land profile id.")
    analyze.add_argument("--overwrite", action="store_true", help="Overwrite an existing project.")

    return parser


def run_doctor() -> int:
    print(f"KarstLab {__version__}")
    print("Runtime check: package import OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return run_doctor()
    if args.command == "analyze":
        return run_analyze(args)

    parser.print_help()
    return 0


def run_analyze(args: argparse.Namespace) -> int:
    dem_path = args.dem.resolve()
    if not dem_path.exists():
        raise SystemExit(f"DEM does not exist: {dem_path}")

    profile = load_land_profile(args.profile)
    project_name = args.name or dem_path.stem
    project = create_project(
        base_dir=args.project_dir.resolve(),
        name=project_name,
        slug=slugify_project_name(project_name),
        land_profile=profile.id,
        crs_analysis=profile.default_crs,
        analysis_params=profile.analysis_defaults,
        overwrite=args.overwrite,
    )
    project = save_project(project.model_copy(update={"dem_paths": [dem_path]}))

    result = run_headless_analysis(
        project,
        hydrology_backend=WhiteboxAdapter.create(work_dir=project.output_dir / "rasters"),
        callback=lambda message: print(message) if message else None,
    )
    project = save_project(
        project.model_copy(
            update={"last_pipeline_result": project.output_dir / "pipeline_result.json"}
        )
    )

    print(f"Analysis complete: {len(result.top_depressions)} top depressions")
    print(f"Project: {project.project_dir}")
    print(f"Pipeline result: {project.last_pipeline_result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
