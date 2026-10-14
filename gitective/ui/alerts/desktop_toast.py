"""Desktop notifications of the Merger profile: topmost borderless windows and taskbar flash (5.8)."""

from __future__ import annotations

import sys
import tkinter as tk
from collections.abc import Callable, Sequence

from gitective.review.profile import Notice
from gitective.ui.themes import Theme

WIDTH = 380
MARGIN = 16
LIFETIME_MS = 8000
MAX_SHOWN = 3


class Toasts:
    """Stack of at most three notifications in the bottom-right corner of the screen (NO-02, NO-05)."""

    def __init__(self, root: tk.Tk, get_theme: Callable[[], Theme], open_url: Callable[[str], None],
                 open_merge_requests: Callable[[], None], logo: tk.PhotoImage | None = None) -> None:
        self._root = root
        self._get_theme = get_theme
        self._open_url = open_url
        self._open_tab = open_merge_requests
        self._logo = logo
        self._windows: list[tk.Toplevel] = []

    def show(self, notices: Sequence[Notice]) -> None:
        """Up to three notices; beyond, one summary per kind replaces them (NO-05)."""
        if not notices:
            return
        if len(notices) <= MAX_SHOWN:
            for notice in notices:
                people = f"{notice.author} → {notice.merger}" if notice.merger else f"par {notice.author}"
                self._popup(notice.title, notice.mr.title, notice.repo.split("/")[-1], people,
                            self._color(notice), lambda n=notice: self._open_url(n.mr.web_url),
                            "Cliquer pour ouvrir dans GitLab")
            return
        theme = self._get_theme()
        merges = [n for n in notices if n.kind == "merge"]
        roles = [n for n in notices if n.kind == "role"]
        if roles:
            self._popup("À traiter", f"{len(roles)} MR assignées ou en relecture", "", "", theme.accent,
                        self._open_tab, "Cliquer pour ouvrir Gitective")
        if merges:
            self._popup("Nouveaux merges", f"{len(merges)} MR mergées sur les dépôts suivis", "", "", theme.ok[1],
                        self._open_tab, "Cliquer pour ouvrir Gitective")

    def _color(self, notice: Notice) -> str:
        """Same colors as the badges: assignee = accent, reviewer = secondary accent, merge = green."""
        theme = self._get_theme()
        if notice.kind == "merge":
            return theme.ok[1]
        return theme.second if notice.title == "Relecture demandée" else theme.accent

    def _popup(self, kind: str, title: str, repo: str, people: str, color: str, on_click: Callable[[], None],
               hint: str) -> None:
        theme = self._get_theme()
        font, size = theme.font
        window = tk.Toplevel(self._root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(background=theme.border)
        outer = tk.Frame(window, background=theme.surface)
        outer.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Frame(outer, background=color, width=5).pack(side="left", fill="y")  # role color, like the badges
        body = tk.Frame(outer, background=theme.surface, padx=14, pady=12)
        body.pack(side="left", fill="both", expand=True)

        head = tk.Frame(body, background=theme.surface)
        head.pack(fill="x")
        close = tk.Label(head, text="✕", background=theme.surface, foreground=theme.muted, cursor="hand2",
                         font=(font, size + 1))
        close.pack(side="right", anchor="n")
        if self._logo is not None:
            tk.Label(head, image=self._logo, background=theme.surface).pack(side="left", padx=(0, 10))
        names = tk.Frame(head, background=theme.surface)
        names.pack(side="left", fill="x")
        tk.Label(names, text="GITECTIVE · à l'instant", background=theme.surface, foreground=theme.muted,
                 font=(font, size - 2, "bold"), anchor="w").pack(fill="x")
        tk.Label(names, text=kind, background=theme.surface, foreground=color, font=(font, size + 1, "bold"),
                 anchor="w").pack(fill="x")

        tk.Label(body, text=title, background=theme.surface, foreground=theme.text, anchor="w", justify="left",
                 wraplength=WIDTH - 50, font=(font, size + 2, "bold")).pack(fill="x", pady=(10, 4))
        if repo or people:
            meta = tk.Frame(body, background=theme.surface)
            meta.pack(fill="x")
            if repo:
                tk.Label(meta, text=repo, background=theme.header, foreground=theme.text, padx=7, pady=1,
                         font=(theme.mono[0], theme.mono[1] - 1)).pack(side="left")
            if people:
                tk.Label(meta, text=people, background=theme.surface, foreground=theme.muted,
                         font=(font, size - 1)).pack(side="left", padx=(8, 0))
        tk.Frame(body, background=theme.border, height=1).pack(fill="x", pady=(10, 6))
        tk.Label(body, text=f"{hint}  ↗", background=theme.surface, foreground=theme.link, anchor="w",
                 font=(font, size - 1)).pack(fill="x")

        hovered = [False]

        def clicked(_event: tk.Event) -> None:
            on_click()
            self._close(window)

        def expire() -> None:
            if hovered[0]:
                window.after(1000, expire)  # stays while the mouse is over it (NO-02)
            else:
                self._close(window)

        for widget in _all(window):
            if widget is not close:
                widget.bind("<Button-1>", clicked)
                widget.configure(cursor="hand2")  # type: ignore[call-arg]
        close.bind("<Button-1>", lambda e: self._close(window))
        window.bind("<Enter>", lambda e: hovered.__setitem__(0, True))
        window.bind("<Leave>", lambda e: hovered.__setitem__(0, False))
        self._windows.append(window)
        self._place()
        window.after(LIFETIME_MS, expire)

    def _close(self, window: tk.Toplevel) -> None:
        if window in self._windows:
            self._windows.remove(window)
            window.destroy()
            self._place()

    def _place(self) -> None:
        """Stack from the bottom-right corner upwards, the oldest at the bottom."""
        screen_w, screen_h = self._root.winfo_screenwidth(), self._root.winfo_screenheight()
        y = screen_h - MARGIN - 40  # above the Windows taskbar
        for window in self._windows:
            window.update_idletasks()
            height = window.winfo_reqheight()
            y -= height
            window.geometry(f"{WIDTH}x{height}+{screen_w - WIDTH - MARGIN}+{y}")
            y -= 8


def _all(widget: tk.Misc) -> list[tk.Misc]:
    found: list[tk.Misc] = [widget]
    for child in widget.winfo_children():
        found += _all(child)
    return found


def flash_taskbar(root: tk.Tk) -> None:
    """Make the minimized window blink in the taskbar (Windows only, NO-06)."""
    if sys.platform != "win32" or root.focus_displayof() is not None:
        return
    try:
        import ctypes
        from ctypes import wintypes

        class FlashInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                        ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]

        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        flash_all, until_foreground = 0x3, 0xC  # FLASHW_ALL, FLASHW_TIMERNOFG
        info = FlashInfo(ctypes.sizeof(FlashInfo), hwnd, flash_all | until_foreground, 0, 0)
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except (AttributeError, OSError):
        pass  # flashing is a bonus: never break the synchronisation for it
