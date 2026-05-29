"""KarstLab GUI entrypoint."""
from __future__ import annotations

import sys
from pathlib import Path

from karstlab.presentation.main_window import MainWindow


def _qm_path(lang: str) -> Path:
    """Return path to compiled translation file for the given language code."""
    resources_dir = Path(__file__).parent.parent / "resources" / "i18n"
    return resources_dir / f"karstlab_{lang}.qm"


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTranslator
    except ImportError as exc:
        raise SystemExit(
            "PySide6 is not installed. Install the package with the 'package' or full app "
            "dependencies before running karstlab-gui."
        ) from exc

    app = QApplication(sys.argv)

    lang: str = "en"
    try:
        from karstlab.data.user_settings import load_user_settings

        settings = load_user_settings()
        lang = settings.language.value
    except Exception:  # noqa: BLE001
        pass

    if lang != "en":
        translator = QTranslator(app)
        qm_path = _qm_path(lang)
        if qm_path.exists():
            translator.load(str(qm_path))
            app.installTranslator(translator)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["MainWindow", "main"]
