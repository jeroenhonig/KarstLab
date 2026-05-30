"""Phase 9 tests: internationalization infrastructure and runtime translation."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

I18N_DIR = Path(__file__).parent.parent / "src" / "karstlab" / "resources" / "i18n"


# ─── Translation file existence ───────────────────────────────────────────────


@pytest.mark.parametrize("lang", ["en", "nl", "fr"])
def test_ts_file_exists(lang: str) -> None:
    assert (I18N_DIR / f"karstlab_{lang}.ts").exists()


@pytest.mark.parametrize("lang", ["en", "nl", "fr"])
def test_qm_file_exists(lang: str) -> None:
    assert (I18N_DIR / f"karstlab_{lang}.qm").exists(), (
        f"karstlab_{lang}.qm not compiled — run 'make translate'"
    )


@pytest.mark.parametrize("lang", ["en", "nl", "fr"])
def test_qm_file_not_empty(lang: str) -> None:
    qm = I18N_DIR / f"karstlab_{lang}.qm"
    assert qm.stat().st_size > 100


# ─── .ts file structure ───────────────────────────────────────────────────────


@pytest.mark.parametrize("lang", ["en", "nl", "fr"])
def test_ts_file_is_valid_xml(lang: str) -> None:
    import xml.etree.ElementTree as ET

    ts_path = I18N_DIR / f"karstlab_{lang}.ts"
    tree = ET.parse(ts_path)
    root = tree.getroot()
    assert root.tag == "TS"


@pytest.mark.parametrize("lang", ["en", "nl", "fr"])
def test_ts_file_has_expected_contexts(lang: str) -> None:
    import xml.etree.ElementTree as ET

    tree = ET.parse(I18N_DIR / f"karstlab_{lang}.ts")
    root = tree.getroot()
    context_names = {ctx.findtext("name") for ctx in root.findall("context")}
    required = {"ToolsTab", "LayersTab", "ResultsTab", "MarkersTab", "GuidedWorkflowPanel"}
    missing = required - context_names
    assert required.issubset(context_names), f"Missing contexts in {lang}.ts: {missing}"


def test_nl_ts_contains_dutch_translations() -> None:
    import xml.etree.ElementTree as ET

    tree = ET.parse(I18N_DIR / "karstlab_nl.ts")
    root = tree.getroot()
    translations: dict[str, str] = {}
    for ctx in root.findall("context"):
        for msg in ctx.findall("message"):
            src = msg.findtext("source") or ""
            trans = msg.findtext("translation") or ""
            if src:
                translations[src] = trans

    assert translations.get("Analyze") == "Analyseren"
    assert translations.get("Contours") == "Hoogtelijnen"
    assert translations.get("Streams") == "Waterlopen"
    assert translations.get("Cancel") == "Annuleren"


def test_fr_ts_contains_french_translations() -> None:
    import xml.etree.ElementTree as ET

    tree = ET.parse(I18N_DIR / "karstlab_fr.ts")
    root = tree.getroot()
    translations: dict[str, str] = {}
    for ctx in root.findall("context"):
        for msg in ctx.findall("message"):
            src = msg.findtext("source") or ""
            trans = msg.findtext("translation") or ""
            if src:
                translations[src] = trans

    assert translations.get("Analyze") == "Analyser"
    assert translations.get("Contours") == "Courbes de niveau"
    assert translations.get("Streams") == "Cours d'eau"
    assert translations.get("Cancel") == "Annuler"


# ─── app.py translator paths ──────────────────────────────────────────────────


def test_qm_path_helper_returns_correct_path() -> None:
    from karstlab.presentation.app import _qm_path

    for lang in ("en", "nl", "fr"):
        p = _qm_path(lang)
        assert p.name == f"karstlab_{lang}.qm"
        assert p.exists()


def test_qm_path_in_resources_i18n_dir() -> None:
    from karstlab.presentation.app import _qm_path

    p = _qm_path("nl")
    assert "resources" in str(p)
    assert "i18n" in str(p)


# ─── Qt translator loading ────────────────────────────────────────────────────


QtWidgets = pytest.importorskip("PySide6.QtWidgets")
QtCore = pytest.importorskip("PySide6.QtCore")


@pytest.fixture(scope="module")
def qapp() -> Iterator[Any]:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["karstlab-i18n-tests"])
    yield app


def test_nl_translator_loads_successfully(qapp: Any) -> None:
    translator = QtCore.QTranslator()
    ok = translator.load(str(I18N_DIR / "karstlab_nl.qm"))
    assert ok, "NL .qm file failed to load into QTranslator"


def test_fr_translator_loads_successfully(qapp: Any) -> None:
    translator = QtCore.QTranslator()
    ok = translator.load(str(I18N_DIR / "karstlab_fr.qm"))
    assert ok, "FR .qm file failed to load into QTranslator"


def test_nl_translator_translates_widget_strings(qapp: Any) -> None:
    """Installing NL translator causes widget strings to appear in Dutch."""
    translator = QtCore.QTranslator()
    translator.load(str(I18N_DIR / "karstlab_nl.qm"))
    qapp.installTranslator(translator)

    try:
        from karstlab.presentation.layers_tab import LayersTab
        tab = LayersTab()
        layer_names = list(tab.checkboxes.keys())
        assert "Hoogtelijnen" in layer_names, "Expected Dutch 'Hoogtelijnen' for 'Contours'"
        assert "Waterlopen" in layer_names, "Expected Dutch 'Waterlopen' for 'Streams'"
    finally:
        qapp.removeTranslator(translator)


def test_fr_translator_translates_widget_strings(qapp: Any) -> None:
    """Installing FR translator causes widget strings to appear in French."""
    translator = QtCore.QTranslator()
    translator.load(str(I18N_DIR / "karstlab_fr.qm"))
    qapp.installTranslator(translator)

    try:
        from karstlab.presentation.layers_tab import LayersTab
        tab = LayersTab()
        layer_names = list(tab.checkboxes.keys())
        assert "Courbes de niveau" in layer_names, "Expected French 'Courbes de niveau'"
        assert "Cours d'eau" in layer_names, "Expected French 'Cours d'eau'"
    finally:
        qapp.removeTranslator(translator)


def test_no_translator_uses_english_strings(qapp: Any) -> None:
    from karstlab.presentation.layers_tab import LayersTab
    tab = LayersTab()
    layer_names = list(tab.checkboxes.keys())
    assert "Contours" in layer_names
    assert "Streams" in layer_names


# ─── Guided workflow i18n ─────────────────────────────────────────────────────


def test_guided_workflow_has_guided_steps_method(qapp: Any) -> None:
    from karstlab.presentation.guided_workflow import GuidedWorkflowPanel
    panel = GuidedWorkflowPanel()
    steps = panel._guided_steps()
    assert len(steps) == 6
    assert all(isinstance(s, str) for s in steps)


def test_guided_workflow_steps_nonempty(qapp: Any) -> None:
    from karstlab.presentation.guided_workflow import GuidedWorkflowPanel
    panel = GuidedWorkflowPanel()
    for step in panel._guided_steps():
        assert len(step) > 10, f"Step text too short: {step!r}"


# ─── Report i18n ──────────────────────────────────────────────────────────────


def _make_pipeline_result() -> Any:
    from karstlab.data.schemas import AnalysisParams, PipelineResult, PipelineStatus
    return PipelineResult(
        project_id=uuid4(),
        status=PipelineStatus.SUCCESS,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        land_profile="generic",
        analysis_params=AnalysisParams(),
        input_dem_paths=[Path("dem.tif")],
        output_dir=Path("out"),
    )


def test_report_has_locale_parameter() -> None:
    import inspect

    from karstlab.presentation.report import generate_html_report

    sig = inspect.signature(generate_html_report)
    assert "locale" in sig.parameters


def test_report_i18n_dict_has_three_locales() -> None:
    from karstlab.presentation.report import _REPORT_I18N

    assert set(_REPORT_I18N.keys()) == {"en", "nl", "fr"}


def test_report_generates_dutch_section_headers() -> None:
    from karstlab.data.schemas import AnalysisParams
    from karstlab.presentation.report import generate_html_report

    result = _make_pipeline_result()
    html = generate_html_report(AnalysisParams(), result, locale="nl")
    assert "Overzicht" in html or "Analyseparameters" in html


def test_report_generates_french_section_headers() -> None:
    from karstlab.data.schemas import AnalysisParams
    from karstlab.presentation.report import generate_html_report

    result = _make_pipeline_result()
    html = generate_html_report(AnalysisParams(), result, locale="fr")
    assert "Résumé" in html or "Paramètres" in html


def test_report_defaults_to_english() -> None:
    from karstlab.data.schemas import AnalysisParams
    from karstlab.presentation.report import generate_html_report

    result = _make_pipeline_result()
    html = generate_html_report(AnalysisParams(), result)
    assert "Run Summary" in html or "Analysis Parameters" in html


def test_report_unknown_locale_falls_back_to_english() -> None:
    from karstlab.data.schemas import AnalysisParams
    from karstlab.presentation.report import generate_html_report

    result = _make_pipeline_result()
    html = generate_html_report(AnalysisParams(), result, locale="xx")
    assert "Run Summary" in html or "Analysis Parameters" in html or "KarstLab" in html


# ─── Settings dialog restart prompt ───────────────────────────────────────────


def test_settings_dialog_stores_original_language(qapp: Any) -> None:
    from karstlab.data.schemas import Locale, UserSettings
    from karstlab.presentation.settings_dialog import SettingsDialog

    settings = UserSettings(language=Locale.EN)
    dialog = SettingsDialog(settings)
    assert dialog._original_language == Locale.EN


def test_settings_dialog_has_original_language_attr(qapp: Any) -> None:
    from karstlab.data.schemas import UserSettings
    from karstlab.presentation.settings_dialog import SettingsDialog

    dialog = SettingsDialog(UserSettings())
    assert hasattr(dialog, "_original_language")
