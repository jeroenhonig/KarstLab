"""Pure helpers that turn pipeline progress messages into a phase + percent.

The analysis pipeline reports progress as free-text messages (and raw
WhiteboxTools stdout lines). This module maps those onto a monotonic overall
percentage and a coarse "phase X of N" stepper so the GUI can show a structured
overview instead of a single opaque bar. Kept free of any Qt import so it can be
unit-tested without a display.
"""

from __future__ import annotations

from typing import NamedTuple

# Ordered top-level phases with the overall percentage reached when each begins.
# WhiteboxTools sub-steps (breach/pointer/accumulation/streams/fill) all fall
# inside the "Running hydrology" phase and only nudge the percentage.
_PHASES: tuple[tuple[str, int], ...] = (
    ("Assembling DEM tiles", 8),
    ("Reading DEM", 14),
    ("Computing terrain derivatives", 18),
    ("Running hydrology analysis", 22),
    ("Filling depressions", 68),
    ("Detecting dolines", 74),
    ("Extracting contours", 82),
    ("Writing exports", 88),
    ("Rendering interactive map", 93),
    ("Writing report", 97),
)

PHASE_COUNT = len(_PHASES)

# Sub-string markers → overall percentage. Order matters only for readability;
# lookup returns the first marker contained in the (lower-cased) message.
_MARKERS: tuple[tuple[str, int], ...] = (
    ("assembling", 8),
    ("building analysis geotiff", 12),
    ("reading dem", 14),
    ("computing terrain", 18),
    ("running hydrology", 22),
    ("breachdepressions", 28),
    ("d8pointer", 34),
    ("d8flowaccumulation", 42),
    ("extractstreams", 50),
    ("filldepressions", 60),
    ("saving data", 64),
    ("output file written", 66),
    ("filling depressions", 68),
    ("detecting dolines", 74),
    ("extracting contours", 82),
    ("writing exports", 88),
    ("rendering interactive map", 93),
    ("writing report", 97),
)


class PhaseStatus(NamedTuple):
    """Coarse phase position derived from the overall percentage."""

    number: int  # 1-based phase number, clamped to [1, PHASE_COUNT]
    total: int
    label: str


def progress_percent(message: str) -> int:
    """Map a progress message to an overall percentage in ``[0, 100]``.

    Recognises pipeline phase markers and raw WhiteboxTools sub-steps. Falls
    back to any explicit ``N%`` embedded in the message, then to a small floor
    so the bar always moves off zero once work starts.
    """
    lowered = message.lower()
    if "analysis complete" in lowered:
        return 100
    for marker, value in _MARKERS:
        if marker in lowered:
            return value
    if "%" in message:
        return min(90, max(10, _extract_percent(message)))
    return 10


def current_phase(percent: int) -> PhaseStatus:
    """Return the highest phase whose start percentage has been reached."""
    index = 1
    for position, (_label, threshold) in enumerate(_PHASES, start=1):
        if percent >= threshold:
            index = position
    label = _PHASES[index - 1][0]
    if percent >= 100:
        return PhaseStatus(PHASE_COUNT, PHASE_COUNT, "Analysis complete")
    return PhaseStatus(index, PHASE_COUNT, label)


def _extract_percent(message: str) -> int:
    tokens = message.rsplit("%", maxsplit=1)[0].split()
    if not tokens:
        return 10
    try:
        return int(float(tokens[-1]))
    except ValueError:
        return 10


__all__ = ["PHASE_COUNT", "PhaseStatus", "current_phase", "progress_percent"]
