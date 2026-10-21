"""Assignee, reviewer and author badges, drawn on a Canvas (6.5, 5.2)."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable

from gitective.review.my_mrs import BadgeCounts
from gitective.ui.components.widgets import Tooltip
from gitective.ui.themes import Theme

ICON = 18
HEIGHT = 34
DOT = 18


class Badge(tk.Canvas):
    """Icon, label, count of open MRs and a dot with the number of new ones (BA-01)."""

    def __init__(self, master: tk.Misc, kind: str, label: str, get_theme: Callable[[], Theme],
                 on_click: Callable[[], None]) -> None:
        super().__init__(master, height=HEIGHT + 8, highlightthickness=0, borderwidth=0, cursor="hand2")
        self.self_themed = True
        self._kind, self._label, self._get_theme = kind, label, get_theme
        self._counts = BadgeCounts(0, 0, 0)
        self._tip_text = ""
        self._tooltip = Tooltip(self, get_theme)
        self.bind("<Button-1>", lambda e: on_click())
        self.bind("<Enter>", lambda e: self._tip_text and self._tooltip.show(e.x_root, e.y_root, self._tip_text))
        self.bind("<Leave>", lambda e: self._tooltip.hide())
        self.redraw()

    def update_counts(self, counts: BadgeCounts, tip: str) -> None:
        self._counts, self._tip_text = counts, tip
        self.redraw()

    def redraw(self) -> None:
        theme = self._get_theme()
        self.delete("all")
        font = tkfont.Font(font=theme.font)
        bold = tkfont.Font(font=(theme.font[0], theme.font[1] + 2, "bold"))
        idle = self._counts.total == 0
        kind_color = {"assignee": theme.accent, "reviewer": theme.second}.get(self._kind, theme.text)
        color = theme.muted if idle else kind_color
        text_color = theme.muted if idle else theme.text
        count = str(self._counts.total)
        width = 12 + ICON + 7 + font.measure(self._label) + 8 + bold.measure(count) + 12
        top = 8  # room above for the dot
        background = theme.bg  # the window header the badges sit on
        self.configure(width=width + DOT // 2 + 2, background=background)
        self._box(1, top, width, top + HEIGHT - 1, theme)
        self._icon(12, top + HEIGHT / 2, color, theme)
        x = 12 + ICON + 7
        self.create_text(x, top + HEIGHT / 2, text=self._label, anchor="w", fill=text_color, font=font)
        x += font.measure(self._label) + 8
        self.create_text(x, top + HEIGHT / 2, text=count, anchor="w", fill=text_color, font=bold)
        if self._counts.new:
            small = tkfont.Font(font=(theme.font[0], max(7, theme.font[1] - 2), "bold"))
            label = str(self._counts.new)
            w = max(DOT, small.measure(label) + 8)
            x1 = width + DOT // 2
            self._pill(x1 - w, 0, x1, DOT, theme.ko[1], background)
            self.create_text(x1 - w / 2, DOT / 2, text=label, fill=theme.ko[0], font=small)

    def _box(self, x0: float, y0: float, x1: float, y1: float, theme: Theme) -> None:
        if theme.relief == "raised":  # Windows 95: bevelled button
            self.create_rectangle(x0, y0, x1, y1, fill=theme.bg, outline="")
            self.create_line(x0, y1, x0, y0, x1, y0, fill="#FFFFFF")
            self.create_line(x0, y1, x1, y1, x1, y0, fill="#404040")
            return
        radius = 8 if theme.radius else 0
        _round_rect(self, x0, y0, x1, y1, radius, theme.surface, theme.border)

    def _pill(self, x0: float, y0: float, x1: float, y1: float, fill: str, ring: str) -> None:
        _round_rect(self, x0, y0, x1, y1, (y1 - y0) / 2, fill, ring)

    def _icon(self, x: float, y: float, color: str, theme: Theme) -> None:
        """Merge arrows for the assignee, an eye for the reviewer, a pencil for the author; plain lines so
        every theme draws them."""
        w = 2
        if self._kind == "author":
            self.create_line(x + 2, y + 7, x + 13, y - 4, fill=color, width=w)
            self.create_line(x + 6, y + 9, x + 17, y - 2, fill=color, width=w)
            self.create_line(x + 13, y - 4, x + 15, y - 6, x + 19, y - 2, x + 17, y - 2, fill=color, width=w)
            self.create_line(x + 2, y + 7, x + 1, y + 10, x + 6, y + 9, fill=color, width=w)
        elif self._kind == "assignee":
            self.create_oval(x + 1, y - 8, x + 5, y - 4, outline=color, width=w)
            self.create_oval(x + 1, y + 4, x + 5, y + 8, outline=color, width=w)
            self.create_oval(x + 12, y - 2, x + 16, y + 2, outline=color, width=w)
            self.create_line(x + 3, y - 4, x + 3, y + 4, fill=color, width=w)
            self.create_line(x + 3, y - 4, x + 3, y - 1, x + 7, y, x + 12, y, fill=color, width=w, smooth=True)
        else:
            self.create_line(x, y, x + 4, y - 4, x + 9, y - 6, x + 14, y - 4, x + 18, y, x + 14, y + 4,
                             x + 9, y + 6, x + 4, y + 4, x, y, fill=color, width=w, smooth=True)
            self.create_oval(x + 6, y - 3, x + 12, y + 3, outline=color, width=w)


def _round_rect(canvas: tk.Canvas, x0: float, y0: float, x1: float, y1: float, r: float, fill: str,
                outline: str) -> None:
    if r <= 0:
        canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline)
        return
    points = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
              x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    canvas.create_polygon(points, smooth=True, fill=fill, outline=outline)
