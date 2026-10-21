"""Reusable widgets: tooltip, multi-select dropdown, scrollable frame, project picker."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
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
        # Keep the tooltip inside the screen (flip to the left near the right edge).
        self._window.update_idletasks()
        width = self._window.winfo_reqwidth()
        x = x_root + 14
        if x + width > self._window.winfo_screenwidth():
            x = max(0, x_root - width - 8)
        self._window.wm_geometry(f"+{x}+{y_root + 16}")
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

    def set_items(self, items: Sequence[tuple[str, str]], keep_order: bool = False) -> None:
        """Replace the (key, label) choices, keeping the current selection; sorted by label unless keep_order."""
        self._items = list(items) if keep_order else sorted(items, key=lambda i: i[1].casefold())
        self._refresh_text()

    def set_selected(self, keys: Sequence[str]) -> None:
        self._selected = list(keys)
        self._refresh_text()

    def _refresh_text(self) -> None:
        if not self._selected:
            text = f"{self._label} : {self._all_text} ({len(self._items)})"
        elif len(self._selected) == 1:
            labels = dict(self._items)
            text = f"{self._label} : {labels.get(self._selected[0], '1 sélection')}"
        else:
            text = f"{self._label} : {len(self._selected)} sélection(s)"
        # An active filter stands out (accent border and text).
        self.configure(text=text + "  ▾", style="Active.TButton" if self._selected else "TButton")

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
        # As wide as the longest choice (long repository paths, people names), within reason.
        font = tkfont.Font(font=theme.font)
        longest = max((font.measure(text) for _, text in self._items), default=0)
        frame.canvas.configure(width=max(280, min(560, longest + 60)), height=min(320, 30 * max(1, len(self._items))))
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
    """Searchable checklist of GitLab projects (SD-02).

    A Treeview row per project instead of one Checkbutton widget each, so
    thousands of projects display and filter instantly. Ticked projects are
    listed first.
    """

    def __init__(self, master: tk.Misc, get_theme: ThemeGetter) -> None:
        super().__init__(master, style="Surface.TFrame")
        self._search = tk.StringVar()
        self._search.trace_add("write", lambda *_: self._render())
        ttk.Label(self, text="Rechercher", style="BarMuted.TLabel").pack(anchor="w")
        ttk.Entry(self, textvariable=self._search).pack(fill="x", pady=(2, 6))
        self._tree = ttk.Treeview(self, show="tree", selectmode="browse")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._tree.bind("<Button-1>", lambda e: self._toggle(self._tree.identify_row(e.y)))
        self._tree.bind("<space>", lambda e: self._toggle(self._tree.focus()))
        self._projects: list[tuple[int, str]] = []
        self._checked: set[int] = set()

    def set_projects(self, projects: Sequence[tuple[int, str]], checked: Sequence[int]) -> None:
        """Show (id, path) projects; checked IDs are ticked."""
        self._projects = sorted(projects, key=lambda p: p[1].casefold())
        self._checked = set(checked) & {pid for pid, _ in self._projects}
        self._render()

    def checked(self) -> list[int]:
        return list(self._checked)

    def _render(self) -> None:
        self._tree.delete(*self._tree.get_children())
        needle = self._search.get().casefold()
        rows = [p for p in self._projects if needle in p[1].casefold()]
        rows.sort(key=lambda p: p[0] not in self._checked)  # stable: ticked first, then by path
        for pid, path in rows:
            self._tree.insert("", "end", iid=str(pid), text=self._label(pid, path))

    def _toggle(self, iid: str) -> None:
        if not iid:
            return
        pid = int(iid)
        self._checked ^= {pid}
        path = next(p for i, p in self._projects if i == pid)
        self._tree.item(iid, text=self._label(pid, path))

    def _label(self, pid: int, path: str) -> str:
        return f"{'☑' if pid in self._checked else '☐'}  {path}"
