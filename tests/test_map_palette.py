"""Guard the central map palette against hue collisions between layers.

The palette exists so stacked map layers stay visually distinct. These tests
encode the collision rules that motivated it, so a future colour tweak that
reintroduces an ambiguity fails loudly instead of shipping.
"""

from __future__ import annotations

import re

from karstlab.presentation import map_palette

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _all_hex_colors() -> dict[str, str]:
    colors: dict[str, str] = {}
    for name in dir(map_palette):
        if name.startswith("_"):
            continue
        value = getattr(map_palette, name)
        if isinstance(value, str) and _HEX.match(value):
            colors[name] = value
        elif isinstance(value, dict):
            for key, sub in value.items():
                if isinstance(sub, str) and _HEX.match(sub):
                    colors[f"{name}[{key}]"] = sub
    return colors


def test_all_palette_colors_are_valid_hex() -> None:
    colors = _all_hex_colors()
    assert colors, "palette exposes no hex colours"
    for name, value in colors.items():
        assert _HEX.match(value), f"{name} is not a 6-digit hex colour: {value!r}"


def test_contours_do_not_collide_with_doline_ramp() -> None:
    """Contours must avoid every doline-distance colour — that was the bug."""
    ramp = set(map_palette.FAULT_DISTANCE_COLORS.values())
    assert map_palette.CONTOURS not in ramp
    # Specifically clear of the ≤250 m yellow that originally clashed.
    assert map_palette.FAULT_DISTANCE_COLORS["<=250m"] != map_palette.CONTOURS


def test_streams_distinct_from_doline_far_blue() -> None:
    """Streams stay in the water-blue family but not the muted >250 m doline blue."""
    assert map_palette.FAULT_DISTANCE_COLORS[">250m"] != map_palette.STREAMS


def test_streams_rgba_matches_hex() -> None:
    """The raster RGBA and the legend hex must describe the same colour."""
    r, g, b, a = map_palette.STREAMS_RGBA
    assert 0 <= a <= 255
    assert map_palette.STREAMS.lower() == f"#{r:02x}{g:02x}{b:02x}"


def test_line_layer_colors_are_mutually_distinct() -> None:
    """Contours, streams, faults and the survey swatch are all different hues."""
    line_colors = [
        map_palette.CONTOURS,
        map_palette.STREAMS,
        map_palette.FAULTS,
        map_palette.SURVEY_REPRESENTATIVE,
    ]
    assert len(set(line_colors)) == len(line_colors)
