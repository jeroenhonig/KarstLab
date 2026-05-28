"""Minimal GUI entrypoint used by the v0.1.0 packaging spike."""

from __future__ import annotations

import sys

from karstlab.version import __version__


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication, QLabel, QMainWindow
    except ImportError as exc:
        raise SystemExit(
            "PySide6 is not installed. Install the package with the 'package' or full app "
            "dependencies before running karstlab-gui."
        ) from exc

    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle(f"KarstLab {__version__}")
    window.setCentralWidget(QLabel("KarstLab packaging spike"))
    window.resize(960, 640)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

