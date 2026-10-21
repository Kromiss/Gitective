"""Fixed visual themes (TH-00 to TH-04) and their application to Tk/ttk."""

from __future__ import annotations

import base64
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

from gitective.shared.i18n import t
from gitective.ui.rounded import blend, rounded_png

CONTROL_RADIUS = 7  # corner radius of buttons and fields in the rounded themes
SLICE = 48  # px of the stretchable middle of the rounded control images
ROUNDED_STYLES = ("TButton", "Accent.TButton", "Active.TButton", "Toolbutton", "TEntry", "TMenubutton",
                  "Active.TMenubutton", "TNotebook.Tab", "Card.TFrame")
# Images must outlive the elements using them: kept per theme, created once.
_IMAGES: dict[str, dict[str, tk.PhotoImage]] = {}
_CLAM_LAYOUTS: dict[str, object] = {}


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
    radius: int = 0  # corner radius of the Overview cards
    feature: str = ""  # background of the Overview's highlighted card (latest merges); surface when empty
    chart: tuple[str, ...] = ("#2B3A5C", "#C9622F", "#2F8F8A", "#5B4A8A", "#2F7A57", "#8A3D5C", "#7A5A1F")
    accent2: str = ""  # secondary accent: reviewer badge (5.2); accent when empty
    selection: str = ""  # background of the selected grid row; header when empty

    @property
    def second(self) -> str:
        return self.accent2 or self.accent

    @property
    def selected_row(self) -> str:
        return self.selection or self.header

    def status_colors(self, status: str) -> tuple[str, str]:
        """(background, foreground) of an OK / KO / N/A cell."""
        return {"ok": self.ok, "ko": self.ko}.get(status, self.na)

    def level_colors(self, level: str) -> tuple[str, str]:
        """(background, foreground) of a score level."""
        return {"green": self.green, "orange": self.orange}.get(level, self.red)


THEMES: dict[str, Theme] = {
    "default": Theme(
        key="default", label=t("Default"), bg="#0B1020", surface="#131A2E", text="#EEF1F8", muted="#A3ADC4",
        border="#26304B", header="#1A2238", accent="#5ED3C6", accent_text="#0B1020", highlight="#8BE6DB",
        link="#7FE0D5", ok=("#163A2E", "#5FD99E"), ko=("#3D1E22", "#FF7D74"), na=("#1E2740", "#A3ADC4"),
        green=("#163A2E", "#5FD99E"), orange=("#3A2D16", "#F5B95C"), red=("#3D1E22", "#FF7D74"),
        error=("#3D1E22", "#FFD0CC"), success=("#163A2E", "#C8F5DD"), info=("#173040", "#BFEFE9"),
        tooltip=("#EEF1F8", "#0B1020"), font=("Segoe UI", 10), mono=("Consolas", 10),
        chart=("#5ED3C6", "#F5B95C", "#8FA8FF", "#FF7D74", "#5FD99E", "#D7A6FF", "#7C87A0"),
        radius=16, feature="#172139", accent2="#9FB4FF", selection="#22395A",
    ),
    "light": Theme(
        key="light", label=t("Clair"), bg="#F5F5F2", surface="#FFFFFF", text="#1C2230", muted="#5E6676",
        border="#D9DAD5", header="#F0F1EE", accent="#2B3A5C", accent_text="#FFFFFF", highlight="#C9622F",
        link="#2B3A5C", ok=("#E3F3E9", "#17643A"), ko=("#FCE8E6", "#A8201A"), na=("#ECEDEF", "#4B5563"),
        green=("#E3F3E9", "#17643A"), orange=("#FDF0DC", "#8A4205"), red=("#FCE8E6", "#A8201A"),
        error=("#FCE8E6", "#7A1712"), success=("#E3F3E9", "#12502E"), info=("#E6ECF7", "#1F3157"),
        tooltip=("#1C2230", "#FFFFFF"), font=("Segoe UI", 10), mono=("Consolas", 10), radius=12,
        accent2="#6B4FB8", selection="#E4E9F4",
    ),
    "dark": Theme(
        key="dark", label=t("Sombre"), bg="#16191F", surface="#1F232B", text="#E6E8EC", muted="#9AA1AE",
        border="#323844", header="#262B35", accent="#6C8CD5", accent_text="#0E1116", highlight="#E08A54",
        link="#8FB0F5", ok=("#183A27", "#7FD8A2"), ko=("#4A1E1C", "#FF9D94"), na=("#2C313B", "#AEB4BF"),
        green=("#183A27", "#7FD8A2"), orange=("#46341A", "#F5C27A"), red=("#4A1E1C", "#FF9D94"),
        error=("#4A1E1C", "#FFD3CF"), success=("#183A27", "#C6F0D6"), info=("#1E2A44", "#C9D7F5"),
        tooltip=("#E6E8EC", "#16191F"), font=("Segoe UI", 10), mono=("Consolas", 10),
        chart=("#8FB0F5", "#E08A54", "#5CC6BF", "#B39DEB", "#7FD8A2", "#F08FB5", "#E6C36A"), radius=12,
        accent2="#B39DEB", selection="#2B3550",
    ),
    "win95": Theme(
        key="win95", label=t("Windows 95"), bg="#C0C0C0", surface="#FFFFFF", text="#000000", muted="#404040",
        border="#808080", header="#C0C0C0", accent="#000080", accent_text="#FFFFFF", highlight="#000080",
        link="#0000EE", ok=("#C0C0C0", "#006400"), ko=("#C0C0C0", "#B00000"), na=("#C0C0C0", "#404040"),
        green=("#C0C0C0", "#006400"), orange=("#C0C0C0", "#8A5A00"), red=("#C0C0C0", "#B00000"),
        error=("#FFFFE1", "#800000"), success=("#FFFFE1", "#004000"), info=("#FFFFE1", "#000080"),
        tooltip=("#FFFFE1", "#000000"), font=("MS Sans Serif", 9), mono=("Courier New", 9), relief="raised",
        chart=("#000080", "#800000", "#008080", "#800080", "#008000", "#808000", "#000000"),
        accent2="#008080", selection="#C8D0F0",
    ),
    "matrix": Theme(
        key="matrix", label=t("Matrix"), bg="#000000", surface="#030A03", text="#33FF66", muted="#1E9C40",
        border="#0F4A1E", header="#061406", accent="#33FF66", accent_text="#000000", highlight="#B6FFC8",
        link="#7CFF9E", ok=("#0B3A16", "#66FF8A"), ko=("#1A1A1A", "#7FB08A"), na=("#0A0F0A", "#5A6B5A"),
        green=("#0B3A16", "#66FF8A"), orange=("#102810", "#B6FFC8"), red=("#1A1A1A", "#7FB08A"),
        error=("#0B200B", "#B6FFC8"), success=("#0B3A16", "#66FF8A"), info=("#061406", "#33FF66"),
        tooltip=("#33FF66", "#000000"), font=("Consolas", 10), mono=("Consolas", 10),
        chart=("#33FF66", "#B6FFC8", "#1E9C40", "#7CFF9E", "#0F7A2E", "#D8FFE2", "#5ACC77"),
        accent2="#B6FFC8", selection="#0B3A16",
    ),
}


