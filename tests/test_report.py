from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from karstlab.data.schemas import AnalysisParams, DepressionResult, PipelineResult, PipelineStatus
from karstlab.presentation.report import generate_html_report, write_html_report


def depression(
    depression_id: str,
    *,
    max_depth_m: float,
    area_m2: float,
    rank: int | None = None,
) -> DepressionResult:
    return DepressionResult.model_validate(
        {
            "id": depression_id,
            "rank": rank,
            "max_depth_m": max_depth_m,
            "area_m2": area_m2,
            "centroid": {"lat": 44.1, "lon": 1.2},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [1.19, 44.09],
                        [1.21, 44.09],
                        [1.21, 44.11],
                        [1.19, 44.11],
                        [1.19, 44.09],
                    ]
                ],
            },
        }
    )


def pipeline_result(depressions: list[DepressionResult]) -> PipelineResult:
    return PipelineResult(
        project_id=uuid4(),
        status=PipelineStatus.SUCCESS,
        started_at=datetime(2026, 5, 29, 9, 0, tzinfo=UTC),
        finished_at=datetime(2026, 5, 29, 9, 5, tzinfo=UTC),
        land_profile="fr",
        analysis_params=AnalysisParams(),
        input_dem_paths=[Path("input/<unsafe-dem>.tif")],
        output_dir=Path("output"),
        depressions=depressions,
        provenance={"operator": "<admin>"},
    )


def test_generate_html_report_escapes_and_renders_key_content() -> None:
    depressions = [
        depression("safe-low", max_depth_m=1.0, area_m2=100.0),
        depression("doline-<script>alert(1)</script>", max_depth_m=5.0, area_m2=200.0),
    ]
    result = pipeline_result(depressions)

    html = generate_html_report(
        result.analysis_params,
        result,
        statistics={
            "depression_count": 2,
            "mean_depth_m": 3.0,
            "note": "<b>review</b>",
            "nested": {"source": "<sensor>"},
        },
        provenance={"tool": "KarstLab <reporter>"},
        map_reference="maps/<interactive>.html",
    )

    assert "KarstLab analysis report" in html
    assert "Analysis Parameters" in html
    assert "Summary Statistics" in html
    assert "Provenance" in html
    assert "Top 25 Depressions" in html
    assert "doline-&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;review&lt;/b&gt;" in html
    assert "&lt;sensor&gt;" in html
    assert "KarstLab &lt;reporter&gt;" in html
    assert "maps/&lt;interactive&gt;.html" in html
    assert "input/&lt;unsafe-dem&gt;.tif" in html
    assert "<script>alert(1)</script>" not in html
    assert "<b>review</b>" not in html


def test_generate_html_report_limits_ranked_table_to_top_25() -> None:
    depressions = [
        depression(f"doline-{index:02d}", max_depth_m=float(index), area_m2=100.0)
        for index in range(30)
    ]
    result = pipeline_result(depressions)

    html = generate_html_report(result.analysis_params, result)

    assert "doline-29" in html
    assert "doline-05" in html
    assert "doline-04" not in html


def test_write_html_report_embeds_map_file(tmp_path: Path) -> None:
    result = pipeline_result([depression("doline-1", max_depth_m=2.0, area_m2=50.0)])
    map_path = tmp_path / "map.html"
    report_path = tmp_path / "report.html"
    map_path.write_text("<html><body><div>Map & data</div></body></html>", encoding="utf-8")

    written_path = write_html_report(
        report_path,
        result.analysis_params,
        result,
        map_html_path=map_path,
    )

    html = report_path.read_text(encoding="utf-8")
    assert written_path == report_path
    assert 'iframe title="KarstLab map"' in html
    assert "&lt;div&gt;Map &amp; data&lt;/div&gt;" in html


def test_generate_html_report_ignores_missing_map_file(tmp_path: Path) -> None:
    result = pipeline_result([depression("doline-1", max_depth_m=2.0, area_m2=50.0)])

    html = generate_html_report(
        result.analysis_params,
        result,
        map_html_path=tmp_path / "missing-map.html",
        map_reference="map/index.html",
    )

    assert 'iframe title="KarstLab map"' not in html
    assert "map/index.html" in html
