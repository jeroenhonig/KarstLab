"""Resolve AnalysisParams from the 5-level settings priority chain."""

from __future__ import annotations

from typing import Any

from karstlab.data.schemas import AnalysisParams, LandProfile, ProjectFile, UserSettings

_DEFAULTS = AnalysisParams()
_FIELDS = list(AnalysisParams.model_fields)


def resolve_analysis_params(
    *,
    ui_overrides: dict[str, Any] | None = None,
    project: ProjectFile | None = None,
    user_settings: UserSettings | None = None,
    land_profile: LandProfile | None = None,
) -> AnalysisParams:
    """Return AnalysisParams resolved from the 5-level priority chain.

    Priority (highest → lowest):
      1. ui_overrides
      2. project.analysis_params
      3. user_settings.analysis_params
      4. land_profile.analysis_defaults
      5. built-in AnalysisParams defaults
    """
    sources: list[dict[str, Any]] = [
        ui_overrides or {},
        project.analysis_params.model_dump() if project else {},
        user_settings.analysis_params.model_dump() if user_settings else {},
        land_profile.analysis_defaults.model_dump() if land_profile else {},
        _DEFAULTS.model_dump(),
    ]

    resolved: dict[str, Any] = {}
    for field in _FIELDS:
        for source in sources:
            if field in source and source[field] is not None:
                resolved[field] = source[field]
                break

    return AnalysisParams.model_validate(resolved)


__all__ = ["resolve_analysis_params"]
