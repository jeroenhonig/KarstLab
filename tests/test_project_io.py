from __future__ import annotations

from pathlib import Path

import pytest

from karstlab.data.project_io import (
    CANONICAL_FILENAMES,
    PROJECT_DIRECTORIES,
    build_project_paths,
    canonical_output_paths,
    create_project,
    load_project,
    save_project,
    slugify_project_name,
)
from karstlab.data.schemas import AnalysisParams, Locale, ProjectFile


def test_slugify_project_name_strips_accents_and_normalizes_separators() -> None:
    assert slugify_project_name("Trou du Vent") == "trou-du-vent"
    assert slugify_project_name("Résurgence #12") == "resurgence-12"
    assert slugify_project_name("!!!") == "project"
    assert slugify_project_name("") == "project"
    assert slugify_project_name("日本語") == "project"
    assert len(slugify_project_name("Long name " * 40)) > 255


def test_build_project_paths_uses_canonical_directories(tmp_path: Path) -> None:
    paths = build_project_paths(tmp_path, "trou-du-vent")

    assert paths.project_dir == tmp_path / "trou-du-vent"
    assert paths.input_dir == paths.project_dir / "input"
    assert paths.output_dir == paths.project_dir / "output"
    assert paths.rasters_dir == paths.project_dir / "output" / "rasters"
    assert paths.vectors_dir == paths.project_dir / "output" / "vectors"
    assert paths.export_dir == paths.project_dir / "output" / "export"
    assert paths.map_dir == paths.project_dir / "map"
    assert paths.cache_dir == paths.project_dir / "cache"
    assert paths.logs_dir == paths.project_dir / "logs"
    assert paths.project_file == paths.project_dir / "project.karstlab"


def test_project_directories_constant_matches_project_paths() -> None:
    assert PROJECT_DIRECTORIES == (
        "input",
        "output",
        "output/rasters",
        "output/vectors",
        "output/export",
        "map",
        "cache",
        "logs",
    )


def test_create_project_creates_directories_and_project_file(tmp_path: Path) -> None:
    project = create_project(
        base_dir=tmp_path,
        name="Trou du Vent",
        land_profile="fr",
        crs_analysis="EPSG:2154",
        language=Locale.FR,
    )

    assert project.name == "Trou du Vent"
    assert project.slug == "trou-du-vent"
    assert project.land_profile == "fr"
    assert project.crs_analysis == "EPSG:2154"
    assert project.language == Locale.FR

    for directory_name in PROJECT_DIRECTORIES:
        assert (project.project_dir / directory_name).is_dir()

    assert (project.project_dir / CANONICAL_FILENAMES["project"]).is_file()
    assert project.export_dir == project.project_dir / "output" / "export"
    assert project.logs_dir == project.project_dir / "logs"


def test_create_project_rejects_existing_project_without_overwrite(tmp_path: Path) -> None:
    create_project(
        base_dir=tmp_path,
        name="Trou du Vent",
        land_profile="fr",
        crs_analysis="EPSG:2154",
    )

    with pytest.raises(FileExistsError):
        create_project(
            base_dir=tmp_path,
            name="Trou du Vent",
            land_profile="fr",
            crs_analysis="EPSG:2154",
        )


def test_create_project_overwrite_updates_project_file_without_cleaning_outputs(
    tmp_path: Path,
) -> None:
    project = create_project(
        base_dir=tmp_path,
        name="Trou du Vent",
        land_profile="fr",
        crs_analysis="EPSG:2154",
    )
    stale_output = project.output_dir / "stale.txt"
    stale_output.write_text("stale", encoding="utf-8")

    overwritten = create_project(
        base_dir=tmp_path,
        name="Trou du Vent Updated",
        slug="trou-du-vent",
        land_profile="generic",
        crs_analysis="EPSG:3857",
        overwrite=True,
    )
    loaded = load_project(overwritten.project_dir / "project.karstlab")

    assert stale_output.read_text(encoding="utf-8") == "stale"
    assert loaded.name == "Trou du Vent Updated"
    assert loaded.land_profile == "generic"
    assert loaded.crs_analysis == "EPSG:3857"


def test_create_project_supports_explicit_slug_and_analysis_params(tmp_path: Path) -> None:
    params = AnalysisParams(contour_interval_m=10.0)
    project = create_project(
        base_dir=tmp_path,
        name="Custom Name",
        slug="custom-project",
        land_profile="generic",
        crs_analysis="EPSG:3857",
        analysis_params=params,
    )

    assert project.slug == "custom-project"
    assert project.project_dir == tmp_path / "custom-project"
    assert project.analysis_params.contour_interval_m == 10.0


def test_save_and_load_project_round_trip(tmp_path: Path) -> None:
    project = create_project(
        base_dir=tmp_path,
        name="Aven Test",
        land_profile="fr",
        crs_analysis="EPSG:2154",
    )
    updated = save_project(
        project.model_copy(update={"dem_paths": [project.input_dir / "dem.tif"]})
    )
    loaded = load_project(project.project_dir / "project.karstlab")

    assert loaded == updated
    assert loaded.dem_paths == [project.input_dir / "dem.tif"]
    assert loaded.modified >= project.modified


def test_load_project_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_project(tmp_path / "missing.karstlab")


def test_load_project_invalid_json_raises_value_error(tmp_path: Path) -> None:
    project_file = tmp_path / "broken.karstlab"
    project_file.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError):
        load_project(project_file)


def test_canonical_output_paths_include_expected_release_outputs(tmp_path: Path) -> None:
    project = ProjectFile(
        name="Trou du Vent",
        slug="trou-du-vent",
        project_dir=tmp_path / "trou-du-vent",
        input_dir=tmp_path / "trou-du-vent" / "input",
        output_dir=tmp_path / "trou-du-vent" / "output",
        export_dir=tmp_path / "trou-du-vent" / "output" / "export",
        map_dir=tmp_path / "trou-du-vent" / "map",
        cache_dir=tmp_path / "trou-du-vent" / "cache",
        logs_dir=tmp_path / "trou-du-vent" / "logs",
        crs_analysis="EPSG:2154",
    )

    paths = canonical_output_paths(project)

    assert paths["project"] == project.project_dir / "project.karstlab"
    assert paths["assembled_dem"] == project.input_dir / "assembled_dem.tif"
    assert paths["pipeline_result"] == project.output_dir / "pipeline_result.json"
    assert paths["statistics"] == project.export_dir / "statistics.json"
    assert paths["report"] == project.export_dir / "report.html"
    assert paths["interactive_map"] == project.map_dir / "index.html"
    assert paths["top_depressions_gpx"] == project.export_dir / "Top_Depressions_trou-du-vent.gpx"
    assert paths["dolines_geojson"] == project.export_dir / "dolines_trou-du-vent.geojson"
    assert paths["dolines_kml"] == project.export_dir / "dolines_trou-du-vent.kml"
    assert paths["contours_geojson"] == project.export_dir / "contours_trou-du-vent.geojson"
    assert paths["contours_kml"] == project.export_dir / "contours_trou-du-vent.kml"
