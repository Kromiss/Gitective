"""Tags tab: Parcourir (tags with their message, release notes and a detail panel) and Comparer sub-tabs (section 12)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from gitective.forge.models import Tag
from gitective.repository.tags import TagRow, build_rows, first_line, visible_tags
from gitective.review.mr_filters import step_selection
from gitective.shared.dates import (
    Period,
    current_month,
    current_year,
    day_range,
    format_date,
    format_datetime,
    last_days,
    parse_date,
)
from gitective.ui.components.grid import Column, sort_rows
from gitective.ui.components.pagination import Pager
from gitective.ui.components.widgets import MultiSelect
from gitective.ui.tabs.data_tab import DataTab
from gitective.ui.tabs.tag_compare import TagCompareView
from gitective.ui.tabs.tag_detail_panel import TagDetailPanel

if TYPE_CHECKING:
    from gitective.ui.app import App

COLUMNS = [
    Column("repo", "Dépôt", 120),
    Column("tag", "Tag", 110, kind="link"),
    Column("message", "Message", 200, kind="tip", stretch=True),
    Column("notes", "Notes de release", 200, kind="tip", stretch=True),
    Column("date", "Date", 150, kind="mono"),
    Column("sha", "Commit", 84, kind="link"),
    Column("author", "Auteur du commit", 140),
]
SORT_KEYS: dict[str, Callable[[TagRow], Any]] = {
    "repo": lambda r: r.project.path.casefold(),
    "tag": lambda r: r.tag.name.casefold(),
    "message": lambda r: r.tag.message.casefold() or None,
    "notes": lambda r: r.tag.release_notes.casefold() or None,
    "date": lambda r: r.tag.committed_date,
    "sha": lambda r: r.tag.commit_sha,
    "author": lambda r: r.author.name.casefold(),
}
Key = tuple[int, str]


def _key(row: TagRow) -> Key:
    return row.project.id, row.tag.name


class TagsBrowseView(DataTab):
    """Parcourir sub-tab: lists the tags; a click on a line opens its detail panel (TG-02..TG-07)."""

    table = "tags"

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master, app, sort_key="date", ascending=False)
        self._rows: list[TagRow] = []
        self._visible: list[TagRow] = []
        self._selected: Key | None = None
        saved = app.settings.tag_filters
        self._total = saved.total
        self._from = tk.StringVar(value="" if saved.total else saved.date_from)
        self._to = tk.StringVar(value="" if saved.total else saved.date_to)

        bar = ttk.Frame(self, style="Card.TFrame", padding=(14, 12))
        bar.pack(fill="x", padx=16, pady=(12, 0))
        top = ttk.Frame(bar, style="Bar.TFrame")
        top.pack(fill="x")
        dates = ttk.Frame(bar, style="Bar.TFrame")
        dates.pack(fill="x", pady=(10, 0))
        self.repos = MultiSelect(top, "Dépôts", self._repos_changed, app.get_theme)
        self.repos.set_selected([str(r) for r in saved.repos])
        self.repos.pack(side="left")
        ttk.Label(top, text="Rechercher (nom, message, notes, SHA)", style="BarMuted.TLabel").pack(
            side="left", padx=(16, 6))
        self._search = tk.StringVar()
        self._search.trace_add("write", lambda *_: self._apply_view(reset_page=True))
        ttk.Entry(top, textvariable=self._search, width=28).pack(side="left")
        self.refresh_button(top).pack(side="right")
        for label, var, pad in (("Du", self._from, 0), ("au", self._to, 8)):
            ttk.Label(dates, text=label, style="BarMuted.TLabel").pack(side="left", padx=(pad, 6))
            entry = ttk.Entry(dates, textvariable=var, width=11)
            entry.pack(side="left")
            entry.bind("<Return>", lambda e: self._apply_dates())
        ttk.Button(dates, text="Appliquer", command=self._apply_dates).pack(side="left", padx=(8, 0))
        for text, period in (("7 jours", lambda: last_days(7)), ("30 jours", lambda: last_days(30)),
                             ("Mois en cours", current_month), ("Année en cours", current_year)):
            ttk.Button(dates, text=text, command=lambda p=period: self._shortcut(p())).pack(side="left", padx=(6, 0))
        self._total_button = ttk.Button(dates, text="Total", command=self._set_total)
        self._total_button.pack(side="left", padx=(6, 0))

        # Table card on the left, detail panel on the right when a tag is selected (TG-07).
        self._split = ttk.PanedWindow(self, orient="horizontal")
        self._split.pack(fill="both", expand=True, padx=16, pady=(12, 0))
        left = ttk.Frame(self._split)
        self._split.add(left, weight=1)
        card = ttk.Frame(left, style="Card.TFrame", padding=(10, 8, 10, 10))
        card.pack(fill="both", expand=True)
        summary = ttk.Frame(card, style="Bar.TFrame", padding=(6, 2, 6, 8))
        summary.pack(fill="x")
        self._count = ttk.Label(summary, style="Section.TLabel")
        self._count.pack(side="left")
        ttk.Label(summary, text="Clic sur un tag ou un commit : ouvre GitLab · sur la ligne : détail",
                  style="BarMuted.TLabel").pack(side="right")
        self.grid_view = self.make_grid(COLUMNS, "Aucun tag pour ces filtres", links=True, master=card,
                                        on_select=self._row_selected)
        self.grid_view.pack(fill="both", expand=True)
        self.pager = Pager(left, lambda _p, _s: self._render_page(), page_size=app.filters.page_size)
        self.pager.pack(fill="x", pady=10)
        self.panel = TagDetailPanel(self._split, app, self.close_detail)
        self._split.bind("<ButtonRelease-1>", lambda e: self._panel_resized())
        body = self.grid_view.body
        body.bind("<Up>", lambda e: self._move(-1))
        body.bind("<Down>", lambda e: self._move(1))
        body.bind("<Escape>", lambda e: self.close_detail())
        self._show_period()

    @property
    def _panel_open(self) -> bool:
        return str(self.panel) in {str(p) for p in self._split.panes()}

    # ------------------------------------------------------------- Filters

    def _period(self) -> Period | None:
        if self._total:
            return None
        return day_range(parse_date(self._from.get()), parse_date(self._to.get()))

    def _save_filters(self) -> None:
        """Repositories and period are remembered (TG-04)."""
        saved = self.app.settings.tag_filters
        saved.repos = [int(k) for k in self.repos.selected]
        saved.total, saved.date_from, saved.date_to = self._total, self._from.get().strip(), self._to.get().strip()
        self.app.save_settings()

    def _apply_dates(self) -> None:
        try:
            day_range(parse_date(self._from.get()), parse_date(self._to.get()))
        except ValueError:
            self.app.notify("error", "Dates invalides : utilisez le format JJ/MM/AAAA, la date de fin après la "
                                     "date de début.")
            return
        self._total = False
        self._period_changed()

    def _shortcut(self, period: Period) -> None:
        self._from.set(format_date(period[0].date()))
        self._to.set(format_date(period[1].date()))
        self._total = False
        self._period_changed()

    def _set_total(self) -> None:
        self._total = True
        self._from.set("")
        self._to.set("")
        self._period_changed()

    def _period_changed(self) -> None:
        self._show_period()
        self._save_filters()
        self._apply_view(reset_page=True)

    def _show_period(self) -> None:
        self._total_button.configure(style="Active.TButton" if self._total else "TButton")

    def _repos_changed(self, _keys: list[str]) -> None:
        self._save_filters()
        self._apply_view(reset_page=True)

    def _people_changed(self, items: list[tuple[str, str]]) -> None:
        pass  # no author filter on this tab

    # ------------------------------------------------------------- Loading

    def reload(self) -> None:
        """Read the stored tags; the synchronisation keeps them up to date (TG-08)."""
        self.dirty = False
        if not self.app.ensure_connection():
            return
        store = self.app.store
        ids = [p.id for p in self.app.settings.projects]

        def task(_progress: Callable[[int, int], None]) -> list[tuple[int, Tag, float | None]]:
            return store.tags(ids)

        self.app.runner.run("tags", task, self._loaded, self.app.report_error)

    def _loaded(self, stored: list[tuple[int, Tag, float | None]]) -> None:
        self._rows = build_rows(stored, self.app.settings.projects, self.app.people)
        self._apply_view(reset_page=False)
        if self._panel_open and self._selected is not None:
            current = next((r for r in self._rows if _key(r) == self._selected), None)
            if current is not None:
                self.panel.show(current)

    # ---------------------------------------------------------------- View

    def _apply_view(self, reset_page: bool = False) -> None:
        try:
            period = self._period()
        except ValueError:
            period = None
        repos = [int(k) for k in self.repos.selected]
        rows = visible_tags(self._rows, repos, self._search.get(), period)
        self._visible = sort_rows(rows, SORT_KEYS[self._sort_key], self._ascending)
        self._count.configure(text=f"{len(rows)} tag(s)")
        self.pager.update_total(len(self._visible), reset=reset_page)
        self._render_page()

    def _page_rows(self) -> list[TagRow]:
        return self._visible[self.pager.slice()]

    def _render_page(self) -> None:
        rows = []
        for r in self._page_rows():
            tag = r.tag
            row: dict[str, Any] = {
                "repo": r.project.path.split("/")[-1],
                "tag": (tag.name, r.web_url),
                "message": (first_line(tag.message), tag.message),
                "notes": (first_line(tag.release_notes), tag.release_notes),
                "date": format_datetime(tag.committed_date),
                "sha": (tag.commit_sha[:8], r.commit_url),
                "author": r.author.name,
                "_selected": _key(r) == self._selected,
            }
            if r.deleted_at is not None:
                row["_muted"], row["_tag"] = True, "SUPPRIMÉ"
            rows.append(row)
        self.grid_view.set_rows(rows, keep_scroll=True)

    # ---------------------------------------------------------- Detail panel

    def _row_selected(self, index: int) -> None:
        rows = self._page_rows()
        if 0 <= index < len(rows):
            self.open_detail(rows[index])

    def open_detail(self, row: TagRow) -> None:
        """Select a tag and show it in the side panel (TG-07, same mechanics as DE-01)."""
        self._selected = _key(row)
        if not self._panel_open:
            self._split.add(self.panel, weight=0)
            self._split.update_idletasks()
            total = self._split.winfo_width()
            if total > 1:
                self._split.sashpos(0, max(300, total - self.app.settings.detail_width))
        self._render_page()
        self.panel.show(row)

    def close_detail(self) -> None:
        if self._panel_open:
            self._split.forget(self.panel)
        self._selected = None
        self._render_page()

    def _panel_resized(self) -> None:
        if self._panel_open:
            self.app.save_detail_width(self.panel.winfo_width())  # shared with the MR panel (TG-07)

    def _move(self, step: int) -> None:
        size = self.pager.page_size
        target = step_selection([_key(r) for r in self._visible], self._selected, step, size)
        if target is None:
            return
        index, page = target
        if page != self.pager.page:
            self.pager.page = page
            self.pager.update_total(len(self._visible))
        self.open_detail(self._visible[index])
        self.grid_view.see(index % size)

    def restyle(self) -> None:
        self._render_page()
        if self._panel_open:
            self.panel.render()


class TagsTab(ttk.Frame):
    """Tags tab: a switch between the Parcourir and Comparer sub-tabs, the shown one remembered (TG-01)."""

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master)
        self.app = app
        self._view = tk.StringVar(value=app.settings.tags_view)
        switch = ttk.Frame(self)
        switch.pack(fill="x", padx=16, pady=(12, 0))
        for value, text in (("browse", "Parcourir"), ("compare", "Comparer")):
            ttk.Radiobutton(switch, text=text, value=value, variable=self._view, style="Toolbutton",
                            command=self._switch).pack(side="left")
        self.browse = TagsBrowseView(self, app)
        self.compare = TagCompareView(self, app)
        self._show()

    @property
    def _current(self) -> TagsBrowseView | TagCompareView:
        return self.compare if self._view.get() == "compare" else self.browse

    @property
    def dirty(self) -> bool:
        return self._current.dirty

    @dirty.setter
    def dirty(self, value: bool) -> None:
        self.browse.dirty = self.compare.dirty = value

    def _show(self) -> None:
        shown, hidden = (self.compare, self.browse) if self._view.get() == "compare" else (self.browse, self.compare)
        hidden.pack_forget()
        shown.pack(fill="both", expand=True)

    def _switch(self) -> None:
        self.app.settings.tags_view = self._view.get()
        self.app.save_settings()
        self._show()
        if self._current.dirty:
            self._current.reload()

    def reload(self) -> None:
        self._current.reload()

    def update_repo_items(self) -> None:
        self.browse.update_repo_items()
        self.compare.update_repo_items()

    def restyle(self) -> None:
        self.browse.restyle()
        self.compare.restyle()
