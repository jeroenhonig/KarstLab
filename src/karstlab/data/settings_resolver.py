"""Resolve AnalysisParams from the 5-level settings priority chain."""

from __future__ import annotations

from typing import Any

from karstlab.data.schemas import AnalysisParams, LandProfile, ProjectFile, UserSettings

_DEFAULTS = AnalysisParams()
_FIELDS = list(AnalysisParams.model_fields)


def _explicit(params: AnalysisParams) -> dict[str, Any]:
    """Return only fields the user explicitly set (not Pydantic defaults)."""
    dump = params.model_dump()
    return {k: dump[k] for k in params.model_fields_set}


def resolve_analysis_params(
    *,
    ui_overrides: dict[str, Any] | None = None,
    project: ProjectFile | None = None,
    user_settings: UserSettings | None = None,
    land_profile: LandProfile | None = None,
) -> AnalysisParams:
    """Return AnalysisParams resolved from the 5-level priority chain.

    Priority (highest → lowest):
      1. ui_overrides          — explicit dict keys only
      2. project.analysis_params   — only fields explicitly set on the model
      3. user_settings.analysis_params — only fields explicitly set on the model
      4. land_profile.analysis_defaults — all fields (profile author intent)
      5. built-in AnalysisParams defaults
    """
    sources: list[dict[str, Any]] = [
        ui_overrides or {},
        _explicit(project.analysis_params) if project else {},
        _explicit(user_settings.analysis_params) if user_settings else {},
        land_profile.analysis_defaults.model_dump() if land_profile else {},
        _DEFAULTS.model_dump(),
    ]

    resolved: dict[str, Any] = {}
    for field in _FIELDS:
        for source in sources:
            if field in source:
                resolved[field] = source[field]
                break

    return AnalysisParams.model_validate(resolved)


__all__ = ["resolve_analysis_params"]
