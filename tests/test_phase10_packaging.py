"""Phase 10 tests: packaging infrastructure and distribution assets."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
PACKAGING = PROJECT_ROOT / "packaging"


# ─── Spec files ───────────────────────────────────────────────────────────────


def test_macos_spec_file_exists() -> None:
    assert (PACKAGING / "karstlab_gui.spec").exists()


def test_windows_spec_file_exists() -> None:
    assert (PACKAGING / "karstlab_gui_win.spec").exists()


def test_macos_spec_bundles_regions() -> None:
    content = (PACKAGING / "karstlab_gui.spec").read_text(encoding="utf-8")
    assert "regions" in content


def test_macos_spec_bundles_schemas() -> None:
    content = (PACKAGING / "karstlab_gui.spec").read_text(encoding="utf-8")
    assert "schemas" in content


def test_macos_spec_bundles_i18n_translations() -> None:
    content = (PACKAGING / "karstlab_gui.spec").read_text(encoding="utf-8")
    assert "i18n" in content


def test_macos_spec_has_proj_data_bundling() -> None:
    content = (PACKAGING / "karstlab_gui.spec").read_text(encoding="utf-8")
    assert "proj" in content.lower()


def test_macos_spec_references_runtime_hook() -> None:
    content = (PACKAGING / "karstlab_gui.spec").read_text(encoding="utf-8")
    assert "runtime_hook" in content or "set_proj_data" in content


def test_macos_spec_uses_console_false() -> None:
    content = (PACKAGING / "karstlab_gui.spec").read_text(encoding="utf-8")
    assert "console=False" in content


def test_macos_spec_has_pyside6_hidden_imports() -> None:
    content = (PACKAGING / "karstlab_gui.spec").read_text(encoding="utf-8")
    assert "PySide6" in content


def test_macos_spec_creates_bundle() -> None:
    content = (PACKAGING / "karstlab_gui.spec").read_text(encoding="utf-8")
    assert "BUNDLE" in content


def test_windows_spec_creates_exe() -> None:
    content = (PACKAGING / "karstlab_gui_win.spec").read_text(encoding="utf-8")
    assert "EXE" in content


def test_windows_spec_uses_console_false() -> None:
    content = (PACKAGING / "karstlab_gui_win.spec").read_text(encoding="utf-8")
    assert "console=False" in content


# ─── PyInstaller hooks ────────────────────────────────────────────────────────


def test_karstlab_hook_exists() -> None:
    assert (PACKAGING / "hooks" / "hook-karstlab.py").exists()


def test_rasterio_hook_exists() -> None:
    assert (PACKAGING / "hooks" / "hook-rasterio.py").exists()


def test_karstlab_hook_collects_data_files() -> None:
    content = (PACKAGING / "hooks" / "hook-karstlab.py").read_text(encoding="utf-8")
    assert "collect_data_files" in content
    assert "datas" in content


def test_karstlab_hook_collects_submodules() -> None:
    content = (PACKAGING / "hooks" / "hook-karstlab.py").read_text(encoding="utf-8")
    assert "collect_submodules" in content
    assert "hiddenimports" in content


# ─── Runtime hook ─────────────────────────────────────────────────────────────


def test_runtime_hook_exists() -> None:
    assert (PACKAGING / "runtime_hooks" / "set_proj_data.py").exists()


def test_runtime_hook_sets_proj_data() -> None:
    content = (PACKAGING / "runtime_hooks" / "set_proj_data.py").read_text(encoding="utf-8")
    assert "PROJ_DATA" in content
    assert "frozen" in content


def test_runtime_hook_sets_gdal_data() -> None:
    content = (PACKAGING / "runtime_hooks" / "set_proj_data.py").read_text(encoding="utf-8")
    assert "GDAL_DATA" in content


def test_runtime_hook_is_valid_python() -> None:
    source = (PACKAGING / "runtime_hooks" / "set_proj_data.py").read_text(encoding="utf-8")
    ast.parse(source)  # raises SyntaxError if invalid


# ─── Icons ────────────────────────────────────────────────────────────────────


def test_svg_icon_exists() -> None:
    assert (PACKAGING / "icons" / "karstlab.svg").exists()


def test_svg_icon_is_valid_xml() -> None:
    import xml.etree.ElementTree as ET

    ET.parse(PACKAGING / "icons" / "karstlab.svg")


def test_svg_icon_has_karstlab_colors() -> None:
    content = (PACKAGING / "icons" / "karstlab.svg").read_text(encoding="utf-8")
    assert "#1a1f2e" in content or "#c75d4a" in content


def test_create_icons_script_exists() -> None:
    assert (PACKAGING / "create_icons.py").exists()


def test_create_icons_script_is_valid_python() -> None:
    source = (PACKAGING / "create_icons.py").read_text(encoding="utf-8")
    ast.parse(source)


# ─── macOS assets ─────────────────────────────────────────────────────────────


def test_macos_entitlements_exists() -> None:
    assert (PACKAGING / "macos" / "entitlements.plist").exists()


def test_macos_entitlements_is_valid_plist() -> None:
    import plistlib

    data = plistlib.loads((PACKAGING / "macos" / "entitlements.plist").read_bytes())
    assert isinstance(data, dict)


def test_macos_entitlements_has_library_validation() -> None:
    content = (PACKAGING / "macos" / "entitlements.plist").read_text(encoding="utf-8")
    assert "library-validation" in content


# ─── Windows assets ───────────────────────────────────────────────────────────


def test_windows_nsis_script_exists() -> None:
    assert (PACKAGING / "windows" / "KarstLab.nsi").exists()


def test_windows_nsis_has_file_association() -> None:
    content = (PACKAGING / "windows" / "KarstLab.nsi").read_text(encoding="utf-8")
    assert ".karstlab" in content


def test_windows_nsis_has_uninstaller() -> None:
    content = (PACKAGING / "windows" / "KarstLab.nsi").read_text(encoding="utf-8")
    assert "Uninstall" in content


def test_windows_nsis_targets_64bit() -> None:
    content = (PACKAGING / "windows" / "KarstLab.nsi").read_text(encoding="utf-8")
    assert "64" in content


# ─── Makefile targets ─────────────────────────────────────────────────────────


def test_makefile_has_translate_target() -> None:
    content = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "translate:" in content


def test_makefile_translate_calls_lrelease() -> None:
    content = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "lrelease" in content


def test_makefile_translate_calls_lupdate() -> None:
    content = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "lupdate" in content


def test_makefile_has_package_macos_target() -> None:
    content = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "package-macos:" in content


def test_makefile_has_package_windows_target() -> None:
    content = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "package-windows" in content


def test_makefile_has_icons_target() -> None:
    content = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "icons:" in content


def test_makefile_package_macos_depends_on_translate() -> None:
    content = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"package-macos.*translate", content)


def test_makefile_has_pyinstaller_invocation() -> None:
    content = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "PyInstaller" in content or "pyinstaller" in content.lower()


# ─── Resource integrity ───────────────────────────────────────────────────────


def test_all_three_qm_files_exist() -> None:
    i18n = PROJECT_ROOT / "src" / "karstlab" / "resources" / "i18n"
    for lang in ("en", "nl", "fr"):
        assert (i18n / f"karstlab_{lang}.qm").exists()


def test_land_profile_json_files_present() -> None:
    regions = PROJECT_ROOT / "src" / "karstlab" / "resources" / "regions"
    jsons = list(regions.glob("*.json"))
    assert len(jsons) >= 4, "Expected at least 4 land profile JSON files"


def test_json_schema_files_present() -> None:
    schemas = PROJECT_ROOT / "src" / "karstlab" / "resources" / "schemas"
    jsons = list(schemas.glob("*.json"))
    assert len(jsons) >= 2


def test_spec_bundles_qm_files_from_i18n() -> None:
    content = (PACKAGING / "karstlab_gui.spec").read_text(encoding="utf-8")
    assert "i18n" in content