def get_theme(key: str) -> Theme:
    return THEMES.get(key, THEMES["default"])


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
    # Window header (logo, tabs, badges) and the rounded cards holding filters and tables.
    style.configure("Header.TFrame", background=theme.bg)
    style.configure("Header.TLabel", background=theme.bg, foreground=theme.text)
    style.configure("HeaderMuted.TLabel", background=theme.bg, foreground=theme.muted)
    style.configure("Card.TFrame", background=theme.surface, bordercolor=theme.border, borderwidth=border,
                    relief=theme.relief if theme.relief == "raised" else "solid")
    # Pages of the main notebook: the tabs are drawn in the header (TabBar), not by ttk.
    style.layout("Pages.TNotebook.Tab", [])
    style.layout("Pages.TNotebook", [("Notebook.client", {"sticky": "nswe"})])
    style.configure("Pages.TNotebook", background=theme.bg, borderwidth=0, tabmargins=0)
    style.configure("TLabel", background=theme.bg, foreground=theme.text)
    style.configure("Bar.TLabel", background=theme.surface, foreground=theme.text)
    style.configure("Muted.TLabel", background=theme.bg, foreground=theme.muted)
    style.configure("BarMuted.TLabel", background=theme.surface, foreground=theme.muted)
    style.configure("Title.TLabel", background=theme.bg, foreground=theme.text, font=(theme.font[0], theme.font[1] + 2, "bold"))
    style.configure("Section.TLabel", background=theme.surface, foreground=theme.text, font=(theme.font[0], theme.font[1] + 1, "bold"))
    # width=0: buttons as wide as their text, so the filter cards fit the window.
    style.configure("TButton", background=theme.surface, foreground=theme.text, borderwidth=border,
                    relief=theme.relief if theme.relief == "raised" else "solid", padding=(10, 4), width=0)
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
    style.configure("TSpinbox", fieldbackground=theme.surface, foreground=theme.text, background=theme.surface,
                    arrowcolor=theme.text, padding=4)
    style.configure("TCombobox", fieldbackground=theme.surface, foreground=theme.text, background=theme.surface,
                    arrowcolor=theme.text)
    style.map("TCombobox", fieldbackground=[("readonly", theme.surface)], foreground=[("readonly", theme.text)])
    style.configure("TNotebook", background=theme.bg, borderwidth=0, tabmargins=(12, 6, 12, 0))
    style.configure("TNotebook.Tab", background=theme.header, foreground=theme.muted, padding=(16, 6), borderwidth=border,
                    font=theme.font)
    style.map("TNotebook.Tab", background=[("selected", theme.surface)], foreground=[("selected", theme.text)])
    style.configure("TLabelframe", background=theme.surface, bordercolor=theme.border)
    style.configure("TLabelframe.Label", background=theme.bg, foreground=theme.text,
                    font=(theme.font[0], theme.font[1] + 1, "bold"))
    # Notification switches pointed at from a desktop notification (NO-10): the card gets the
    # "alternate" state (accent border), its title and switches the accent color.
    style.map("Card.TFrame", bordercolor=[("alternate", theme.accent)])
    style.configure("Highlight.TLabel", background=theme.surface, foreground=theme.accent,
                    font=(theme.font[0], theme.font[1] + 1, "bold"))
    style.configure("Highlight.TCheckbutton", background=theme.surface, foreground=theme.accent,
                    indicatorbackground=theme.surface, indicatorforeground=theme.accent,
                    font=(theme.font[0], theme.font[1], "bold"))
    style.map("Highlight.TCheckbutton", background=[("active", theme.surface)])
    style.configure("Horizontal.TProgressbar", background=theme.highlight, troughcolor=theme.header, bordercolor=theme.border)
    for scrollbar in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(scrollbar, background=theme.header, troughcolor=theme.bg, arrowcolor=theme.muted,
                        bordercolor=theme.bg, lightcolor=theme.header, darkcolor=theme.header)
    style.configure("TSeparator", background=theme.border)
    style.configure("Treeview", background=theme.surface, fieldbackground=theme.surface, foreground=theme.text)
    style.configure("Active.TButton", foreground=theme.accent, bordercolor=theme.accent)
    style.configure("TMenubutton", background=theme.surface, foreground=theme.text, padding=(10, 4),
                    arrowcolor=theme.text)
    style.map("TMenubutton", background=[("active", theme.header), ("disabled", theme.bg)],
              foreground=[("disabled", theme.muted)])
    style.configure("Active.TMenubutton", foreground=theme.accent, bordercolor=theme.accent)
    style.map("TNotebook.Tab", lightcolor=[("selected", theme.accent)])
    _rounded_controls(root, style, theme)

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


