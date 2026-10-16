"""Shared frame of the side panels (MR and tag details): scrolling, text wrap and the small building blocks."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from gitective.ui.components.widgets import ScrollableFrame
from gitective.ui.themes import Theme


class SidePanel(ttk.Frame):
    """Scrollable column of cards; subclasses fill `self._scroller.inner` in render() (DE-02, TG-07)."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self._scroller = ScrollableFrame(self)
        self._scroller.pack(fill="both", expand=True)
        self.bind("<Configure>", lambda e: self._wrap_changed(e.width))
        self._wrap = 360
        self._error = ""
        self._loading = False

    def render(self) -> None:
        raise NotImplementedError

    def _clear(self, theme: Theme) -> tk.Misc:
        """Empty the panel and return the frame to fill."""
        inner = self._scroller.inner
        for child in inner.winfo_children():
            child.destroy()
        self._scroller.set_background(theme.bg)
        return inner

    def _bind_wheel(self) -> None:
        """Children were rebuilt: scroll with the wheel over all of them."""
        for widget in _descendants(self._scroller.inner):
            self._scroller.bind_wheel(widget)

    def _close_button(self, parent: tk.Misc, theme: Theme, on_close: Callable[[], None]) -> None:
        close = tk.Label(parent, text="✕", background=theme.bg, foreground=theme.muted, cursor="hand2",
                         font=self._font(theme, 3))
        close.pack(side="right", anchor="n")
        close.bind("<Button-1>", lambda e: on_close())

    def _wrap_changed(self, width: int) -> None:
        wrap = max(200, width - 70)
        if abs(wrap - self._wrap) > 20:
            self._wrap = wrap
            self.render()

    def _font(self, theme: Theme, delta: int = 0, weight: str = "normal") -> tuple[str, int, str]:
        return (theme.font[0], theme.font[1] + delta, weight)

    def _card(self, parent: tk.Misc, theme: Theme, title: str = "", right: str = "",
              right_colors: tuple[str, str] | None = None) -> tk.Frame:
        card = tk.Frame(parent, background=theme.surface, highlightthickness=1, highlightbackground=theme.border)
        card.pack(fill="x", padx=12, pady=(10, 0))
        if title or right:
            head = tk.Frame(card, background=theme.surface)
            head.pack(fill="x", padx=12, pady=(9, 4))
            tk.Label(head, text=title.upper(), background=theme.surface, foreground=theme.muted,
                     font=self._font(theme, -2, "bold")).pack(side="left")
            if right:
                bg, fg = right_colors or (theme.surface, theme.text)
                tk.Label(head, text=right, background=bg, foreground=fg, padx=6,
                         font=self._font(theme, 2, "bold")).pack(side="right")
        body = tk.Frame(card, background=theme.surface)
        body.pack(fill="x", padx=12, pady=(0, 9))
        return body

    def _line(self, parent: tk.Misc, theme: Theme, left: str, right: str = "", color: str | None = None,
              right_color: str | None = None, icon: str = "", icon_color: str = "", mono: bool = False) -> None:
        row = tk.Frame(parent, background=theme.surface)
        row.pack(fill="x", pady=1)
        if icon:
            tk.Label(row, text=icon, width=2, background=theme.surface, foreground=icon_color,
                     font=self._font(theme, 0, "bold")).pack(side="left")
        font = (theme.mono[0], theme.mono[1] - 1) if mono else self._font(theme)
        if right:
            tk.Label(row, text=right, background=theme.surface, foreground=right_color or theme.muted,
                     font=font).pack(side="right")
        tk.Label(row, text=left, background=theme.surface, foreground=color or theme.text, font=font,
                 justify="left", anchor="w", wraplength=self._wrap - 120 if right else self._wrap - 20).pack(
            side="left", fill="x")

    def _placeholder(self, parent: tk.Misc, theme: Theme, title: str) -> None:
        body = self._card(parent, theme, title)
        text = self._error or "Chargement…"
        tk.Label(body, text=text, background=theme.surface, foreground=theme.muted, font=self._font(theme),
                 wraplength=self._wrap - 20, justify="left").pack(anchor="w")

    def _tag(self, parent: tk.Misc, text: str, colors: tuple[str, str], theme: Theme) -> None:
        tk.Label(parent, text=text, background=colors[0], foreground=colors[1], padx=7, pady=1,
                 font=self._font(theme, -1, "bold")).pack(side="left", padx=(0, 6), pady=2)


def _descendants(widget: tk.Misc) -> list[tk.Misc]:
    found = []
    for child in widget.winfo_children():
        found.append(child)
        found.extend(_descendants(child))
    return found
