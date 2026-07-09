"""Structured analysis progress panel: phase stepper + live timer + detail log.

Replaces the single opaque progress bar. Shows which phase of the pipeline is
running ("Phase 4 / 10"), a clock that keeps ticking during long phases so the
run never looks frozen, and a collapsible log of every raw step (including
WhiteboxTools lines) with the elapsed time at which it arrived.
"""

from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from karstlab.presentation.progress_model import current_phase, progress_percent


def _format_clock(milliseconds: int) -> str:
    total_seconds = max(0, milliseconds) // 1000
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"


class AnalysisProgressPanel(QWidget):
    """Phase header, progress bar, live elapsed clock, and collapsible log."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._elapsed = QElapsedTimer()
        self._running = False
        self._last_message = ""

        self._tick = QTimer(self)
        self._tick.setInterval(500)
        self._tick.timeout.connect(self._refresh_clock)

        self._phase_label = QLabel(self.tr("Ready"))
        self._phase_label.setObjectName("phaseHeader")

        self._step_label = QLabel("")
        self._step_label.setObjectName("secondaryText")
        self._step_label.setWordWrap(True)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(True)
        self.bar.setFormat("%p%")

        self._details_toggle = QToolButton()
        self._details_toggle.setText(self.tr("▸ Details"))
        self._details_toggle.setObjectName("secondaryText")
        self._details_toggle.setCheckable(True)
        self._details_toggle.setAutoRaise(True)
        self._details_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._details_toggle.toggled.connect(self._on_toggle_details)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        self._log.setMaximumHeight(140)
        self._log.setVisible(False)

        # ``_status_label`` is the line the rest of the app reads/writes via
        # ToolsTab.set_status; kept as the step label so existing callers and
        # tests keep working while the panel adds the richer view around it.
        self.message_label = self._step_label

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._phase_label)
        layout.addWidget(self._step_label)
        layout.addWidget(self.bar)
        layout.addWidget(self._details_toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._log)

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    def begin(self) -> None:
        """Reset the panel and start the live clock for a new run."""
        self._running = True
        self._last_message = ""
        self._elapsed.restart()
        self.bar.setValue(0)
        self._log.clear()
        self._step_label.setText("")
        self._phase_label.setText(self.tr("Phase 1 / {0}  ·  0:00").format(self._total()))
        self._tick.start()

    def report(self, message: str) -> None:
        """Record a progress message: advance the bar, header, and detail log."""
        if not message:
            return
        percent = max(self.bar.value(), progress_percent(message))
        self.bar.setValue(percent)
        phase = current_phase(percent)
        self._phase_label.setText(
            self.tr("Phase {0} / {1}  ·  {2}").format(
                phase.number, phase.total, _format_clock(self._elapsed_ms())
            )
        )
        self._step_label.setText(message)
        if message != self._last_message:
            self._last_message = message
            self._log.appendPlainText(f"{_format_clock(self._elapsed_ms())}  {message}")

    def end(self, summary: str, *, percent: int | None = None) -> None:
        """Stop the clock and show a terminal summary (complete/failed/cancelled)."""
        self._running = False
        self._tick.stop()
        if percent is not None:
            self.bar.setValue(percent)
        self._phase_label.setText(f"{summary}  ·  {_format_clock(self._elapsed_ms())}")
        self._step_label.setText(summary)

    # ─── Backwards-compatible direct setters (used by tests / simple callers) ──

    def set_percent(self, value: int) -> None:
        self.bar.setValue(value)

    def set_message(self, text: str) -> None:
        self._step_label.setText(text)

    # ─── Internals ─────────────────────────────────────────────────────────────

    def _total(self) -> int:
        return current_phase(0).total

    def _elapsed_ms(self) -> int:
        return int(self._elapsed.elapsed()) if self._elapsed.isValid() else 0

    def _refresh_clock(self) -> None:
        if not self._running:
            return
        text = self._phase_label.text()
        head = text.rsplit("·", maxsplit=1)[0].rstrip()
        self._phase_label.setText(f"{head}  ·  {_format_clock(self._elapsed_ms())}")

    def _on_toggle_details(self, shown: bool) -> None:
        self._log.setVisible(shown)
        self._details_toggle.setText(self.tr("▾ Details") if shown else self.tr("▸ Details"))


__all__ = ["AnalysisProgressPanel"]
