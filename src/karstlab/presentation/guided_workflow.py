"""Guided workflow panel with step navigation."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_GUIDED_STEPS = [
    "Download DEM tiles from the land profile DEM sources.",
    "Select DEM file(s) in the Tools tab.",
    "Choose land profile and project folder.",
    "Click Analyze and wait for the pipeline to complete.",
    "Review Top 25 depressions in the Results tab.",
    "Export markers, KML, or GPX from the Export tab.",
]


class GuidedWorkflowPanel(QFrame):
    """Collapsible step-by-step workflow guidance panel."""

    step_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("guidedBar")

        self._current_step = 0
        self._completed_steps: set[int] = set()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._content_widget = QWidget()
        content_layout = QHBoxLayout(self._content_widget)
        content_layout.setContentsMargins(12, 8, 12, 8)
        content_layout.setSpacing(8)

        self._prev_btn = QPushButton("◀")
        self._prev_btn.setFixedWidth(32)
        self._prev_btn.clicked.connect(self._on_prev)

        self._step_label = QLabel(self._format_step_text(0))
        self._step_label.setObjectName("secondaryText")
        self._step_label.setWordWrap(True)

        self._next_btn = QPushButton("▶")
        self._next_btn.setFixedWidth(32)
        self._next_btn.clicked.connect(self._on_next)

        self._toggle_btn = QPushButton("▲")
        self._toggle_btn.setFixedWidth(32)
        self._toggle_btn.clicked.connect(self._on_toggle)

        content_layout.addWidget(self._prev_btn)
        content_layout.addWidget(self._step_label, 1)
        content_layout.addWidget(self._next_btn)
        content_layout.addWidget(self._toggle_btn)

        main_layout.addWidget(self._content_widget)
        self._update_button_states()

    def set_step(self, step: int) -> None:
        """Set the current step (0-indexed, clamped to valid range)."""
        step = max(0, min(step, len(_GUIDED_STEPS) - 1))
        if step != self._current_step:
            self._current_step = step
            self._step_label.setText(self._format_step_text(step))
            self._update_button_states()
            self.step_changed.emit(step)

    def current_step(self) -> int:
        """Return the current step (0-indexed)."""
        return self._current_step

    def advance_to(self, step: int) -> None:
        """Alias for set_step."""
        self.set_step(step)

    def mark_step_complete(self, step: int) -> None:
        """Mark a step as complete with a checkmark."""
        if 0 <= step < len(_GUIDED_STEPS):
            self._completed_steps.add(step)
            if step == self._current_step:
                self._step_label.setText(self._format_step_text(step))

    def _format_step_text(self, step: int) -> str:
        """Format step text with optional checkmark."""
        prefix = "✓ " if step in self._completed_steps else ""
        total = len(_GUIDED_STEPS)
        return f"{prefix}Step {step + 1}/{total}: {_GUIDED_STEPS[step]}"

    def _on_prev(self) -> None:
        """Move to previous step."""
        if self._current_step > 0:
            self.set_step(self._current_step - 1)

    def _on_next(self) -> None:
        """Move to next step."""
        if self._current_step < len(_GUIDED_STEPS) - 1:
            self.set_step(self._current_step + 1)

    def _on_toggle(self) -> None:
        """Toggle collapse/expand state."""
        if self._content_widget.isVisible():
            self._content_widget.hide()
            self._toggle_btn.setText("▼")
        else:
            self._content_widget.show()
            self._toggle_btn.setText("▲")

    def _update_button_states(self) -> None:
        """Enable/disable prev/next buttons based on current step."""
        self._prev_btn.setEnabled(self._current_step > 0)
        self._next_btn.setEnabled(self._current_step < len(_GUIDED_STEPS) - 1)


__all__ = ["GuidedWorkflowPanel"]
