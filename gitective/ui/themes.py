"""Fixed visual themes (TH-01 to TH-04) and their application to Tk/ttk."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk


@dataclass(frozen=True)
class Theme:
    """Every color and font used by the interface."""

    key: str
    label: str
    bg: str
    surface: str
    text: str
    muted: str
    border: str
    header: str
    accent: str
    accent_text: str
    highlight: str
    link: str
    ok: tuple[str, str]
    ko: tuple[str, str]
    na: tuple[str, str]
    green: tuple[str, str]
    orange: tuple[str, str]
    red: tuple[str, str]
    error: tuple[str, str]
    success: tuple[str, str]
    info: tuple[str, str]
    tooltip: tuple[str, str]
    font: tuple[str, int]
    mono: tuple[str, int]
    relief: str = "flat"
    chart: tuple[str, ...] = ("#2B3A5C", "#C9622F", "#2F8F8A", "#5B4A8A", "#2F7A57", "#8A3D5C", "#7A5A1F")

    def status_colors(self, status: str) -> tuple[str, str]:
        """(background, foreground) of an OK / KO / N/A cell."""
        return {"ok": self.ok, "ko": self.ko}.get(status, self.na)

    def level_colors(self, level: str) -> tuple[str, str]:
        """(background, foreground) of a score level."""
        return {"green": self.green, "orange": self.orange}.get(level, self.red)


THEMES: dict[str, Theme] = {
    "light": Theme(
        key="light", label="Clair", bg="#F5F5F2", surface="#FFFFFF", text="#1C2230", muted="#5E6676",
        border="#D9DAD5", header="#F0F1EE", accent="#2B3A5C", accent_text="#FFFFFF", highlight="#C9622F",
        link="#2B3A5C", ok=("#E3F3E9", "#17643A"), ko=("#FCE8E6", "#A8201A"), na=("#ECEDEF", "#4B5563"),
        green=("#E3F3E9", "#17643A"), orange=("#FDF0DC", "#8A4205"), red=("#FCE8E6", "#A8201A"),
        error=("#FCE8E6", "#7A1712"), success=("#E3F3E9", "#12502E"), info=("#E6ECF7", "#1F3157"),
        tooltip=("#1C2230", "#FFFFFF"), font=("Segoe UI", 10), mono=("Consolas", 10),
    ),
    "dark": Theme(
        key="dark", label="Sombre", bg="#16191F", surface="#1F232B", text="#E6E8EC", muted="#9AA1AE",
        border="#323844", header="#262B35", accent="#6C8CD5", accent_text="#0E1116", highlight="#E08A54",
        link="#8FB0F5", ok=("#183A27", "#7FD8A2"), ko=("#4A1E1C", "#FF9D94"), na=("#2C313B", "#AEB4BF"),
        green=("#183A27", "#7FD8A2"), orange=("#46341A", "#F5C27A"), red=("#4A1E1C", "#FF9D94"),
        error=("#4A1E1C", "#FFD3CF"), success=("#183A27", "#C6F0D6"), info=("#1E2A44", "#C9D7F5"),
        tooltip=("#E6E8EC", "#16191F"), font=("Segoe UI", 10), mono=("Consolas", 10),
        chart=("#8FB0F5", "#E08A54", "#5CC6BF", "#B39DEB", "#7FD8A2", "#F08FB5", "#E6C36A"),
    ),
    "win95": Theme(
        key="win95", label="Windows 95", bg="#C0C0C0", surface="#FFFFFF", text="#000000", muted="#404040",
        border="#808080", header="#C0C0C0", accent="#000080", accent_text="#FFFFFF", highlight="#000080",
        link="#0000EE", ok=("#C0C0C0", "#006400"), ko=("#C0C0C0", "#B00000"), na=("#C0C0C0", "#404040"),
        green=("#C0C0C0", "#006400"), orange=("#C0C0C0", "#8A5A00"), red=("#C0C0C0", "#B00000"),
        error=("#FFFFE1", "#800000"), success=("#FFFFE1", "#004000"), info=("#FFFFE1", "#000080"),
        tooltip=("#FFFFE1", "#000000"), font=("MS Sans Serif", 9), mono=("Courier New", 9), relief="raised",
        chart=("#000080", "#800000", "#008080", "#800080", "#008000", "#808000", "#000000"),
    ),
    "matrix": Theme(
        key="matrix", label="Matrix", bg="#000000", surface="#030A03", text="#33FF66", muted="#1E9C40",
        border="#0F4A1E", header="#061406", accent="#33FF66", accent_text="#000000", highlight="#B6FFC8",
        link="#7CFF9E", ok=("#0B3A16", "#66FF8A"), ko=("#1A1A1A", "#7FB08A"), na=("#0A0F0A", "#5A6B5A"),
        green=("#0B3A16", "#66FF8A"), orange=("#102810", "#B6FFC8"), red=("#1A1A1A", "#7FB08A"),
        error=("#0B200B", "#B6FFC8"), success=("#0B3A16", "#66FF8A"), info=("#061406", "#33FF66"),
        tooltip=("#33FF66", "#000000"), font=("Consolas", 10), mono=("Consolas", 10),
        chart=("#33FF66", "#B6FFC8", "#1E9C40", "#7CFF9E", "#0F7A2E", "#D8FFE2", "#5ACC77"),
    ),
}


def get_theme(key: str) -> Theme:
    return THEMES.get(key, THEMES["light"])


def apply_theme(root: tk.Tk, theme: Theme) -> None:
    """Style ttk widgets and recolor plain Tk widgets already created."""
    style = ttk.Style(root)
    style.theme_use("clam")
    border = 2 if theme.relief == "raised" else 1
    style.configure(".", background=theme.bg, foreground=theme.text, font=theme.font,
                    fieldbackground=theme.surface, bordercolor=theme.border, lightcolor=theme.bg,
                    darkcolor=theme.border, troughcolor=theme.header, insertcolor=theme.text,
                    selectbackground=theme.accent, selectforeground=theme.accent_text)
    style.configure("TFrame", background=theme.bg)
    style.configure("Surface.TFrame", background=theme.surface)
    style.configure("Bar.TFrame", background=theme.surface)
    style.configure("TLabel", background=theme.bg, foreground=theme.text)
    style.configure("Bar.TLabel", background=theme.surface, foreground=theme.text)
    style.configure("Muted.TLabel", background=theme.bg, foreground=theme.muted)
    style.configure("BarMuted.TLabel", background=theme.surface, foreground=theme.muted)
    style.configure("Title.TLabel", background=theme.bg, foreground=theme.text, font=(theme.font[0], theme.font[1] + 2, "bold"))
    style.configure("Section.TLabel", background=theme.surface, foreground=theme.text, font=(theme.font[0], theme.font[1] + 1, "bold"))
    style.configure("TButton", background=theme.surface, foreground=theme.text, borderwidth=border,
                    relief=theme.relief if theme.relief == "raised" else "solid", padding=(10, 4))
    style.map("TButton", background=[("active", theme.header), ("disabled", theme.bg)],
              foreground=[("disabled", theme.muted)])
    style.configure("Accent.TButton", background=theme.accent, foreground=theme.accent_text, font=(theme.font[0], theme.font[1], "bold"))
    style.map("Accent.TButton", background=[("active", theme.highlight)], foreground=[("active", theme.accent_text)])
    style.configure("Toolbutton", background=theme.surface, foreground=theme.text, padding=(10, 4),
                    borderwidth=border, relief=theme.relief if theme.relief == "raised" else "solid")
    style.map("Toolbutton", background=[("selected", theme.accent), ("active", theme.header)],
              foreground=[("selected", theme.accent_text)])
    style.configure("TCheckbutton", background=theme.surface, foreground=theme.text, indicatorbackground=theme.surface,
                    indicatorforeground=theme.text)
    style.map("TCheckbutton", background=[("active", theme.surface)])
    style.configure("TRadiobutton", background=theme.surface, foreground=theme.text,
                    indicatorbackground=theme.surface, indicatorforeground=theme.text)
    style.map("TRadiobutton", background=[("active", theme.surface)],
              indicatorbackground=[("selected", theme.accent)])
    style.configure("TEntry", fieldbackground=theme.surface, foreground=theme.text, padding=4)
    style.configure("TCombobox", fieldbackground=theme.surface, foreground=theme.text, background=theme.surface,
                    arrowcolor=theme.text)
    style.map("TCombobox", fieldbackground=[("readonly", theme.surface)], foreground=[("readonly", theme.text)])
    style.configure("TNotebook", background=theme.bg, borderwidth=0, tabmargins=(12, 6, 12, 0))
    style.configure("TNotebook.Tab", background=theme.header, foreground=theme.muted, padding=(16, 6), borderwidth=border)
    style.map("TNotebook.Tab", background=[("selected", theme.surface)], foreground=[("selected", theme.text)])
    style.configure("TLabelframe", background=theme.surface, bordercolor=theme.border)
    style.configure("TLabelframe.Label", background=theme.bg, foreground=theme.text,
                    font=(theme.font[0], theme.font[1] + 1, "bold"))
    style.configure("Horizontal.TProgressbar", background=theme.highlight, troughcolor=theme.header, bordercolor=theme.border)
    style.configure("Vertical.TScrollbar", background=theme.header, troughcolor=theme.bg, arrowcolor=theme.text)
    style.configure("TSeparator", background=theme.border)

    root.configure(background=theme.bg)
    root.option_add("*Font", theme.font)
    root.option_add("*TCombobox*Listbox.background", theme.surface)
    root.option_add("*TCombobox*Listbox.foreground", theme.text)
    _recolor_tree(root, theme)


def _recolor_tree(widget: tk.Misc, theme: Theme) -> None:
    """Recolor classic Tk widgets (Text, Listbox, Canvas, Toplevel) recursively."""
    for child in widget.winfo_children():
        if isinstance(child, (tk.Text, tk.Listbox)):
            child.configure(background=theme.surface, foreground=theme.text, insertbackground=theme.text,
                            selectbackground=theme.accent, selectforeground=theme.accent_text,
                            highlightbackground=theme.border, highlightcolor=theme.accent, font=theme.font)
        elif isinstance(child, tk.Canvas) and not getattr(child, "self_themed", False):
            child.configure(background=theme.surface, highlightbackground=theme.border)
        elif isinstance(child, tk.Toplevel):
            child.configure(background=theme.bg)
        _recolor_tree(child, theme)
