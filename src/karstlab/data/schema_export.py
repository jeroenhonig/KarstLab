"""Generate committed JSON Schema resources from Pydantic contracts."""

from __future__ import annotations

import argparse
import json
from importlib.resources import files
from pathlib import Path

from pydantic import BaseModel

from karstlab.data.schemas import LandProfile, ProjectFile, UserSettings

type SchemaModel = type[BaseModel]

SCHEMA_MODELS: dict[str, SchemaModel] = {
    "land_profile.schema.json": LandProfile,
    "project.schema.json": ProjectFile,
    "user_settings.schema.json": UserSettings,
}


def schema_output_dir() -> Path:
    return Path(str(files("karstlab.resources.schemas")))


def render_schema(model: SchemaModel) -> str:
    return json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"


def write_schemas(output_dir: Path | None = None) -> list[Path]:
    target_dir = output_dir or schema_output_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, model in SCHEMA_MODELS.items():
        target = target_dir / filename
        target.write_text(render_schema(model), encoding="utf-8")
        written.append(target)
    return written


def check_schemas(output_dir: Path | None = None) -> list[Path]:
    target_dir = output_dir or schema_output_dir()
    stale: list[Path] = []
    for filename, model in SCHEMA_MODELS.items():
        target = target_dir / filename
        expected = render_schema(model)
        if not target.exists() or target.read_text(encoding="utf-8") != expected:
            stale.append(target)
    return stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or check KarstLab JSON Schema files.")
    parser.add_argument("--check", action="store_true", help="Check committed schemas for drift.")
    args = parser.parse_args(argv)

    if args.check:
        stale = check_schemas()
        if stale:
            for path in stale:
                print(f"stale schema: {path}")
            return 1
        print("JSON schemas are up to date")
        return 0

    for path in write_schemas():
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
