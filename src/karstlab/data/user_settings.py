"""Load and persist user-level KarstLab settings."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from karstlab.data.schemas import UserSettings

_MAX_RECENT_PROJECTS = 5


def _config_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "karstlab" / "settings.json"


def load_user_settings(path: Path | None = None) -> UserSettings:
    target = path or _config_path()
    if not target.exists():
        return UserSettings()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return UserSettings.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, OSError):
        return UserSettings()


def save_user_settings(settings: UserSettings, path: Path | None = None) -> UserSettings:
    target = path or _config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = settings.model_dump(mode="json")
    tmp = target.with_suffix(f"{target.suffix}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(target)
    return settings


def add_recent_project(settings: UserSettings, project_path: Path) -> UserSettings:
    """Return updated settings with project_path at the front of recent_projects (max 5)."""
    existing = [p for p in settings.recent_projects if p != project_path]
    recent = [project_path, *existing][:_MAX_RECENT_PROJECTS]
    return settings.model_copy(update={"recent_projects": recent})


__all__ = ["add_recent_project", "load_user_settings", "save_user_settings"]
