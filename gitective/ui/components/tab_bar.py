"""Main tabs drawn in the window header: quiet labels, the selected one underlined in the accent color."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from gitective.ui.themes import Theme

UNDERLINE = 2  # px of the accent bar under the selected tab


class TabBar(tk.Frame):
    """Clickable tab labels for a ttk.Notebook whose own tabs are hidden (Pages.TNotebook)."""

    def __init__(self, master: tk.Misc, get_theme: Callable[[], Theme], on_select: Callable[[int], None]) -> None:
        super().__init__(master, borderwidth=0, highlightthickness=0)
        self._get_theme = get_theme
        self._on_select = on_select
        self._tabs: list[tuple[tk.Frame, tk.Label, tk.Frame]] = []
        self._selected = 0
        self._hover: int | None = None

    def add(self, text: str) -> None:
        index = len(self._tabs)
        cell = tk.Frame(self, borderwidth=0, highlightthickness=0, cursor="hand2")
        cell.pack(side="left", fill="y")
        label = tk.Label(cell, text=text, padx=14, borderwidth=0, cursor="hand2")
        label.pack(side="top", fill="both", expand=True)
        bar = tk.Frame(cell, height=UNDERLINE, borderwidth=0, highlightthickness=0)
        bar.pack(side="bottom", fill="x")
        for widget in (cell, label):
            widget.bind("<Button-1>", lambda e, i=index: self._on_select(i))
            widget.bind("<Enter>", lambda e, i=index: self._set_hover(i))
            widget.bind("<Leave>", lambda e: self._set_hover(None))
        self._tabs.append((cell, label, bar))
        self.restyle()

    def select(self, index: int) -> None:
        """Show which page is selected (the notebook itself is switched by the caller)."""
        self._selected = index
        self.restyle()

    def _set_hover(self, index: int | None) -> None:
        self._hover = index
        self.restyle()

    def restyle(self) -> None:
        theme = self._get_theme()
        self.configure(background=theme.bg)
        for index, (cell, label, bar) in enumerate(self._tabs):
            selected = index == self._selected
            color = theme.text if selected or index == self._hover else theme.muted
            cell.configure(background=theme.bg)
            label.configure(background=theme.bg, foreground=color, font=(theme.font[0], theme.font[1] + 1))
            bar.configure(background=theme.accent if selected else theme.bg)
