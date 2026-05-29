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


def generate_html_report(
    analysis_params: AnalysisParams,
    pipeline_result: PipelineResult,
    *,
    depressions: Sequence[DepressionResult] | None = None,
    statistics: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
    map_html_path: Path | str | None = None,
    map_reference: str | None = None,
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
            "      <p>KarstLab analysis report</p>",
            f"      <h1>Project {_text(str(pipeline_result.project_id))}</h1>",
            "    </header>",
            _section("Run Summary", _run_summary(pipeline_result, len(report_depressions))),
            _section(
                "Analysis Parameters",
                _mapping_table(analysis_params.model_dump(mode="json")),
            ),
            _section("Summary Statistics", _mapping_table(report_statistics)),
            _section("Provenance", _mapping_table(report_provenance)),
            _section("Top 25 Depressions", _depressions_table(top_depressions)),
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
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
    return destination


def _run_summary(pipeline_result: PipelineResult, depression_count: int) -> str:
    rows: dict[str, Any] = {
        "Status": pipeline_result.status.value,
        "Land profile": pipeline_result.land_profile,
        "Started at": _format_datetime(pipeline_result.started_at),
        "Finished at": _format_datetime(pipeline_result.finished_at),
        "Input DEM paths": [str(path) for path in pipeline_result.input_dem_paths],
        "Output directory": str(pipeline_result.output_dir),
        "Depressions detected": depression_count,
        "Pipeline steps": len(pipeline_result.steps),
    }
    return _mapping_table(rows)


def _depressions_table(depressions: Sequence[DepressionResult]) -> str:
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
            "          <th>Rank</th>",
            "          <th>ID</th>",
            "          <th>Max depth (m)</th>",
            "          <th>Area (m2)</th>",
            "          <th>Latitude</th>",
            "          <th>Longitude</th>",
            "          <th>Depth confidence</th>",
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
