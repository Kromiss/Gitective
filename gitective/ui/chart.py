"""Weekly score line chart drawn on a Tk Canvas (ST-09)."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from gitective.ui.themes import Theme

MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP, MARGIN_BOTTOM = 56, 24, 40, 30


@dataclass(frozen=True)
class Series:
    """One curve: label, one value per week (None = no data), emphasis."""

    label: str
    values: Sequence[float | None]
    main: bool = False


class WeeklyChart(tk.Canvas):
    """Score (0-100 %) per week; the first series is drawn thicker (global)."""

    def __init__(self, master: tk.Misc, get_theme: Callable[[], Theme], height: int = 240) -> None:
        super().__init__(master, height=height, highlightthickness=0, borderwidth=0)
        self.self_themed = True
        self._get_theme = get_theme
        self._weeks: list[str] = []
        self._series: list[Series] = []
        self.bind("<Configure>", lambda e: self.redraw())

    def set_data(self, weeks: Sequence[str], series: Sequence[Series]) -> None:
        self._weeks = list(weeks)
        self._series = list(series)
        self.redraw()

    def redraw(self) -> None:
        theme = self._get_theme()
        font = tkfont.Font(font=theme.font)
        bold = tkfont.Font(font=(theme.font[0], theme.font[1], "bold"))
        self.configure(background=theme.surface)
        self.delete("all")
        width, height = max(self.winfo_width(), 300), max(self.winfo_height(), 160)
        left, right = MARGIN_LEFT, width - MARGIN_RIGHT
        top, bottom = MARGIN_TOP, height - MARGIN_BOTTOM
        self.create_text(16, 16, text="Score moyen par semaine", anchor="w", fill=theme.text, font=bold)

        def y_of(value: float) -> float:
            return bottom - (bottom - top) * value / 100

        for value in (0, 25, 50, 75, 100):
            y = y_of(value)
            self.create_line(left, y, right, y, fill=theme.border if value == 0 else theme.header)
            self.create_text(left - 8, y, text=f"{value} %", anchor="e", fill=theme.muted, font=font)

        if not self._weeks:
            self.create_text((left + right) / 2, (top + bottom) / 2, text="Aucune donnée", fill=theme.muted, font=font)
            return

        count = len(self._weeks)
        step = (right - left) / max(count, 1)

        def x_of(index: int) -> float:
            return left + step * (index + 0.5)

        label_every = max(1, int(count / max(1, (right - left) // 48)))
        for index, label in enumerate(self._weeks):
            if index % label_every == 0:
                self.create_text(x_of(index), bottom + 14, text=label, fill=theme.muted, font=font)

        legend_x = right
        for number, series in reversed(list(enumerate(self._series))):
            color = theme.chart[number % len(theme.chart)]
            line_width = 4 if series.main else 2
            segment: list[float] = []
            for index, value in enumerate(series.values):
                if value is None:
                    if len(segment) >= 4:
                        self.create_line(*segment, fill=color, width=line_width, joinstyle="round")
                    segment = []
                    continue
                x, y = x_of(index), y_of(value)
                segment += [x, y]
                radius = 4 if series.main else 3
                self.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline=color)
            if len(segment) >= 4:
                self.create_line(*segment, fill=color, width=line_width, joinstyle="round")
            text_width = font.measure(series.label)
            legend_x -= text_width
            self.create_text(legend_x, 16, text=series.label, anchor="w", fill=theme.text, font=font)
            legend_x -= 22
            self.create_line(legend_x, 16, legend_x + 16, 16, fill=color, width=line_width)
            legend_x -= 16
