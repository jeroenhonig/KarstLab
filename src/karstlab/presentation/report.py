"""HTML report generation for pipeline results."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from karstlab.business.depression_ranker import rank_depressions
from karstlab.data.schemas import AnalysisParams, DepressionResult, PipelineResult

_REPORT_I18N: dict[str, dict[str, str]] = {
    "en": {
        "title": "KarstLab analysis report",
        "project": "Project",
        "run_summary": "Run Summary",
        "analysis_parameters": "Analysis Parameters",
        "summary_statistics": "Summary Statistics",
        "provenance": "Provenance",
        "top_depressions": "Top 25 Depressions",
        "rank": "Rank",
        "id": "ID",
        "depth": "Depth (m)",
        "area": "Area (m²)",
        "lat": "Latitude",
        "lon": "Longitude",
        "flags": "Flags",
        "started": "Started",
        "finished": "Finished",
        "depressions_found": "Depressions found",
        "top_depressions_count": "Top depressions",
        "land_profile": "Land profile",
    },
    "nl": {
        "title": "KarstLab-analyserapport",
        "project": "Project",
        "run_summary": "Overzicht",
        "analysis_parameters": "Analyseparameters",
        "summary_statistics": "Overzichtsstatistieken",
        "provenance": "Herkomst",
        "top_depressions": "Top 25 depressies",
        "rank": "Rang",
        "id": "ID",
        "depth": "Diepte (m)",
        "area": "Opp. (m²)",
        "lat": "Breedtegraad",
        "lon": "Lengtegraad",
        "flags": "Markeringen",
        "started": "Gestart",
        "finished": "Afgerond",
        "depressions_found": "Depressies gevonden",
        "top_depressions_count": "Top depressies",
        "land_profile": "Landprofiel",
    },
    "fr": {
        "title": "Rapport d'analyse KarstLab",
        "project": "Projet",
        "run_summary": "Résumé",
        "analysis_parameters": "Paramètres d'analyse",
        "summary_statistics": "Statistiques sommaires",
        "provenance": "Provenance",
        "top_depressions": "Top 25 dépressions",
        "rank": "Rang",
        "id": "ID",
        "depth": "Prof. (m)",
        "area": "Superficie (m²)",
        "lat": "Latitude",
        "lon": "Longitude",
        "flags": "Indicateurs",
        "started": "Démarré",
        "finished": "Terminé",
        "depressions_found": "Dépressions trouvées",
        "top_depressions_count": "Meilleures dépressions",
        "land_profile": "Profil de terrain",
    },
}


def generate_html_report(
    analysis_params: AnalysisParams,
    pipeline_result: PipelineResult,
    *,
    depressions: Sequence[DepressionResult] | None = None,
    statistics: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
    map_html_path: Path | str | None = None,
    map_reference: str | None = None,
    locale: str = "en",
) -> str:
    """Generate an HTML report for a completed analysis."""
    report_depressions = (
        list(depressions) if depressions is not None else pipeline_result.depressions
    )
    top_depressions = (
        list(pipeline_result.top_depressions)
        if pipeline_result.top_depressions
        else rank_depressions(report_depressions)
    )
    report_provenance = dict(provenance) if provenance is not None else pipeline_result.provenance
    report_statistics = dict(statistics or {})
    map_html = _read_map_html(map_html_path)
    i18n = _REPORT_I18N.get(locale, _REPORT_I18N["en"])

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1">',
            f"  <title>KarstLab report - {_text(str(pipeline_result.project_id))}</title>",
            "  <style>",
            _styles(),
            "  </style>",
            "</head>",
            "<body>",
            "  <main>",
            "    <header>",
            f"      <p>{_text(i18n['title'])}</p>",
            f"      <h1>{_text(i18n['project'])} {_text(str(pipeline_result.project_id))}</h1>",
            "    </header>",
            _section(
                i18n["run_summary"],
                _run_summary(pipeline_result, len(report_depressions), i18n),
            ),
            _section(
                i18n["analysis_parameters"],
                _mapping_table(analysis_params.model_dump(mode="json")),
            ),
            _section(i18n["summary_statistics"], _mapping_table(report_statistics)),
            _section(i18n["provenance"], _mapping_table(report_provenance)),
            _section(i18n["top_depressions"], _depressions_table(top_depressions, i18n)),
            _map_section(map_html, map_reference),
            "  </main>",
            "</body>",
            "</html>",
        ]
    )


def write_html_report(
    output_path: Path | str,
    analysis_params: AnalysisParams,
    pipeline_result: PipelineResult,
    *,
    depressions: Sequence[DepressionResult] | None = None,
    statistics: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
    map_html_path: Path | str | None = None,
    map_reference: str | None = None,
    locale: str = "en",
) -> Path:
    """Write an HTML report and return the written path."""
    destination = Path(output_path)
    html = generate_html_report(
        analysis_params,
        pipeline_result,
        depressions=depressions,
        statistics=statistics,
        provenance=provenance,
        map_html_path=map_html_path,
        map_reference=map_reference,
        locale=locale,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
    return destination


def _run_summary(
    pipeline_result: PipelineResult, depression_count: int, i18n: dict[str, str]
) -> str:
    rows: dict[str, Any] = {
        "Status": pipeline_result.status.value,
        i18n["land_profile"]: pipeline_result.land_profile,
        i18n["started"]: _format_datetime(pipeline_result.started_at),
        i18n["finished"]: _format_datetime(pipeline_result.finished_at),
        "Input DEM paths": [str(path) for path in pipeline_result.input_dem_paths],
        "Output directory": str(pipeline_result.output_dir),
        i18n["depressions_found"]: depression_count,
        "Pipeline steps": len(pipeline_result.steps),
    }
    return _mapping_table(rows)


def _depressions_table(
    depressions: Sequence[DepressionResult], i18n: dict[str, str]
) -> str:
    if not depressions:
        return '<p class="empty">No depressions available.</p>'

    rows = [
        "      <tr>"
        f"<td>{_text(str(depression.rank or index))}</td>"
        f"<td>{_text(depression.id)}</td>"
        f"<td>{depression.max_depth_m:.2f}</td>"
        f"<td>{depression.area_m2:.2f}</td>"
        f"<td>{depression.centroid.lat:.6f}</td>"
        f"<td>{depression.centroid.lon:.6f}</td>"
        f"<td>{_text(depression.quality_flags.depth_confidence.value)}</td>"
        "</tr>"
        for index, depression in enumerate(depressions[:25], start=1)
    ]
    return "\n".join(
        [
            "    <table>",
            "      <thead>",
            "        <tr>",
            f"          <th>{_text(i18n['rank'])}</th>",
            f"          <th>{_text(i18n['id'])}</th>",
            f"          <th>{_text(i18n['depth'])}</th>",
            f"          <th>{_text(i18n['area'])}</th>",
            f"          <th>{_text(i18n['lat'])}</th>",
            f"          <th>{_text(i18n['lon'])}</th>",
            f"          <th>{_text(i18n['flags'])}</th>",
            "        </tr>",
            "      </thead>",
            "      <tbody>",
            *rows,
            "      </tbody>",
            "    </table>",
        ]
    )


def _mapping_table(values: Mapping[str, Any]) -> str:
    if not values:
        return '<p class="empty">No data available.</p>'

    rows = [
        "      <tr>"
        f"<th>{_text(str(key))}</th>"
        f"<td>{_format_value(value)}</td>"
        "</tr>"
        for key, value in values.items()
    ]
    return "\n".join(["    <table>", "      <tbody>", *rows, "      </tbody>", "    </table>"])


def _format_value(value: Any) -> str:
    if value is None:
        return '<span class="muted">None</span>'
    if isinstance(value, datetime):
        return _text(_format_datetime(value))
    if isinstance(value, int | float | bool | str):
        return _text(str(value))
    if isinstance(value, Path):
        return _text(str(value))
    return f"<pre>{_text(json.dumps(value, default=str, indent=2, sort_keys=True))}</pre>"


def _map_section(map_html: str | None, map_reference: str | None) -> str:
    if map_html is None and map_reference is None:
        return ""

    content: list[str] = []
    if map_reference is not None:
        content.append(f'    <p class="map-reference">{_text(map_reference)}</p>')
    if map_html is not None:
        content.append(
            '    <iframe title="KarstLab map" srcdoc="'
            + escape(map_html, quote=True)
            + '"></iframe>'
        )
    return _section("Map", "\n".join(content))


def _read_map_html(map_html_path: Path | str | None) -> str | None:
    if map_html_path is None:
        return None
    try:
        return Path(map_html_path).read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError):
        return None


def _section(title: str, content: str) -> str:
    return "\n".join(
        [
            "    <section>",
            f"      <h2>{_text(title)}</h2>",
            content,
            "    </section>",
        ]
    )


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "None"
    return value.isoformat()


def _text(value: str) -> str:
    return escape(value, quote=True)


def _styles() -> str:
    return """
    :root { color-scheme: light; font-family: Inter, Arial, sans-serif; }
    body { margin: 0; background: #f7f8f9; color: #1f2933; }
    main { max-width: 1120px; margin: 0 auto; padding: 32px 24px 48px; }
    header { border-bottom: 2px solid #253858; margin-bottom: 24px; padding-bottom: 16px; }
    header p { color: #52606d; font-size: 0.9rem; margin: 0 0 8px; text-transform: uppercase; }
    h1 { font-size: 2rem; line-height: 1.2; margin: 0; }
    h2 { font-size: 1.2rem; margin: 0 0 12px; }
    section { margin-top: 24px; }
    table { border-collapse: collapse; width: 100%; background: #ffffff; }
    th, td { border: 1px solid #d9e2ec; padding: 8px 10px; text-align: left; vertical-align: top; }
    th { background: #eef2f6; color: #334e68; font-weight: 700; }
    td { color: #243b53; }
    pre { margin: 0; white-space: pre-wrap; word-break: break-word; }
    iframe { border: 1px solid #bcccdc; height: 520px; width: 100%; background: #ffffff; }
    .empty, .muted, .map-reference { color: #627d98; }
    """.strip()


__all__ = ["generate_html_report", "write_html_report"]
