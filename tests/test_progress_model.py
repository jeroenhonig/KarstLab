"""Tests for the Qt-free analysis progress model and the progress panel."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest

from karstlab.presentation.progress_model import (
    PHASE_COUNT,
    current_phase,
    progress_percent,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ─── progress_percent ──────────────────────────────────────────────────────────


def test_progress_percent_recognises_phase_markers() -> None:
    assert progress_percent("Reading DEM") == 14
    assert progress_percent("Computing terrain derivatives") == 18
    assert progress_percent("Detecting dolines") == 74
    assert progress_percent("Writing report") == 97


def test_progress_percent_recognises_whitebox_substeps() -> None:
    assert progress_percent("D8FlowAccumulation: 50%") == 42
    assert progress_percent("ExtractStreams - saving data") == 50


def test_progress_percent_complete_and_floor() -> None:
    assert progress_percent("Analysis complete") == 100
    assert progress_percent("something unmapped") == 10


def test_progress_percent_falls_back_to_explicit_percent() -> None:
    assert progress_percent("Operation: 75%") == 75
    assert progress_percent("%") == 10


# ─── current_phase ──────────────────────────────────────────────────────────────


def test_current_phase_is_monotonic_and_clamped() -> None:
    first = current_phase(0)
    assert first.number == 1
    assert first.total == PHASE_COUNT

    mid = current_phase(74)
    assert mid.label == "Detecting dolines"
    assert 1 <= mid.number <= PHASE_COUNT

    done = current_phase(100)
    assert done.number == PHASE_COUNT
    assert done.label == "Analysis complete"


def test_current_phase_index_never_decreases_with_percent() -> None:
    indices = [current_phase(p).number for p in range(0, 101)]
    assert indices == sorted(indices)


# ─── AnalysisProgressPanel ──────────────────────────────────────────────────────


@pytest.fixture
def qapp() -> Iterator[Any]:
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["karstlab-tests"])
    yield app


def test_panel_begin_resets_and_reports_advance_bar(qapp: Any) -> None:
    from karstlab.presentation.analysis_progress import AnalysisProgressPanel

    panel = AnalysisProgressPanel()
    panel.begin()
    assert panel.bar.value() == 0

    panel.report("Computing terrain derivatives")
    assert panel.bar.value() == 18

    # Bar is monotonic: a lower-percent message never rewinds it.
    panel.report("Reading DEM")
    assert panel.bar.value() == 18


def test_panel_report_logs_distinct_messages(qapp: Any) -> None:
    from karstlab.presentation.analysis_progress import AnalysisProgressPanel

    panel = AnalysisProgressPanel()
    panel.begin()
    panel.report("Reading DEM")
    panel.report("Reading DEM")  # duplicate is not logged twice
    panel.report("Detecting dolines")

    log_text = panel._log.toPlainText()
    assert log_text.count("Reading DEM") == 1
    assert "Detecting dolines" in log_text


def test_panel_end_stops_clock_and_sets_percent(qapp: Any) -> None:
    from karstlab.presentation.analysis_progress import AnalysisProgressPanel

    panel = AnalysisProgressPanel()
    panel.begin()
    panel.end("Analysis complete", percent=100)
    assert panel.bar.value() == 100
    assert not panel._tick.isActive()
