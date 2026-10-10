"""Custom table drawn on a Canvas: colored cells, sortable headers, tooltips."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from gitective.ui.themes import Theme
from gitective.ui.widgets import Tooltip

ROW_HEIGHT = 34
HEADER_HEIGHT = 38
MIN_WIDTH = 40
GRIP = 5  # px on each side of a header border that start a resize
TITLE_PAD = 26  # room around a header title, including the sort arrow
PAD = 10
STATUS_TEXT = {"ok": "OK", "ko": "KO", "na": "N/A"}

Row = dict[str, Any]


@dataclass(frozen=True)
class Column:
    """Column definition.

    kind: 'text', 'mono', 'link' (value = (text, url)), 'status'
    (value = (status, detail)), 'score' (value = (text, level)),
    'avatar' (value = (PhotoImage | None, initials, color, name)).
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
        empty_text: str = "Aucune donnée",
        widths: dict[str, int] | None = None,
        on_widths_changed: Callable[[dict[str, int]], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.columns = list(columns)
        self._get_theme = get_theme
        self._on_sort = on_sort
        self._on_link = on_link
        self._empty_text = empty_text
        self._rows: list[Row] = []
        self._sort_key: str | None = None
        self._ascending = True
        self._x: list[tuple[int, int]] = []
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

    # -------------------------------------------------------------- Public API

    def set_columns(self, columns: Sequence[Column]) -> None:
        """Replace the columns (custom rules added or removed)."""
        self.columns = list(columns)
        self.redraw()

    def set_rows(self, rows: Sequence[Row]) -> None:
        self._rows = list(rows)
        self.body.yview_moveto(0)
        self.redraw()

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
        return max(col.width, bold.measure(col.title) + TITLE_PAD)

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
        theme = self._get_theme()
        font = tkfont.Font(font=theme.font)
        bold = tkfont.Font(font=(theme.font[0], theme.font[1], "bold"))
        mono = tkfont.Font(font=theme.mono)
        view_width = max(self.body.winfo_width(), 200)
        self._layout(view_width, bold)
        width = max(view_width, self._content_width)
        self._toggle_hscroll(self._content_width > view_width)
        self.header.configure(background=theme.header)
        self.body.configure(background=theme.surface)
        self.header.delete("all")
        self.body.delete("all")

        for col, (x0, x1) in zip(self.columns, self._x):
            title = col.title
            if col.key == self._sort_key:
                title += " ▲" if self._ascending else " ▼"
            self._text(self.header, x0, x1, HEADER_HEIGHT / 2, title, bold, theme.text, col.align)
            # Column separator, also the handle for resizing.
            self.header.create_line(x1, 8, x1, HEADER_HEIGHT - 8, fill=theme.border)
        self.header.create_line(0, HEADER_HEIGHT - 1, width, HEADER_HEIGHT - 1, fill=theme.border)

        if not self._rows:
            self.body.create_text(width / 2, 40, text=self._empty_text, fill=theme.muted, font=font)
            self.body.configure(scrollregion=(0, 0, width, 80))
            self.header.configure(scrollregion=(0, 0, width, HEADER_HEIGHT))
            return

        for index, row in enumerate(self._rows):
            top = index * ROW_HEIGHT
            mid = top + ROW_HEIGHT / 2
            for col, (x0, x1) in zip(self.columns, self._x):
                value = row.get(col.key)
                if col.kind == "status" and value:
                    self._pill(x0, x1, mid, STATUS_TEXT.get(value[0], value[0]), theme.status_colors(value[0]), bold)
                elif col.kind == "score" and value:
                    self._pill(x0, x1, mid, value[0], theme.level_colors(value[1]), bold, minimum=52)
                elif col.kind == "link" and value:
                    self._text(self.body, x0, x1, mid, value[0], font, theme.link, col.align, underline=True)
                elif col.kind == "avatar" and value:
                    self._avatar(x0, x1, mid, value, font, bold, theme)
                elif value not in (None, ""):
                    self._text(self.body, x0, x1, mid, str(value), mono if col.kind == "mono" else font,
                               theme.text, col.align)
            self.body.create_line(0, top + ROW_HEIGHT - 1, width, top + ROW_HEIGHT - 1, fill=theme.header)
        self.body.configure(scrollregion=(0, 0, width, len(self._rows) * ROW_HEIGHT))
        self.header.configure(scrollregion=(0, 0, width, HEADER_HEIGHT))

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
              color: str, align: str, underline: bool = False, wrap: bool = False) -> None:
        room = x1 - x0 - 8
        if wrap and font.measure(text) > room:
            x = {"w": x0, "center": (x0 + x1) / 2, "e": x1 - 8}[align]
            canvas.create_text(x, y, text=text, fill=color, font=font, anchor={"w": "w", "center": "center", "e": "e"}[align],
                               width=room, justify={"w": "left", "center": "center", "e": "right"}[align])
            return
        shown = _ellipsize(text, font, room)
        anchor = {"w": "w", "center": "center", "e": "e"}[align]
        x = {"w": x0, "center": (x0 + x1) / 2, "e": x1 - 8}[align]
        item = canvas.create_text(x, y, text=shown, fill=color, font=font, anchor=anchor)
        if underline:
            bbox = canvas.bbox(item)
            if bbox:
                canvas.create_line(bbox[0], bbox[3] - 1, bbox[2], bbox[3] - 1, fill=color)

    def _pill(self, x0: int, x1: int, y: float, text: str, colors: tuple[str, str], font: tkfont.Font,
              minimum: int = 44) -> None:
        w = max(minimum, font.measure(text) + 14)
        cx = (x0 + x1 - 8) / 2
        self.body.create_rectangle(cx - w / 2, y - 11, cx + w / 2, y + 11, fill=colors[0], outline=colors[0])
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

    def _hit(self, event: tk.Event) -> tuple[Row, Column] | None:
        y = self.body.canvasy(event.y)
        index = int(y // ROW_HEIGHT)
        if not 0 <= index < len(self._rows):
            return None
        x = self.body.canvasx(event.x)
        for col, (x0, x1) in zip(self.columns, self._x):
            if x0 <= x < x1:
                return self._rows[index], col
        return None

    def _on_click(self, event: tk.Event) -> None:
        hit = self._hit(event)
        if hit and hit[1].kind == "link" and self._on_link:
            value = hit[0].get(hit[1].key)
            if value and value[1]:
                self._on_link(value[1])

    def _on_motion(self, event: tk.Event) -> None:
        hit = self._hit(event)
        cursor = ""
        tip = ""
        if hit:
            row, col = hit
            value = row.get(col.key)
            if col.kind == "link" and value:
                cursor = "hand2"
            if col.kind == "status" and value and value[0] in ("ko", "na") and value[1]:
                tip = value[1]
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
            near = self._border_at(self.header.canvasx(event.x)) is not None
            self.header.configure(cursor="sb_h_double_arrow" if near else "")

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


def _ellipsize(text: str, font: tkfont.Font, room: int) -> str:
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
