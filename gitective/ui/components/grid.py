"""Custom table drawn on a Canvas: colored cells, sortable headers, tooltips."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from gitective.shared.i18n import t
from gitective.ui.components.gauge import draw_gauge, gauge_width
from gitective.ui.themes import Theme
from gitective.ui.components.widgets import Tooltip

ROW_HEIGHT = 34
HEADER_HEIGHT = 38
MIN_WIDTH = 40
GRIP = 5  # px on each side of a header border that start a resize
TITLE_PAD = 26  # room around a header title, including the sort arrow
TITLE_MAX = 170  # automatic width given to a long title: beyond, it is cut and shown whole on hover
PAD = 10
GAUGE_HEIGHT = 11
STATUS_TEXT = {"ok": "OK", "ko": "KO", "na": "N/A"}

Row = dict[str, Any]


@dataclass(frozen=True)
class Column:
    """Column definition.

    kind: 'text', 'mono', 'link' (value = (text, url)), 'status'
    (value = (status, detail)), 'score' (value = (text, level)),
    'tip' (value = (text, tooltip shown on hover)),
    'avatar' (value = (PhotoImage | None, initials, color, name)),
    'people' (value = (includes the user, other names): "Moi" first, in the accent color),
    'flag' (value = (text, warning): warning color and "≠" when the warning is set, tooltip = warning),
    'dot' (value = True: small accent dot, e.g. a new MR),
    'links' (value = [(text, url, tooltip)]: several links in one cell, e.g. the MRs of a branch),
    'pill' (value = (text, (background, foreground)): colored label, e.g. a branch state).

    Row keys starting with "_" style the whole row: "_muted" (dimmed text),
    "_tag" (label drawn before the link text: BROUILLON, or the SHA a search found), "_selected".
    """

    key: str
    title: str
    width: int  # minimum width needed by the cell content
    kind: str = "text"
    stretch: bool = False
    align: str = "w"
    sortable: bool = True


class DataGrid(ttk.Frame):
    """Read-only grid with a fixed header and a scrollable body."""

    def __init__(
        self,
        master: tk.Misc,
        columns: Sequence[Column],
        get_theme: Callable[[], Theme],
        on_sort: Callable[[str], None] | None = None,
        on_link: Callable[[str], None] | None = None,
        empty_text: str = t("Aucune donnée"),
        widths: dict[str, int] | None = None,
        on_widths_changed: Callable[[dict[str, int]], None] | None = None,
        on_select: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._on_select = on_select
        self.columns = list(columns)
        self._get_theme = get_theme
        self._on_sort = on_sort
        self._on_link = on_link
        self._empty_text = empty_text
        self._rows: list[Row] = []
        self._sort_key: str | None = None
        self._ascending = True
        self._x: list[tuple[int, int]] = []
        # Clickable parts of 'links' cells: (row index, column key) → [(x0, x1, url, tooltip)].
        self._spans: dict[tuple[int, str], list[tuple[float, float, str, str]]] = {}
        self._row_index = 0
        # Texts cut with an ellipsis: (row index, column key) → whole text, shown on hover; row -1 = header.
        self._cut: dict[tuple[int, str], str] = {}
        self._cell: tuple[int, str] | None = None
        # Widths set by the user (dragged), by column key; saved in config.json.
        self._user_widths: dict[str, int] = dict(widths or {})
        self._on_widths_changed = on_widths_changed
        self._drag: tuple[int, float, int] | None = None  # (column index, start x, start width)
        self.header = tk.Canvas(self, height=HEADER_HEIGHT, highlightthickness=0, borderwidth=0)
        self.body = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.header.self_themed = True  # type: ignore[attr-defined]
        self.body.self_themed = True  # type: ignore[attr-defined]
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.body.yview)
        self.hscrollbar = ttk.Scrollbar(self, orient="horizontal", command=self._xview)
        self.body.configure(yscrollcommand=self.scrollbar.set, xscrollcommand=self._on_xscroll)
        self.header.grid(row=0, column=0, sticky="ew")
        self.body.grid(row=1, column=0, sticky="nsew")
        self.scrollbar.grid(row=1, column=1, sticky="ns")
        self._content_width = 0
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._tooltip = Tooltip(self, get_theme)
        self.body.bind("<Configure>", lambda e: self.redraw())
        self.body.bind("<Button-1>", self._on_click)
        self.body.bind("<Motion>", self._on_motion)
        self.body.bind("<Leave>", lambda e: self._tooltip.hide())
        self.body.bind("<MouseWheel>", lambda e: self.body.yview_scroll(int(-e.delta / 120) or -1, "units"))
        self.body.bind("<Button-4>", lambda e: self.body.yview_scroll(-1, "units"))
        self.body.bind("<Button-5>", lambda e: self.body.yview_scroll(1, "units"))
        self.body.bind("<Shift-MouseWheel>", lambda e: self._xview("scroll", str(int(-e.delta / 120) or -1), "units"))
        self.header.bind("<Button-1>", self._on_header_press)
        self.header.bind("<B1-Motion>", self._on_header_drag)
        self.header.bind("<ButtonRelease-1>", self._on_header_release)
        self.header.bind("<Double-Button-1>", self._on_header_double)
        self.header.bind("<Motion>", self._on_header_motion)
        self.header.bind("<Leave>", lambda e: self._tooltip.hide())

    # -------------------------------------------------------------- Public API

    def set_columns(self, columns: Sequence[Column]) -> None:
        """Replace the columns (custom rules added or removed)."""
        self.columns = list(columns)
        self.redraw()

    def set_rows(self, rows: Sequence[Row], keep_scroll: bool = False) -> None:
        self._rows = list(rows)
        if not keep_scroll:
            self.body.yview_moveto(0)
        self.redraw()

    def see(self, index: int) -> None:
        """Scroll so that a row is visible (keyboard navigation)."""
        total = max(1, len(self._rows) * ROW_HEIGHT)
        top, bottom = self.body.yview()
        y0, y1 = index * ROW_HEIGHT / total, (index + 1) * ROW_HEIGHT / total
        if y0 < top:
            self.body.yview_moveto(y0)
        elif y1 > bottom:
            self.body.yview_moveto(max(0.0, y1 - (bottom - top)))

    def set_sort(self, key: str | None, ascending: bool) -> None:
        """Show the sort arrow on a column header."""
        self._sort_key = key
        self._ascending = ascending
        self.redraw()

    # ---------------------------------------------------------------- Drawing

    def auto_width(self, col: Column, bold: tkfont.Font | None = None) -> int:
        """Width showing the whole title on one line, never below the content minimum."""
        if bold is None:
            theme = self._get_theme()
            bold = tkfont.Font(font=(theme.font[0], theme.font[1], "bold"))
        return max(col.width, min(bold.measure(col.title) + TITLE_PAD, TITLE_MAX))

    def _layout(self, width: int, bold: tkfont.Font) -> None:
        """Compute column positions.

        Each column uses the width set by the user, else its automatic width.
        Stretch columns not resized by the user share the spare space; a
        table wider than the view scrolls horizontally.
        """
        base = [self._user_widths.get(c.key) or self.auto_width(c, bold) for c in self.columns]
        stretchers = [i for i, c in enumerate(self.columns) if c.stretch and c.key not in self._user_widths]
        spare = max(0, width - sum(base) - 2 * PAD)
        extra = spare // len(stretchers) if stretchers else 0
        x = PAD
        self._x = []
        for index, w in enumerate(base):
            w += extra if index in stretchers else 0
            self._x.append((x, x + w))
            x += w
        self._content_width = x + PAD

    def redraw(self) -> None:
        """Redraw header and rows with the current theme, widths and sort."""
        theme = self._get_theme()
        fonts = (tkfont.Font(font=theme.font), tkfont.Font(font=(theme.font[0], theme.font[1], "bold")),
                 tkfont.Font(font=theme.mono))
        view_width = max(self.body.winfo_width(), 200)
        self._layout(view_width, fonts[1])
        width = max(view_width, self._content_width)
        self._toggle_hscroll(self._content_width > view_width)
        self._draw_header(theme, fonts[1], width)
        self._draw_rows(theme, fonts, width)

    def _draw_header(self, theme: Theme, bold: tkfont.Font, width: int) -> None:
        self.header.configure(background=theme.header)
        self.header.delete("all")
        self._cut = {k: v for k, v in self._cut.items() if k[0] != -1}
        for col, (x0, x1) in zip(self.columns, self._x):
            title = col.title
            if col.key == self._sort_key:
                title += " ▲" if self._ascending else " ▼"
            self._cell = (-1, col.key)
            self._text(self.header, x0, x1, HEADER_HEIGHT / 2, title, bold, theme.text, col.align)
            # Column separator, also the handle for resizing.
            self.header.create_line(x1, 8, x1, HEADER_HEIGHT - 8, fill=theme.border)
        self.header.create_line(0, HEADER_HEIGHT - 1, width, HEADER_HEIGHT - 1, fill=theme.border)
        self.header.configure(scrollregion=(0, 0, width, HEADER_HEIGHT))

    def _draw_rows(self, theme: Theme, fonts: tuple[tkfont.Font, tkfont.Font, tkfont.Font], width: int) -> None:
        font, bold, mono = fonts
        self.body.configure(background=theme.surface)
        self.body.delete("all")
        self._spans = {}
        self._cut = {k: v for k, v in self._cut.items() if k[0] == -1}
        if not self._rows:
            self.body.create_text(width / 2, 40, text=self._empty_text, fill=theme.muted, font=font)
            self.body.configure(scrollregion=(0, 0, width, 80))
            return
        for index, row in enumerate(self._rows):
            top = index * ROW_HEIGHT
            if row.get("_selected"):
                self.body.create_rectangle(0, top, width, top + ROW_HEIGHT - 1, fill=theme.selected_row, outline="")
                self.body.create_rectangle(0, top, 3, top + ROW_HEIGHT - 1, fill=theme.accent, outline="")
            self._row_index = index
            for col, (x0, x1) in zip(self.columns, self._x):
                self._cell = (index, col.key)
                self._draw_cell(col, row.get(col.key), x0, x1, top + ROW_HEIGHT / 2, theme, fonts, row)
            self.body.create_line(0, top + ROW_HEIGHT - 1, width, top + ROW_HEIGHT - 1, fill=theme.header)
        self.body.configure(scrollregion=(0, 0, width, len(self._rows) * ROW_HEIGHT))

    def _draw_cell(self, col: Column, value: Any, x0: int, x1: int, mid: float, theme: Theme,
                   fonts: tuple[tkfont.Font, tkfont.Font, tkfont.Font], row: Row | None = None) -> None:
        font, bold, mono = fonts
        if value in (None, ""):
            return
        row = row or {}
        text_color = theme.muted if row.get("_muted") else theme.text
        if col.kind == "link" and row.get("_tag"):
            tag = row["_tag"]
            muted = bool(row.get("_muted"))
            small = tkfont.Font(font=(theme.font[0], max(7, theme.font[1] - 2), "bold"))
            w = small.measure(tag) + 10
            bg, fg = theme.na if muted else theme.info
            self.body.create_rectangle(x0, mid - 9, x0 + w, mid + 9, fill=bg, outline=bg)
            self.body.create_text(x0 + w / 2, mid, text=tag, fill=fg, font=small)
            self._text(self.body, x0 + w + 6, x1, mid, value[0], font, theme.muted if muted else theme.link,
                       col.align, underline=True)
            return
        if col.kind == "people":
            includes_me, others = value
            x = x0
            if includes_me:
                item = self.body.create_text(x, mid, text=t("Moi"), fill=theme.accent, font=bold, anchor="w")
                bbox = self.body.bbox(item)
                x = (bbox[2] if bbox else x + 30)
                if others:
                    self._text(self.body, x, x1, mid, ", " + others, font, text_color, "w")
            else:
                self._text(self.body, x0, x1, mid, others, font, text_color, col.align)
            return
        if col.kind == "flag":
            text, warning = value
            if warning:
                self._text(self.body, x0, x1, mid, "≠ " + text, bold, theme.orange[1], col.align)
            else:
                self._text(self.body, x0, x1, mid, text, font, text_color, col.align)
            return
        if col.kind == "dot":
            cx = (x0 + x1 - 8) / 2 if col.align == "center" else x0 + 6
            self.body.create_oval(cx - 5, mid - 5, cx + 5, mid + 5, fill=theme.second, outline="")
            return
        if col.kind == "links":
            self._links(col, value, x0, x1, mid, font, theme.muted if row.get("_muted") else theme.link)
            return
        if col.kind == "pill":
            self._pill(x0, x1, mid, value[0], value[1], bold, align="w")
            return
        if col.kind == "status":
            self._pill(x0, x1, mid, STATUS_TEXT.get(value[0], value[0]), theme.status_colors(value[0]), bold)
        elif col.kind == "score":
            gauge = (value[1], theme.empty_bar) if theme.shapes else None
            self._pill(x0, x1, mid, value[0], theme.level_colors(value[1]), bold, minimum=52, gauge=gauge)
        elif col.kind == "link":
            self._text(self.body, x0, x1, mid, value[0], font, theme.muted if row.get("_muted") else theme.link,
                       col.align, underline=True)
        elif col.kind == "avatar":
            self._avatar(x0, x1, mid, value, font, bold, theme)
        elif col.kind == "tip":
            self._text(self.body, x0, x1, mid, value[0], font, text_color, col.align)
        else:
            self._text(self.body, x0, x1, mid, str(value), mono if col.kind == "mono" else font, text_color, col.align)

    # ------------------------------------------------------- Horizontal scroll

    def _xview(self, *args: str) -> None:
        self.body.xview(*args)
        self.header.xview(*args)

    def _on_xscroll(self, first: str, last: str) -> None:
        self.hscrollbar.set(first, last)
        self.header.xview_moveto(first)

    def _toggle_hscroll(self, needed: bool) -> None:
        if needed and not self.hscrollbar.winfo_ismapped():
            self.hscrollbar.grid(row=2, column=0, sticky="ew")
        elif not needed and self.hscrollbar.winfo_ismapped():
            self.hscrollbar.grid_remove()
            self._xview("moveto", "0")

    def _text(self, canvas: tk.Canvas, x0: int, x1: int, y: float, text: str, font: tkfont.Font,
              color: str, align: str, underline: bool = False) -> None:
        room = x1 - x0 - 8
        shown = ellipsize(text, font, room)
        if shown != text and self._cell is not None:
            self._cut[self._cell] = text
        anchor = {"w": "w", "center": "center", "e": "e"}[align]
        x = {"w": x0, "center": (x0 + x1) / 2, "e": x1 - 8}[align]
        item = canvas.create_text(x, y, text=shown, fill=color, font=font, anchor=anchor)
        if underline:
            bbox = canvas.bbox(item)
            if bbox:
                canvas.create_line(bbox[0], bbox[3] - 1, bbox[2], bbox[3] - 1, fill=color)

    def _links(self, col: Column, value: list[tuple[str, str, str]], x0: int, x1: int, mid: float,
               font: tkfont.Font, color: str) -> None:
        """Several underlined links separated by commas; each keeps its own click area."""
        x, spans = float(x0), []
        for index, (text, url, tip) in enumerate(value):
            label = text + ("," if index < len(value) - 1 else "")
            width = font.measure(text)
            if x + width > x1 - 8:
                self.body.create_text(x, mid, text="…", fill=color, font=font, anchor="w")
                break
            self.body.create_text(x, mid, text=label, fill=color, font=font, anchor="w")
            self.body.create_line(x, mid + 8, x + width, mid + 8, fill=color)
            spans.append((x, x + width, url, tip))
            x += font.measure(label + " ")
        self._spans[(self._row_index, col.key)] = spans

    def _span_at(self, index: int, col: Column, x: float) -> tuple[float, float, str, str] | None:
        return next((s for s in self._spans.get((index, col.key), []) if s[0] <= x <= s[1]), None)

    def _pill(self, x0: int, x1: int, y: float, text: str, colors: tuple[str, str], font: tkfont.Font,
              minimum: int = 44, align: str = "center", gauge: tuple[str, str] | None = None) -> None:
        """Colored badge; `gauge` = (score level, empty bar color) adds the 3-bar gauge before the text (TH-05)."""
        extra = gauge_width(GAUGE_HEIGHT) + 6 if gauge else 0
        w = max(minimum, font.measure(text) + 14 + extra)
        cx = x0 + w / 2 if align == "w" else (x0 + x1 - 8) / 2
        self.body.create_rectangle(cx - w / 2, y - 11, cx + w / 2, y + 11, fill=colors[0], outline=colors[0])
        if gauge:
            left = cx - (font.measure(text) + extra) / 2
            draw_gauge(self.body, left, y, gauge[0], colors[1], gauge[1], GAUGE_HEIGHT)
            self.body.create_text(left + extra, y, text=text, fill=colors[1], font=font, anchor="w")
        else:
            self.body.create_text(cx, y, text=text, fill=colors[1], font=font)

    def _avatar(self, x0: int, x1: int, y: float, value: tuple[Any, str, str, str], font: tkfont.Font,
                bold: tkfont.Font, theme: Theme) -> None:
        image, initials, color, name = value
        if image is not None:
            self.body.create_image(x0 + 13, y, image=image)
        else:
            self.body.create_oval(x0, y - 13, x0 + 26, y + 13, fill=color, outline=color)
            self.body.create_text(x0 + 13, y, text=initials, fill="#FFFFFF", font=bold)
        self._text(self.body, x0 + 36, x1, y, name, font, theme.text, "w")

    # ---------------------------------------------------------------- Events

    def _row_at(self, event: tk.Event) -> int | None:
        index = int(self.body.canvasy(event.y) // ROW_HEIGHT)
        return index if 0 <= index < len(self._rows) else None

    def _hit(self, event: tk.Event) -> tuple[Row, Column] | None:
        index = self._row_at(event)
        if index is None:
            return None
        x = self.body.canvasx(event.x)
        for col, (x0, x1) in zip(self.columns, self._x):
            if x0 <= x < x1:
                return self._rows[index], col
        return None

    def _on_click(self, event: tk.Event) -> None:
        """A click on a link opens it; anywhere else on a row selects the row (DE-01)."""
        hit = self._hit(event)
        if hit and hit[1].kind == "link" and self._on_link:
            value = hit[0].get(hit[1].key)
            if value and value[1]:
                self._on_link(value[1])
                return
        if hit and hit[1].kind == "links" and self._on_link:
            span = self._span_at(self._row_at(event) or 0, hit[1], self.body.canvasx(event.x))
            if span:
                self._on_link(span[2])
                return
        index = self._row_at(event)
        if index is not None and self._on_select:
            self.body.focus_set()
            self._on_select(index)

    def _on_motion(self, event: tk.Event) -> None:
        hit = self._hit(event)
        cursor = ""
        tip = ""
        if hit:
            row, col = hit
            value = row.get(col.key)
            if col.kind == "link" and value:
                cursor = "hand2"
            if col.kind == "links" and value:
                span = self._span_at(self._row_at(event) or 0, col, self.body.canvasx(event.x))
                if span:
                    cursor, tip = "hand2", span[3]
            if col.kind == "status" and value and value[0] in ("ko", "na") and value[1]:
                tip = value[1]
            if col.kind in ("tip", "flag") and value and value[1]:
                tip = value[1]
            index = self._row_at(event)
            if not tip and index is not None:
                tip = self._cut.get((index, col.key), "")
        self.body.configure(cursor=cursor)
        if tip:
            self._tooltip.show(event.x_root, event.y_root, tip)
        else:
            self._tooltip.hide()

    # ------------------------------------------------------- Header: sort & resize

    def _border_at(self, x: float) -> int | None:
        """Index of the column whose right border is under x, if any."""
        for index, (_, x1) in enumerate(self._x):
            if abs(x - x1) <= GRIP:
                return index
        return None

    def _on_header_motion(self, event: tk.Event) -> None:
        if self._drag is None:
            x = self.header.canvasx(event.x)
            near = self._border_at(x) is not None
            self.header.configure(cursor="sb_h_double_arrow" if near else "")
            col = next((c for c, (x0, x1) in zip(self.columns, self._x) if x0 <= x < x1), None)
            title = self._cut.get((-1, col.key), "") if col is not None and not near else ""
            if title:
                self._tooltip.show(event.x_root, event.y_root, title)
            else:
                self._tooltip.hide()

    def _on_header_press(self, event: tk.Event) -> None:
        x = self.header.canvasx(event.x)
        border = self._border_at(x)
        if border is not None:
            x0, x1 = self._x[border]
            self._drag = (border, x, x1 - x0)
            return
        for col, (x0, x1) in zip(self.columns, self._x):
            if x0 <= x < x1 and col.sortable and self._on_sort:
                self._on_sort(col.key)
                return

    def _on_header_drag(self, event: tk.Event) -> None:
        if self._drag is None:
            return
        index, start_x, start_width = self._drag
        new_width = max(MIN_WIDTH, int(start_width + self.header.canvasx(event.x) - start_x))
        self._user_widths[self.columns[index].key] = new_width
        self.redraw()

    def _on_header_release(self, _event: tk.Event) -> None:
        if self._drag is not None:
            index, _, start_width = self._drag
            self._drag = None
            if self._user_widths.get(self.columns[index].key, start_width) != start_width:
                self._widths_changed()

    def _on_header_double(self, event: tk.Event) -> None:
        """Double-click on a border: back to the automatic width."""
        border = self._border_at(self.header.canvasx(event.x))
        if border is not None:
            self._drag = None
            self._user_widths.pop(self.columns[border].key, None)
            self.redraw()
            self._widths_changed()

    def _widths_changed(self) -> None:
        if self._on_widths_changed:
            self._on_widths_changed(dict(self._user_widths))


def ellipsize(text: str, font: tkfont.Font, room: int) -> str:
    """Cut text with an ellipsis so it fits in room pixels."""
    if room <= 0 or font.measure(text) <= room:
        return text
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if font.measure(text[:mid] + "…") <= room:
            low = mid
        else:
            high = mid - 1
    return text[:low] + "…"


def sort_rows(rows: list[Any], key: Callable[[Any], Any], ascending: bool) -> list[Any]:
    """Stable sort that keeps empty values (None) at the end."""
    present = [r for r in rows if key(r) is not None]
    missing = [r for r in rows if key(r) is None]
    return sorted(present, key=key, reverse=not ascending) + missing
