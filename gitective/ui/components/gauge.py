"""Score marks that do not rely on color: 3-bar gauges, hatches and dots (TH-05, 5.2).

Drawn only when the theme asks for them (`Theme.shapes`); the color-blind
theme does, so a score level reads from its shape as well as its color.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk

BARS = {"green": 3, "orange": 2, "red": 1}  # filled bars per score level
TEXT = {"green": "▮▮▮", "orange": "▮▮▯", "red": "▮▯▯"}  # the gauge in a plain Tk label

GAUGE_GAP = 2


def gauge_width(height: float) -> float:
    """Width of a gauge `height` px tall: three bars and two gaps."""
    return 3 * bar_width(height) + 2 * GAUGE_GAP


def bar_width(height: float) -> float:
    return max(2.0, round(height / 4))


def draw_gauge(canvas: tk.Canvas, x: float, y: float, level: str, color: str, empty: str,
               height: float = 11) -> float:
    """Three rising bars from x, vertically centred on y, `BARS[level]` of them filled; returns the width."""
    w = bar_width(height)
    filled = BARS.get(level, 1)
    bottom = y + height / 2
    for index in range(3):
        top = bottom - height * (index + 2) / 4
        left = x + index * (w + GAUGE_GAP)
        canvas.create_rectangle(left, top, left + w, bottom, outline="",
                                fill=color if index < filled else empty)
    return gauge_width(height)


def label_text(text: str, level: str, shapes: bool) -> str:
    """A score for a Tk label: "▮▮▯ 75 %" with the gauge, the bare score otherwise."""
    return f"{TEXT.get(level, TEXT['red'])} {text}" if shapes else text


def draw_hatched(canvas: tk.Canvas, x0: float, y0: float, x1: float, y1: float, color: str, back: str,
                 step: int = 5) -> None:
    """Rectangle with diagonal stripes, drawn as lines (Tk stipples are unreliable on Windows)."""
    canvas.create_rectangle(x0, y0, x1, y1, fill=back, outline="")
    width, height = x1 - x0, y1 - y0
    offset = -height
    while offset < width:
        # Line from (offset, bottom) to (offset + height, top), clipped to the box.
        sx, sy, ex, ey = offset, height, offset + height, 0.0
        if sx < 0:
            sy, sx = height + sx, 0.0
        if ex > width:
            ey, ex = ex - width, width
        if ex > sx:
            canvas.create_line(x0 + sx, y0 + sy, x0 + ex, y0 + ey, fill=color, width=2)
        offset += step


def draw_dotted(canvas: tk.Canvas, x0: float, y0: float, x1: float, y1: float, color: str, dot: str,
                step: int = 5) -> None:
    """Filled rectangle sprinkled with small dots."""
    canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")
    y = y0 + step / 2
    while y < y1:
        x = x0 + step / 2
        while x < x1:
            canvas.create_rectangle(x, y, x + 1, y + 1, fill=dot, outline="")
            x += step
        y += step


# Dash patterns Tk draws on Windows too: one per chart series after the first (solid).
DASHES = ("-", ".", "-.", "-..")