def _rounded_controls(root: tk.Tk, style: ttk.Style, theme: Theme) -> None:
    """Rounded, anti-aliased buttons, segments and fields with hover / pressed states.

    Only for the flat themes with rounded corners; Windows 95 keeps its bevels
    and Matrix its square terminal look (5.2).
    """
    for name in ROUNDED_STYLES:
        if name not in _CLAM_LAYOUTS:
            try:
                _CLAM_LAYOUTS[name] = style.layout(name)
            except tk.TclError:  # derived style (e.g. Accent.TButton) without a layout of its own
                _CLAM_LAYOUTS[name] = style.layout(name.split(".", 1)[1])
    if theme.relief == "raised" or not theme.radius:
        for name, layout in _CLAM_LAYOUTS.items():
            style.layout(name, layout)  # type: ignore[arg-type]
        return
    images = _IMAGES.get(theme.key)
    if images is None:
        images = _IMAGES[theme.key] = _make_images(root, theme)
        _create_elements(style, theme.key, images)
    key = theme.key
    pad = (12, 5)

    def button(element: str) -> list[tuple[str, dict[str, object]]]:
        return [(f"{key}.{element}", {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})]

    style.layout("TButton", button("button"))
    style.layout("Accent.TButton", button("accent"))
    style.layout("Card.TFrame", [(f"{key}.card", {"sticky": "nsew"})])
    style.layout("Active.TButton", button("active"))
    style.layout("Toolbutton", [(f"{key}.segment", {"sticky": "nsew", "children": [
        ("Toolbutton.padding", {"sticky": "nsew", "children": [("Toolbutton.label", {"sticky": "nsew"})]})]})])
    style.layout("TEntry", [(f"{key}.field", {"sticky": "nsew", "children": [
        ("Entry.padding", {"sticky": "nsew", "children": [("Entry.textarea", {"sticky": "nsew"})]})]})])
    for name, element in (("TMenubutton", "button"), ("Active.TMenubutton", "active")):
        style.layout(name, [(f"{key}.{element}", {"sticky": "nsew", "children": [
            ("Menubutton.padding", {"sticky": "nsew", "children": [("Menubutton.label", {"sticky": "w"})]})]})])
    for name in ("TButton", "Active.TButton", "Toolbutton", "TMenubutton", "Active.TMenubutton"):
        style.configure(name, padding=pad, background=theme.header)
    style.configure("Accent.TButton", padding=pad, background=theme.accent)
    style.map("TButton", background=[], foreground=[("disabled", theme.muted)])
    style.map("Accent.TButton", background=[], foreground=[("disabled", theme.muted)])
    style.map("Toolbutton", background=[], foreground=[("selected", theme.text), ("disabled", theme.muted)])
    style.map("TMenubutton", background=[], foreground=[("disabled", theme.muted)])
    style.configure("TEntry", fieldbackground=theme.bg, padding=(8, 4))
    # Main tabs: quiet text, a soft hover, the selected one lifted with an accent bar underneath.
    style.layout("TNotebook.Tab", [(f"{key}.tab", {"sticky": "nsew", "children": [
        ("Notebook.padding", {"side": "top", "sticky": "nsew", "children": [
            ("Notebook.label", {"side": "top", "sticky": ""})]})]})])
    style.configure("TNotebook", background=theme.bg, bordercolor=theme.bg, lightcolor=theme.bg,
                    darkcolor=theme.bg, tabmargins=(12, 8, 12, 0))
    style.configure("TNotebook.Tab", padding=(18, 8), foreground=theme.muted,
                    font=(theme.font[0], theme.font[1] + 1))
    style.map("TNotebook.Tab", foreground=[("selected", theme.text), ("active", theme.text)],
              background=[], lightcolor=[], expand=[])


