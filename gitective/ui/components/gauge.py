"""Score marks that do not rely on color: 3-bar gauges, hatches and dots (5.2.1).

Drawn when the theme asks for them (`Theme.shapes`, true for every built-in
theme), so a score level reads from its shape as well as its color.
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
    """Rectangle with vertical stripes on whole pixels: no staircase nor moiré at any size or scaling (TF-02)."""
    x0, y0, x1, y1 = round(x0), round(y0), round(x1), round(y1)
    canvas.create_rectangle(x0, y0, x1, y1, fill=back, outline="")
    for x in range(x0 + 1, x1, step):
        canvas.create_rectangle(x, y0, min(x + 2, x1), y1, fill=color, outline="")


def draw_dotted(canvas: tk.Canvas, x0: float, y0: float, x1: float, y1: float, color: str, dot: str,
                step: int = 5) -> None:
    """Filled rectangle sprinkled with 1-pixel dots on whole pixels, evenly spaced at any size (TF-02)."""
    x0, y0, x1, y1 = round(x0), round(y0), round(x1), round(y1)
    canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")
    for y in range(y0 + step // 2, y1, step):
        for x in range(x0 + step // 2, x1, step):
            canvas.create_rectangle(x, y, x + 1, y + 1, fill=dot, outline="")


# Dash patterns Tk draws on Windows too: one per chart series after the first (solid).
DASHES = ("-", ".", "-.", "-..")
