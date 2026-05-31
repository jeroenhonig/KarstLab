from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely.geometry import LineString, Point

from karstlab.business.backtest import BacktestParams, run_backtest
from karstlab.business.conduit import ConduitProjectionParams

ANALYSIS_CRS = "EPSG:2154"
_TO_WGS84 = Transformer.from_crs(ANALYSIS_CRS, "EPSG:4326", always_xy=True)
ORIGIN = (700000.0, 6600000.0)


def _wgs84_point(x: float, y: float) -> Point:
    lon, lat = _TO_WGS84.transform(x, y)
    return Point(float(lon), float(lat))


def _straight_survey(length: float, *, azimuth_deg: float = 0.0, steps: int = 21) -> LineString:
    rad = math.radians(azimuth_deg)
    ux, uy = math.sin(rad), math.cos(rad)
    points = [
        _wgs84_point(
            ORIGIN[0] + ux * length * t / (steps - 1),
            ORIGIN[1] + uy * length * t / (steps - 1),
        ).coords[0]
        for t in range(steps)
    ]
    return LineString(points)


def _small_conduit() -> ConduitProjectionParams:
    return ConduitProjectionParams(
        sigma_m=300.0,
        decay_lambda=0.001,
        max_projection_distance_m=3000.0,
        raster_resolution_m=20.0,
    )


# --- (a) -------------------------------------------------------------------


def test_long_survey_has_all_valid_splits(tmp_path: Path) -> None:
    survey = _straight_survey(1000.0)
    result = run_backtest(
        survey,
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="long",
        conduit_params=_small_conduit(),
        write_figure=False,
    )
    assert len(result.valid_splits) == 5
    assert result.skipped_splits == []
    assert result.is_sufficient is True
    assert result.insufficiency_reason is None


# --- (b) -------------------------------------------------------------------


def test_short_survey_filters_some_splits_with_reason(tmp_path: Path) -> None:
    survey = _straight_survey(600.0)
    params = BacktestParams(split_fractions=(0.3, 0.4, 0.5, 0.6, 0.7, 0.95))
    result = run_backtest(
        survey,
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="short",
        conduit_params=_small_conduit(),
        backtest_params=params,
        write_figure=False,
    )
    reasons = {skipped.reason for skipped in result.skipped_splits}
    assert result.skipped_splits  # some filtered
    assert result.valid_splits  # but not all
    assert "known_too_short" in reasons
    assert "hidden_too_short" in reasons


# --- (c) -------------------------------------------------------------------


def test_very_short_survey_is_insufficient(tmp_path: Path) -> None:
    survey = _straight_survey(350.0)
    result = run_backtest(
        survey,
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="tiny",
        conduit_params=_small_conduit(),
        write_figure=False,
    )
    assert result.is_sufficient is False
    assert result.insufficiency_reason
    assert result.valid_splits == []


# --- (d) -------------------------------------------------------------------


def test_reversed_orientation_is_detected_with_targets(tmp_path: Path) -> None:
    # Survey runs SOUTH (vertex-0 north/upstream, vertex-last south near target).
    survey = _straight_survey(1000.0, azimuth_deg=180.0)
    resurgence = _wgs84_point(ORIGIN[0], ORIGIN[1] - 1100.0)  # near vertex-last
    result = run_backtest(
        survey,
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="rev",
        target_points=[resurgence],
        conduit_params=_small_conduit(),
        write_figure=False,
    )
    assert result.orientation_warning is not None
    assert "reversed" in result.orientation_warning


# --- (e) -------------------------------------------------------------------


def test_positive_control_high_coverage(tmp_path: Path) -> None:
    survey = _straight_survey(1000.0)
    result = run_backtest(
        survey,
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="pos",
        conduit_params=_small_conduit(),
        write_figure=False,
    )
    mid = next(split for split in result.valid_splits if split.split_fraction == pytest.approx(0.5))
    assert mid.fraction_within_isoline_050 >= 0.8
    assert mid.heading_within_tolerance is True


# --- (f) -------------------------------------------------------------------


def test_metrics_independent_of_raster_resolution(tmp_path: Path) -> None:
    survey = _straight_survey(1000.0)

    def fractions(res: float) -> list[float]:
        result = run_backtest(
            survey,
            [],
            [],
            crs=ANALYSIS_CRS,
            output_dir=tmp_path / f"res{int(res)}",
            slug="res",
            conduit_params=ConduitProjectionParams(
                sigma_m=300.0,
                decay_lambda=0.001,
                max_projection_distance_m=3000.0,
                raster_resolution_m=res,
            ),
            write_figure=False,
        )
        return [split.fraction_within_isoline_050 for split in result.valid_splits]

    assert fractions(10.0) == pytest.approx(fractions(5.0))


# --- (g) -------------------------------------------------------------------


def test_report_json_has_per_split_lengths(tmp_path: Path) -> None:
    survey = _straight_survey(1000.0)
    result = run_backtest(
        survey,
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="rep",
        conduit_params=_small_conduit(),
        write_figure=False,
    )
    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0.0"
    for split in payload["valid_splits"]:
        assert "chainage_m" in split
        assert "known_length_m" in split
        assert "hidden_length_m" in split


# --- (h) -------------------------------------------------------------------


def test_skipped_splits_never_omitted_from_report(tmp_path: Path) -> None:
    survey = _straight_survey(600.0)
    params = BacktestParams(split_fractions=(0.3, 0.4, 0.5, 0.6, 0.7, 0.95))
    result = run_backtest(
        survey,
        [],
        [],
        crs=ANALYSIS_CRS,
        output_dir=tmp_path,
        slug="skip",
        conduit_params=_small_conduit(),
        backtest_params=params,
        write_figure=False,
    )
    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert len(payload["skipped_splits"]) == len(result.skipped_splits)
    assert len(payload["skipped_splits"]) > 0
