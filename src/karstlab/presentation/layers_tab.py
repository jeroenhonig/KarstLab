"""Layers tab for controlling layer visibility and opacity."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class LayersTab(QWidget):
    """Tab for managing layer visibility and opacity with optional tile grid toggle."""

    layer_visibility_changed = Signal(str, bool)
    layer_opacity_changed = Signal(str, int)
    tile_grid_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checkboxes: dict[str, QCheckBox] = {}
        self._sliders: dict[str, QSlider] = {}
        self._layer_state: dict[str, dict[str, int | bool]] = {}

        # Dragging an opacity slider fires valueChanged for every intermediate
        # value (~100 per drag), and each emit drives a Leaflet DOM update on the
        # map. Coalesce them: update local state immediately, but emit only the
        # final value once the slider has been still for a moment.
        self._pending_opacity: dict[str, int] = {}
        self._opacity_debounce = QTimer(self)
        self._opacity_debounce.setSingleShot(True)
        self._opacity_debounce.setInterval(120)
        self._opacity_debounce.timeout.connect(self._flush_pending_opacity)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layers = [
            (self.tr("Doline footprints"), True, 80),
            (self.tr("Top 25 markers"), True, 80),
            (self.tr("Contours"), True, 80),
            (self.tr("Streams"), False, 40),
            (self.tr("Hillshade"), False, 40),
        ]

        for layer_name, checked, opacity in layers:
            self._add_layer_row(layout, layer_name, checked, opacity)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        self._tile_grid_checkbox = QCheckBox(self.tr("Show tile boundary grid"))
        self._tile_grid_checkbox.setChecked(False)
        self._tile_grid_checkbox.toggled.connect(self._on_tile_grid_toggled)
        layout.addWidget(self._tile_grid_checkbox)

        layout.addStretch(1)

    def _add_layer_row(
        self, layout: QVBoxLayout, layer_name: str, checked: bool, opacity: int
    ) -> None:
        """Add a layer visibility and opacity control row."""
        row = QHBoxLayout()

        checkbox = QCheckBox(layer_name)
        checkbox.setChecked(checked)
        checkbox.toggled.connect(
            lambda visible, name=layer_name: self._on_visibility_changed(name, visible)
        )
        self._checkboxes[layer_name] = checkbox

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(opacity)
        slider.valueChanged.connect(
            lambda value, name=layer_name: self._on_opacity_changed(name, value)
        )
        self._sliders[layer_name] = slider

        self._layer_state[layer_name] = {"visible": checked, "opacity": opacity}

        row.addWidget(checkbox)
        row.addWidget(slider)
        layout.addLayout(row)

    def _on_visibility_changed(self, layer_name: str, visible: bool) -> None:
        """Handle layer visibility toggle."""
        self._layer_state[layer_name]["visible"] = visible
        self.layer_visibility_changed.emit(layer_name, visible)

    def _on_opacity_changed(self, layer_name: str, opacity: int) -> None:
        """Handle layer opacity change (debounced emit, immediate state update)."""
        self._layer_state[layer_name]["opacity"] = opacity
        self._pending_opacity[layer_name] = opacity
        self._opacity_debounce.start()

    def _flush_pending_opacity(self) -> None:
        """Emit the final opacity for every layer touched during the last drag."""
        pending = self._pending_opacity
        self._pending_opacity = {}
        for layer_name, opacity in pending.items():
            self.layer_opacity_changed.emit(layer_name, opacity)

    def _on_tile_grid_toggled(self, checked: bool) -> None:
        """Handle tile grid toggle."""
        self.tile_grid_toggled.emit(checked)

    @property
    def checkboxes(self) -> dict[str, QCheckBox]:
        """Return dict mapping layer names to their visibility checkboxes."""
        return self._checkboxes

    @property
    def sliders(self) -> dict[str, QSlider]:
        """Return dict mapping layer names to their opacity sliders."""
        return self._sliders

    @property
    def layer_state(self) -> dict[str, dict[str, int | bool]]:
        """Return the current layer state (visibility and opacity)."""
        return self._layer_state


__all__ = ["LayersTab"]