def _make_images(root: tk.Tk, theme: Theme) -> dict[str, tk.PhotoImage]:
    """Every state of every rounded control of a theme, as PhotoImages."""
    # Stretchable middle well wider than the corners: Tk tiles it to fill each control, and a
    # 2-pixel middle meant hundreds of alpha blits per widget, so a tab switch took over a second.
    size, r = 2 * (CONTROL_RADIUS + 2) + SLICE, CONTROL_RADIUS
    plain, hover = theme.header, blend(theme.header, theme.accent, 0.14)
    pressed = blend(theme.header, theme.accent, 0.28)
    specs = {
        "button": (plain, theme.border, None),
        "button.hover": (hover, blend(theme.border, theme.accent, 0.5), None),
        "button.pressed": (pressed, theme.accent, None),
        "button.disabled": (theme.bg, theme.border, None),
        "accent": (theme.accent, theme.accent, None),
        "accent.hover": (theme.highlight, theme.highlight, None),
        "accent.pressed": (blend(theme.accent, theme.bg, 0.25), blend(theme.accent, theme.bg, 0.25), None),
        "active": (plain, theme.accent, None),
        "active.hover": (hover, theme.accent, None),
        "segment": (theme.bg, theme.border, None),
        "segment.hover": (plain, theme.border, None),
        "segment.selected": (plain, theme.border, theme.accent),
        "tab": (theme.bg, theme.bg, None),
        "tab.hover": (theme.header, theme.header, None),
        "tab.selected": (theme.surface, theme.border, theme.accent),
        "field": (theme.bg, theme.border, None),
        "field.focus": (theme.bg, theme.accent, None),
        "card": (theme.surface, theme.border, None),
        "card.highlight": (theme.surface, theme.accent, None),
    }
    return {name: tk.PhotoImage(master=root, data=base64.b64encode(rounded_png(size, r, fill, line, underline=under)))
            for name, (fill, line, under) in specs.items()}


def _create_elements(style: ttk.Style, key: str, images: dict[str, tk.PhotoImage]) -> None:
    border = CONTROL_RADIUS + 2
    # border = slices kept intact when stretched; padding = room inside, the style adds its own.
    # width / height: minimum size of the control, independent of the (wide) image size.
    minimum = 2 * border + 2
    options = {"border": border, "padding": (4, 2), "sticky": "nsew", "width": minimum, "height": minimum}
    style.element_create(f"{key}.button", "image", images["button"], ("pressed", images["button.pressed"]),
                         ("active", images["button.hover"]), ("disabled", images["button.disabled"]), **options)
    style.element_create(f"{key}.accent", "image", images["accent"], ("pressed", images["accent.pressed"]),
                         ("active", images["accent.hover"]), ("disabled", images["button.disabled"]), **options)
    style.element_create(f"{key}.active", "image", images["active"], ("pressed", images["button.pressed"]),
                         ("active", images["active.hover"]), ("disabled", images["button.disabled"]), **options)
    style.element_create(f"{key}.segment", "image", images["segment"], ("selected", images["segment.selected"]),
                         ("active", images["segment.hover"]), ("disabled", images["button.disabled"]), **options)
    style.element_create(f"{key}.field", "image", images["field"], ("focus", images["field.focus"]), **options)
    style.element_create(f"{key}.card", "image", images["card"], ("alternate", images["card.highlight"]), **options)
    style.element_create(f"{key}.tab", "image", images["tab"], ("selected", images["tab.selected"]),
                         ("active", images["tab.hover"]), **options)
