"""KarstLab GUI entrypoint."""

from __future__ import annotations

import sys

from karstlab.presentation.main_window import MainWindow


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise SystemExit(
            "PySide6 is not installed. Install the package with the 'package' or full app "
            "dependencies before running karstlab-gui."
        ) from exc

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["MainWindow", "main"]
