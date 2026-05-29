from __future__ import annotations

from pathlib import Path

from karstlab.data.schemas import AnalysisParams, Locale, UserSettings
from karstlab.data.user_settings import add_recent_project, load_user_settings, save_user_settings


def test_load_user_settings_returns_defaults_when_file_missing(tmp_path: Path) -> None:
    settings = load_user_settings(tmp_path / "nonexistent.json")
    assert isinstance(settings, UserSettings)
    assert settings.recent_projects == []


def test_load_user_settings_returns_defaults_on_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")
    settings = load_user_settings(path)
    assert isinstance(settings, UserSettings)


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    original = UserSettings(language=Locale.NL, land_profile="fr")
    save_user_settings(original, path)
    loaded = load_user_settings(path)
    assert loaded.language == original.language
    assert loaded.land_profile == original.land_profile


def test_save_is_atomic(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = UserSettings()
    save_user_settings(settings, path)
    assert path.exists()
    assert not path.with_suffix(".json.tmp").exists()


def test_save_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "settings.json"
    save_user_settings(UserSettings(), path)
    assert path.exists()


def test_add_recent_project_prepends_and_deduplicates(tmp_path: Path) -> None:
    p1 = tmp_path / "a.karstlab"
    p2 = tmp_path / "b.karstlab"
    settings = UserSettings(recent_projects=[p1, p2])
    updated = add_recent_project(settings, p1)
    assert updated.recent_projects[0] == p1
    assert len(updated.recent_projects) == 2


def test_add_recent_project_caps_at_five(tmp_path: Path) -> None:
    paths = [tmp_path / f"{i}.karstlab" for i in range(6)]
    settings = UserSettings(recent_projects=paths[:5])
    updated = add_recent_project(settings, paths[5])
    assert len(updated.recent_projects) == 5
    assert updated.recent_projects[0] == paths[5]


def test_user_settings_stores_analysis_params() -> None:
    params = AnalysisParams(contour_interval_m=10.0)
    settings = UserSettings(analysis_params=params)
    assert settings.analysis_params.contour_interval_m == 10.0


def test_save_and_load_preserves_last_project_dir(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    project_dir = tmp_path / "myproject"
    settings = UserSettings(last_project_dir=project_dir)
    save_user_settings(settings, settings_path)
    loaded = load_user_settings(settings_path)
    assert loaded.last_project_dir == project_dir
