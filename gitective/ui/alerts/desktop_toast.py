"""Desktop notifications of the Merger profile: topmost borderless windows and taskbar flash (5.8)."""

from __future__ import annotations

import sys
import tkinter as tk
from collections.abc import Callable, Sequence

from gitective.review.profile import Notice
from gitective.ui.themes import Theme

WIDTH = 340
MARGIN = 16
LIFETIME_MS = 8000
MAX_SHOWN = 3


class Toasts:
    """Stack of at most three notifications in the bottom-right corner of the screen (NO-02, NO-05)."""

    def __init__(self, root: tk.Tk, get_theme: Callable[[], Theme], open_url: Callable[[str], None],
                 open_merge_requests: Callable[[], None]) -> None:
        self._root = root
        self._get_theme = get_theme
        self._open_url = open_url
        self._open_tab = open_merge_requests
        self._windows: list[tk.Toplevel] = []

    def show(self, notices: Sequence[Notice]) -> None:
        """Up to three notices; beyond, one summary per kind replaces them (NO-05)."""
        if not notices:
            return
        if len(notices) <= MAX_SHOWN:
            for notice in notices:
                lines = [notice.mr.title, notice.repo, f"{notice.author} → {notice.merger}" if notice.merger
                         else notice.author]
                self._popup(notice.title, lines, lambda n=notice: self._open_url(n.mr.web_url))
            return
        merges = [n for n in notices if n.kind == "merge"]
        roles = [n for n in notices if n.kind == "role"]
        if roles:
            self._popup(f"{len(roles)} MR à traiter", ["Assignées ou en relecture"], self._open_tab)
        if merges:
            self._popup(f"{len(merges)} nouveaux merges", ["Sur les dépôts suivis"], self._open_tab)

    def _popup(self, title: str, lines: list[str], on_click: Callable[[], None]) -> None:
        theme = self._get_theme()
        window = tk.Toplevel(self._root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(background=theme.border)
        frame = tk.Frame(window, background=theme.surface, padx=14, pady=10)
        frame.pack(fill="both", expand=True, padx=1, pady=1)
        head = tk.Frame(frame, background=theme.surface)
        head.pack(fill="x")
        close = tk.Label(head, text="✕", background=theme.surface, foreground=theme.muted, cursor="hand2")
        close.pack(side="right")
        tk.Label(head, text=title, background=theme.surface, foreground=theme.accent, anchor="w",
                 font=(theme.font[0], theme.font[1], "bold")).pack(side="left")
        for index, line in enumerate(lines):
            tk.Label(frame, text=line, background=theme.surface, anchor="w", justify="left", wraplength=WIDTH - 30,
                     foreground=theme.text if index == 0 else theme.muted,
                     font=(theme.font[0], theme.font[1] + (1 if index == 0 else -1))).pack(fill="x")

        hovered = [False]

        def clicked(_event: tk.Event) -> None:
            on_click()
            self._close(window)

        def expire() -> None:
            if hovered[0]:
                window.after(1000, expire)  # stays while the mouse is over it (NO-02)
            else:
                self._close(window)

        for widget in (window, frame, head, *frame.winfo_children(), *head.winfo_children()):
            if widget is not close:
                widget.bind("<Button-1>", clicked)
                widget.configure(cursor="hand2")
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
