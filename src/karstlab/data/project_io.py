"""Project directory creation and persistence helpers."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from karstlab.data.schemas import AnalysisParams, Locale, ProjectFile

PROJECT_FILENAME = "project.karstlab"
PIPELINE_RESULT_FILENAME = "pipeline_result.json"
STATISTICS_FILENAME = "analysis_statistics.json"
MAP_FILENAME = "interactive_map.html"
REPORT_FILENAME = "report.html"
ASSEMBLED_DEM_FILENAME = "assembled_dem.tif"

PROJECT_DIRECTORIES = ("input", "output", "export", "map", "cache", "logs")

CANONICAL_FILENAMES = {
    "project": PROJECT_FILENAME,
    "pipeline_result": PIPELINE_RESULT_FILENAME,
    "statistics": STATISTICS_FILENAME,
    "interactive_map": MAP_FILENAME,
    "report": REPORT_FILENAME,
    "assembled_dem": ASSEMBLED_DEM_FILENAME,
}


@dataclass(frozen=True)
class ProjectPaths:
    project_dir: Path
    input_dir: Path
    output_dir: Path
    export_dir: Path
    map_dir: Path
    cache_dir: Path
    logs_dir: Path
    project_file: Path


def slugify_project_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_name.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "project"


def build_project_paths(base_dir: Path, slug: str) -> ProjectPaths:
    project_dir = base_dir / slug
    return ProjectPaths(
        project_dir=project_dir,
        input_dir=project_dir / "input",
        output_dir=project_dir / "output",
        export_dir=project_dir / "export",
        map_dir=project_dir / "map",
        cache_dir=project_dir / "cache",
        logs_dir=project_dir / "logs",
        project_file=project_dir / PROJECT_FILENAME,
    )


def canonical_output_paths(project: ProjectFile) -> dict[str, Path]:
    return {
        "project": project.project_dir / PROJECT_FILENAME,
        "pipeline_result": project.output_dir / PIPELINE_RESULT_FILENAME,
        "statistics": project.export_dir / STATISTICS_FILENAME,
        "interactive_map": project.map_dir / MAP_FILENAME,
        "report": project.export_dir / REPORT_FILENAME,
        "assembled_dem": project.input_dir / ASSEMBLED_DEM_FILENAME,
        "top_depressions_gpx": project.export_dir / f"Top_Depressions_{project.slug}.gpx",
        "dolines_geojson": project.export_dir / f"dolines_{project.slug}.geojson",
        "dolines_kml": project.export_dir / f"dolines_{project.slug}.kml",
        "contours_geojson": project.export_dir / f"contours_{project.slug}.geojson",
        "contours_kml": project.export_dir / f"contours_{project.slug}.kml",
    }


def create_project(
    *,
    base_dir: Path,
    name: str,
    land_profile: str,
    crs_analysis: str,
    analysis_params: AnalysisParams | None = None,
    language: Locale = Locale.EN,
    slug: str | None = None,
    overwrite: bool = False,
) -> ProjectFile:
    project_slug = slug or slugify_project_name(name)
    paths = build_project_paths(base_dir, project_slug)

    if paths.project_dir.exists() and not overwrite:
        raise FileExistsError(f"Project directory already exists: {paths.project_dir}")

    for directory in (
        paths.input_dir,
        paths.output_dir,
        paths.export_dir,
        paths.map_dir,
        paths.cache_dir,
        paths.logs_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    project = ProjectFile(
        name=name,
        slug=project_slug,
        created=now,
        modified=now,
        project_dir=paths.project_dir,
        input_dir=paths.input_dir,
        output_dir=paths.output_dir,
        export_dir=paths.export_dir,
        map_dir=paths.map_dir,
        cache_dir=paths.cache_dir,
        land_profile=land_profile,
        crs_analysis=crs_analysis,
        language=language,
        analysis_params=analysis_params or AnalysisParams(),
    )
    return save_project(project, paths.project_file, touch_modified=False)


def save_project(
    project: ProjectFile,
    path: Path | None = None,
    *,
    touch_modified: bool = True,
) -> ProjectFile:
    project_to_save = (
        project.model_copy(update={"modified": datetime.now(UTC)}) if touch_modified else project
    )
    target = path or project_to_save.project_dir / PROJECT_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)

    payload = project_to_save.model_dump(mode="json")
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return project_to_save


def load_project(path: Path) -> ProjectFile:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ProjectFile.model_validate(payload)

