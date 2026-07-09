"""Guided workflow panel with step navigation."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


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

        # The collapsible part: previous/next navigation plus the step text. It
        # is kept as small as possible (4px vertical padding) and can be hidden
        # entirely, leaving only the thin handle strip below.
        self._content_widget = QWidget()
        content_layout = QHBoxLayout(self._content_widget)
        content_layout.setContentsMargins(10, 4, 10, 4)
        content_layout.setSpacing(6)

        self._prev_btn = QPushButton("◀")
        self._prev_btn.setFixedWidth(26)
        self._prev_btn.clicked.connect(self._on_prev)

        self._step_label = QLabel(self._format_step_text(0))
        self._step_label.setObjectName("secondaryText")
        self._step_label.setWordWrap(True)

        self._next_btn = QPushButton("▶")
        self._next_btn.setFixedWidth(26)
        self._next_btn.clicked.connect(self._on_next)

        content_layout.addWidget(self._prev_btn)
        content_layout.addWidget(self._step_label, 1)
        content_layout.addWidget(self._next_btn)

        # The handle strip stays visible even when the content is collapsed, so
        # the guide can always be expanded again. It carries the collapse toggle
        # (and a compact step counter while collapsed).
        handle = QWidget()
        handle_layout = QHBoxLayout(handle)
        handle_layout.setContentsMargins(10, 2, 6, 2)
        handle_layout.setSpacing(6)

        self._handle_label = QLabel("")
        self._handle_label.setObjectName("secondaryText")
        self._handle_label.setVisible(False)

        self._toggle_btn = QPushButton("▼")
        self._toggle_btn.setFixedWidth(26)
        self._toggle_btn.setToolTip(self.tr("Hide workflow guide"))
        self._toggle_btn.clicked.connect(self._on_toggle)

        handle_layout.addWidget(self._handle_label, 1)
        handle_layout.addWidget(self._toggle_btn)

        main_layout.addWidget(self._content_widget)
        main_layout.addWidget(handle)
        self._update_button_states()

    def _guided_steps(self) -> list[str]:
        """Return the list of guided workflow steps with translations."""
        return [
            self.tr("Download DEM tiles from the land profile DEM sources."),
            self.tr("Select DEM file(s) in the Tools tab."),
            self.tr("Choose land profile and project folder."),
            self.tr("Click Analyze and wait for the pipeline to complete."),
            self.tr("Review Top 25 depressions in the Results tab."),
            self.tr("Export markers, KML, or GPX from the Export tab."),
        ]

    def set_step(self, step: int) -> None:
        """Set the current step (0-indexed, clamped to valid range)."""
        steps = self._guided_steps()
        step = max(0, min(step, len(steps) - 1))
        if step != self._current_step:
            self._current_step = step
            self._step_label.setText(self._format_step_text(step))
            if self._handle_label.isVisible():
                self._handle_label.setText(self._collapsed_step_text())
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
        steps = self._guided_steps()
        if 0 <= step < len(steps):
            self._completed_steps.add(step)
            if step == self._current_step:
                self._step_label.setText(self._format_step_text(step))

    def _format_step_text(self, step: int) -> str:
        """Format step text with optional checkmark."""
        steps = self._guided_steps()
        total = len(steps)
        if step in self._completed_steps:
            return self.tr("✓ Step {0}/{1}: {2}").format(step + 1, total, steps[step])
        return self.tr("Step {0}/{1}: {2}").format(step + 1, total, steps[step])

    def _on_prev(self) -> None:
        """Move to previous step."""
        if self._current_step > 0:
            self.set_step(self._current_step - 1)

    def _on_next(self) -> None:
        """Move to next step."""
        steps = self._guided_steps()
        if self._current_step < len(steps) - 1:
            self.set_step(self._current_step + 1)

    def _on_toggle(self) -> None:
        """Collapse the guide to a thin handle, or expand it again."""
        if self._content_widget.isVisible():
            self._content_widget.hide()
            self._handle_label.setText(self._collapsed_step_text())
            self._handle_label.setVisible(True)
            self._toggle_btn.setText("▲")
            self._toggle_btn.setToolTip(self.tr("Show workflow guide"))
        else:
            self._content_widget.show()
            self._handle_label.setVisible(False)
            self._toggle_btn.setText("▼")
            self._toggle_btn.setToolTip(self.tr("Hide workflow guide"))

    def _collapsed_step_text(self) -> str:
        """Minimal one-line counter shown on the handle while collapsed."""
        total = len(self._guided_steps())
        return self.tr("Step {0}/{1}").format(self._current_step + 1, total)

    def _update_button_states(self) -> None:
        """Enable/disable prev/next buttons based on current step."""
        steps = self._guided_steps()
        self._prev_btn.setEnabled(self._current_step > 0)
        self._next_btn.setEnabled(self._current_step < len(steps) - 1)


__all__ = ["GuidedWorkflowPanel"]
