"""Reusable widgets: tooltip, multi-select dropdown, scrollable frame, project picker."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from gitective.ui.themes import Theme

ThemeGetter = Callable[[], Theme]


class Tooltip:
    """Small borderless window following the mouse (TA-01)."""

    def __init__(self, master: tk.Misc, get_theme: ThemeGetter) -> None:
        self._master = master
        self._get_theme = get_theme
        self._window: tk.Toplevel | None = None
        self._label: tk.Label | None = None
        self._text = ""

    def show(self, x_root: int, y_root: int, text: str) -> None:
        theme = self._get_theme()
        if self._window is None:
            self._window = tk.Toplevel(self._master)
            self._window.wm_overrideredirect(True)
            self._label = tk.Label(self._window, justify="left", padx=10, pady=6, wraplength=320)
            self._label.pack()
        assert self._label is not None
        if text != self._text:
            self._label.configure(text=text, background=theme.tooltip[0], foreground=theme.tooltip[1], font=theme.font)
            self._text = text
        self._window.wm_geometry(f"+{x_root + 14}+{y_root + 16}")
        self._window.deiconify()
        self._window.lift()

    def hide(self) -> None:
        if self._window is not None:
            self._window.withdraw()
        self._text = ""


class ScrollableFrame(ttk.Frame):
    """Frame with a vertical scrollbar; put children in .inner."""

    def __init__(self, master: tk.Misc, style: str = "TFrame") -> None:
        super().__init__(master, style=style)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, style=style)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.bind_wheel(self.canvas)

    def bind_wheel(self, widget: tk.Misc) -> None:
        widget.bind("<Enter>", lambda e: widget.bind_all("<MouseWheel>", self._on_wheel))
        widget.bind("<Leave>", lambda e: widget.unbind_all("<MouseWheel>"))

    def _on_wheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120) or (-1 if event.delta > 0 else 1), "units")

    def set_background(self, color: str) -> None:
        self.canvas.configure(background=color)


class MultiSelect(ttk.Button):
    """Button opening a checklist popup; an empty selection means 'all'."""

    def __init__(self, master: tk.Misc, label: str, on_change: Callable[[list[str]], None],
                 get_theme: ThemeGetter, all_text: str = "Tous") -> None:
        super().__init__(master, command=self._open)
        self._label = label
        self._all_text = all_text
        self._on_change = on_change
        self._get_theme = get_theme
        self._items: list[tuple[str, str]] = []
        self._selected: list[str] = []
        self._popup: tk.Toplevel | None = None
        self._refresh_text()

    @property
    def selected(self) -> list[str]:
        """Selected keys; empty list means every item."""
        return list(self._selected)

    def set_items(self, items: Sequence[tuple[str, str]]) -> None:
        """Replace the (key, label) choices, keeping the current selection."""
        self._items = sorted(items, key=lambda i: i[1].casefold())
        self._refresh_text()

    def set_selected(self, keys: Sequence[str]) -> None:
        self._selected = list(keys)
        self._refresh_text()

    def _refresh_text(self) -> None:
        if not self._selected:
            text = f"{self._label} : {self._all_text} ({len(self._items)})"
        else:
            text = f"{self._label} : {len(self._selected)} sélection(s)"
        self.configure(text=text + "  ▾")

    def _open(self) -> None:
        if self._popup is not None:
            self._popup.destroy()
        theme = self._get_theme()
        popup = tk.Toplevel(self, background=theme.bg)
        popup.title(self._label)
        popup.transient(self.winfo_toplevel())
        popup.geometry(f"+{self.winfo_rootx()}+{self.winfo_rooty() + self.winfo_height() + 2}")
        self._popup = popup
        variables: dict[str, tk.BooleanVar] = {}
        frame = ScrollableFrame(popup, style="Surface.TFrame")
        frame.set_background(theme.surface)
        frame.canvas.configure(width=280, height=min(320, 30 * max(1, len(self._items))))
        for key, text in self._items:
            var = tk.BooleanVar(value=(not self._selected) or key in self._selected)
            variables[key] = var
            ttk.Checkbutton(frame.inner, text=text, variable=var).pack(anchor="w", padx=10, pady=3)
        buttons = ttk.Frame(popup)
        buttons.pack(side="bottom", fill="x", padx=8, pady=8)
        frame.pack(side="top", fill="both", expand=True, padx=8, pady=(8, 0))

        def set_all(value: bool) -> None:
            for var in variables.values():
                var.set(value)

        def apply() -> None:
            chosen = [k for k, v in variables.items() if v.get()]
            self._selected = [] if len(chosen) == len(variables) or not chosen else chosen
            self._refresh_text()
            popup.destroy()
            self._popup = None
            self._on_change(self.selected)

        ttk.Button(buttons, text="Tout", command=lambda: set_all(True)).pack(side="left")
        ttk.Button(buttons, text="Aucun", command=lambda: set_all(False)).pack(side="left", padx=6)
        ttk.Button(buttons, text="Appliquer", style="Accent.TButton", command=apply).pack(side="right")
        popup.bind("<Escape>", lambda e: popup.destroy())


class ProjectPicker(ttk.Frame):
    """Searchable checklist of GitLab projects (SD-02)."""

    def __init__(self, master: tk.Misc, get_theme: ThemeGetter) -> None:
        super().__init__(master, style="Surface.TFrame")
        self._get_theme = get_theme
        self._search = tk.StringVar()
        self._search.trace_add("write", lambda *_: self._render())
        ttk.Label(self, text="Rechercher", style="BarMuted.TLabel").pack(anchor="w")
        ttk.Entry(self, textvariable=self._search).pack(fill="x", pady=(2, 6))
        self._list = ScrollableFrame(self, style="Surface.TFrame")
        self._list.set_background(get_theme().surface)
        self._list.pack(fill="both", expand=True)
        self._projects: list[tuple[int, str]] = []
        self._vars: dict[int, tk.BooleanVar] = {}

    def set_projects(self, projects: Sequence[tuple[int, str]], checked: Sequence[int]) -> None:
        """Show (id, path) projects; checked IDs are ticked."""
        self._projects = sorted(projects, key=lambda p: p[1].casefold())
        self._vars = {pid: tk.BooleanVar(value=pid in checked) for pid, _ in self._projects}
        self._render()

    def checked(self) -> list[int]:
        return [pid for pid, var in self._vars.items() if var.get()]

    def _render(self) -> None:
        for child in self._list.inner.winfo_children():
            child.destroy()
        needle = self._search.get().casefold()
        for pid, path in self._projects:
            if needle in path.casefold():
                ttk.Checkbutton(self._list.inner, text=path, variable=self._vars[pid]).pack(anchor="w", pady=2)
