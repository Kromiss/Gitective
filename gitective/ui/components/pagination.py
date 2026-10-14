"""Web-style pager: page size choice, range label, page buttons (PA-01..PA-03)."""

from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from gitective.settings.config_file import PAGE_SIZES

MAX_PAGE_BUTTONS = 7


class Pager(ttk.Frame):
    """Emits on_change(page, page_size) whenever the user navigates."""

    def __init__(self, master: tk.Misc, on_change: Callable[[int, int], None], page_size: int = 20) -> None:
        super().__init__(master)
        self._on_change = on_change
        self.page = 1
        self.total = 0
        self._size = tk.StringVar(value=str(page_size if page_size in PAGE_SIZES else PAGE_SIZES[0]))
        ttk.Label(self, text="Afficher", style="Muted.TLabel").pack(side="left")
        size_box = ttk.Combobox(self, textvariable=self._size, values=[str(s) for s in PAGE_SIZES],
                                width=5, state="readonly")
        size_box.pack(side="left", padx=6)
        size_box.bind("<<ComboboxSelected>>", lambda e: self._go(1))
        ttk.Label(self, text="par page", style="Muted.TLabel").pack(side="left")
        self._buttons = ttk.Frame(self)
        self._buttons.pack(side="right")
        self._range = ttk.Label(self, style="Muted.TLabel")
        self._range.pack(side="right", padx=12)

    @property
    def page_size(self) -> int:
        return int(self._size.get())

    @property
    def page_count(self) -> int:
        return max(1, math.ceil(self.total / self.page_size))

    def slice(self) -> slice:
        """Slice of the full list for the current page."""
        start = (self.page - 1) * self.page_size
        return slice(start, start + self.page_size)

    def update_total(self, total: int, reset: bool = False) -> None:
        """Set the item count; optionally go back to page 1."""
        self.total = total
        if reset:
            self.page = 1
        self.page = min(self.page, self.page_count)
        self._render()

    def _go(self, page: int) -> None:
        self.page = max(1, min(page, self.page_count))
        self._render()
        self._on_change(self.page, self.page_size)

    def _render(self) -> None:
        for child in self._buttons.winfo_children():
            child.destroy()
        first = (self.page - 1) * self.page_size + 1 if self.total else 0
        last = min(self.total, self.page * self.page_size)
        self._range.configure(text=f"{first}–{last} sur {self.total}")
        count = self.page_count
        start = max(1, min(self.page - MAX_PAGE_BUTTONS // 2, count - MAX_PAGE_BUTTONS + 1))
        end = min(count, start + MAX_PAGE_BUTTONS - 1)
        prev = ttk.Button(self._buttons, text="‹", width=3, command=lambda: self._go(self.page - 1))
        prev.pack(side="left", padx=2)
        if self.page == 1:
            prev.state(["disabled"])
        for number in range(start, end + 1):
            style = "Accent.TButton" if number == self.page else "TButton"
            ttk.Button(self._buttons, text=str(number), width=3, style=style,
                       command=lambda n=number: self._go(n)).pack(side="left", padx=2)
        nxt = ttk.Button(self._buttons, text="›", width=3, command=lambda: self._go(self.page + 1))
        nxt.pack(side="left", padx=2)
        if self.page >= count:
            nxt.state(["disabled"])
