"""Altimetric profile dialog rendering an elevation transect with matplotlib."""

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget


class ProfileDialog(QDialog):
    """Show a DEM elevation profile between two WGS84 points."""

    def __init__(
        self,
        distances: np.ndarray,
        elevations: np.ndarray,
        start: tuple[float, float],
        end: tuple[float, float],
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Elevation profile"))
        self.resize(640, 400)

        figure = Figure(figsize=(6, 4))
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        axis = figure.add_subplot(111)

        use_km = float(distances[-1]) >= 1000.0 if len(distances) else False
        x = distances / 1000.0 if use_km else distances
        x_unit = "km" if use_km else "m"

        finite = np.isfinite(elevations)
        axis.plot(x[finite], elevations[finite], color="#0f766e", linewidth=1.5)
        if finite.any():
            axis.fill_between(
                x[finite],
                elevations[finite],
                float(np.nanmin(elevations)),
                alpha=0.25,
                color="#14b8a6",
            )
        axis.set_xlabel(self.tr("Distance ({0})").format(x_unit))
        axis.set_ylabel(self.tr("Elevation (m)"))
        total = float(distances[-1]) if len(distances) else 0.0
        axis.set_title(
            self.tr("{0:.4f},{1:.4f} → {2:.4f},{3:.4f}  ({4:.0f} m)").format(
                start[0], start[1], end[0], end[1], total
            )
        )
        figure.tight_layout()

        layout = QVBoxLayout(self)
        layout.addWidget(canvas)


__all__ = ["ProfileDialog"]
