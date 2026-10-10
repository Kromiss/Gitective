"""Commits without MR tab (CO-01..CO-08)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from gitective.core.dates import format_datetime
from gitective.core.orphan_commits import OrphanCommit, find_orphan_commits
from gitective.core.people import PersonRef
from gitective.ui.data_tab import DataTab
from gitective.ui.grid import Column, sort_rows
from gitective.ui.pagination import Pager
from gitective.core.search import matches
from gitective.ui.widgets import MultiSelect, search_box

if TYPE_CHECKING:
    from gitective.ui.app import App

COLUMNS = [
    Column("repo", "Dépôt", 150),
    Column("branch", "Branche", 110, kind="mono"),
    Column("sha", "SHA", 96, kind="link"),
    Column("message", "Message", 300, kind="link", stretch=True),
    Column("author", "Auteur", 160),
    Column("date", "Date de commit", 130, kind="mono"),
]

Item = tuple[OrphanCommit, PersonRef]

SORT_KEYS: dict[str, Callable[[Item], Any]] = {
    "repo": lambda i: i[0].project.path.casefold(),
    "branch": lambda i: i[0].project.branch,
    "sha": lambda i: i[0].commit.short_id,
    "message": lambda i: i[0].commit.title.casefold(),
    "author": lambda i: i[1].name.casefold(),
    "date": lambda i: i[0].commit.committed_date,
}


class CommitsTab(DataTab):
    """Commits pushed on the watched branches without any merge request."""

    table = "commits"

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master, app, sort_key="date", ascending=False)
        self._items: list[Item] = []
        self._visible: list[Item] = []

        bar = ttk.Frame(self, style="Bar.TFrame", padding=(16, 10))
        bar.pack(fill="x")
        period = ttk.Frame(bar, style="Bar.TFrame")
        period.pack(side="left")
        ttk.Label(period, text="Période (reprise du filtre MR)", style="BarMuted.TLabel").pack(anchor="w")
        self._period = ttk.Label(period, style="Bar.TLabel")
        self._period.pack(anchor="w")
        self.repos = MultiSelect(bar, "Dépôts", self._repos_changed, app.get_theme)
        self.repos.pack(side="left", padx=(20, 0))
        self.repos.set_selected([str(r) for r in app.filters.repos])
        self.authors = self.make_authors(bar)
        self.authors.pack(side="left", padx=(8, 0))
        progress = ttk.Frame(bar, style="Bar.TFrame")
        progress.pack(side="left", padx=(24, 0))
        self._progress_text = ttk.Label(progress, style="BarMuted.TLabel")
        self._progress_text.pack(anchor="w")
        self._progress = ttk.Progressbar(progress, length=260, mode="determinate")
        self.refresh_button(bar).pack(side="right")

        summary = ttk.Frame(self, padding=(16, 10, 16, 6))
        summary.pack(fill="x")
        self._count = ttk.Label(summary, style="Title.TLabel")
        self._count.pack(side="left")
        self._search = search_box(summary, lambda: self._apply_view(reset_page=True))
        ttk.Label(summary, text="Clic sur un commit : ouvre sa page GitLab", style="Muted.TLabel").pack(side="right")
        self.grid_view = self.make_grid(COLUMNS, "Aucun commit hors MR sur cette période", links=True)
        self.grid_view.pack(fill="both", expand=True, padx=16)
        # Same page size as the MR tab at launch; not saved separately.
        self.pager = Pager(self, lambda _page, _size: self._render_page(), page_size=app.filters.page_size)
        self.pager.pack(fill="x", padx=16, pady=10)
        app.filters.subscribe(self._filters_changed)
        self._update_period()

    def _repos_changed(self, keys: list[str]) -> None:
        self.app.filters.repos = [int(k) for k in keys]
        self.app.filters.changed("repos")

    def _filters_changed(self, what: str) -> None:
        self._update_period()
        if what == "authors":
            self.authors.set_selected(self.app.filters.authors)
            self._apply_view(reset_page=True)
        elif what in ("period", "repos"):
            self.repos.set_selected([str(r) for r in self.app.filters.repos])
            self.request_reload()

    def _update_period(self) -> None:
        self._period.configure(text=self.app.filters.period_text())

    def reload(self) -> None:
        self.dirty = False
        if not self.app.ensure_connection():
            return
        try:
            period = self.app.filters.period()
        except ValueError:
            self.app.notify("error", "Dates invalides : utilisez le format JJ/MM/AAAA.")
            return
        projects = [p for p in self.app.selected_projects() if p.branch]
        if not projects:
            self.app.notify("info", "Aucune branche surveillée : définissez une branche par dépôt dans l'onglet Config.")
        client, cache = self.app.client, self.app.cache
        assert client is not None
        workers = self.app.settings.parallel_requests
        self._progress.pack(anchor="w", pady=(2, 0))
        self._progress_text.configure(text="Recherche des commits…")
        self._progress.configure(value=0, maximum=1)

        def task(progress: Callable[[int, int], None]) -> tuple[list[OrphanCommit], list[Exception]]:
            errors: list[Exception] = []
            orphans = find_orphan_commits(client, cache, projects, period, progress=progress,
                                          on_error=errors.append, workers=workers)
            return orphans, errors

        self.app.runner.run("commits", task, self._loaded, self._failed, on_progress=self._on_progress)

    def _on_progress(self, done: int, total: int) -> None:
        self._progress.configure(maximum=max(total, 1), value=done)
        self._progress_text.configure(text=f"Analyse des commits : {done} / {total}")

    def _hide_progress(self) -> None:
        self._progress.pack_forget()
        self._progress_text.configure(text="")

    def _failed(self, exc: BaseException) -> None:
        self._hide_progress()
        self.app.report_error(exc)

    def _loaded(self, result: tuple[list[OrphanCommit], list[Exception]]) -> None:
        orphans, errors = result
        self._hide_progress()
        if errors:
            self.app.report_error(errors[0], extra=len(errors) - 1)
        self._items = [(o, self.app.people.for_git(o.commit.author_name, o.commit.author_email)) for o in orphans]
        self.app.register_people((p.key, p.name) for _, p in self._items)
        self._apply_view(reset_page=True)

    def _apply_view(self, reset_page: bool = False) -> None:
        authors = set(self.app.filters.authors)
        needle = self._search.get().strip().casefold()
        items = [(o, p) for o, p in self._items
                 if (not authors or p.key in authors)
                 and matches(needle, o.commit.message, o.commit.id, p.name, o.commit.author_email, o.project.path)]
        self._visible = sort_rows(items, SORT_KEYS[self._sort_key], self._ascending)
        self._count.configure(text=f"{len(self._visible)} commit(s) poussé(s) sans MR")
        self.pager.update_total(len(self._visible), reset=reset_page)
        self._render_page()

    def _render_page(self) -> None:
        """Only the current page is drawn, so long lists stay fluid (P2)."""
        self.grid_view.set_rows([{
            "repo": o.project.path.split("/")[-1],
            "branch": o.project.branch,
            "sha": (o.commit.short_id, o.commit.web_url),
            "message": (o.commit.title, o.commit.web_url),
            "author": person.name,
            "date": format_datetime(o.commit.committed_date),
        } for o, person in self._visible[self.pager.slice()]])
