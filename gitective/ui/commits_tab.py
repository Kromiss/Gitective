"""Commits without MR tab (CO-01..CO-08)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from gitective.core.dates import format_datetime
from gitective.core.orphan_commits import OrphanCommit, find_orphan_commits
from gitective.core.people import PersonRef
from gitective.ui.grid import Column, DataGrid, sort_rows
from gitective.ui.widgets import MultiSelect

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


class CommitsTab(ttk.Frame):
    """Commits pushed on the watched branches without any merge request."""

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master)
        self.app = app
        self.dirty = True
        self._items: list[Item] = []
        self._sort_key = "date"
        self._ascending = False

        bar = ttk.Frame(self, style="Bar.TFrame", padding=(16, 10))
        bar.pack(fill="x")
        period = ttk.Frame(bar, style="Bar.TFrame")
        period.pack(side="left")
        ttk.Label(period, text="Période (reprise du filtre MR)", style="BarMuted.TLabel").pack(anchor="w")
        self._period = ttk.Label(period, style="Bar.TLabel")
        self._period.pack(anchor="w")
        self.repos = MultiSelect(bar, "Dépôts", self._repos_changed, app.get_theme)
        self.repos.pack(side="left", padx=(20, 0))
        self.authors = MultiSelect(bar, "Auteurs", self._authors_changed, app.get_theme, all_text="Toutes")
        self.authors.pack(side="left", padx=(8, 0))
        self.repos.set_selected([str(r) for r in app.filters.repos])
        self.authors.set_selected(app.filters.authors)
        progress = ttk.Frame(bar, style="Bar.TFrame")
        progress.pack(side="left", padx=(24, 0))
        self._progress_text = ttk.Label(progress, style="BarMuted.TLabel")
        self._progress_text.pack(anchor="w")
        self._progress = ttk.Progressbar(progress, length=260, mode="determinate")
        ttk.Button(bar, text="⟳  Rafraîchir (F5)", style="Accent.TButton", command=app.refresh).pack(side="right")

        summary = ttk.Frame(self, padding=(16, 10, 16, 6))
        summary.pack(fill="x")
        self._count = ttk.Label(summary, style="Title.TLabel")
        self._count.pack(side="left")
        ttk.Label(summary, text="Clic sur un commit : ouvre sa page GitLab", style="Muted.TLabel").pack(side="right")
        self.grid_view = DataGrid(self, COLUMNS, app.get_theme, on_sort=self._sort_by, on_link=app.open_url,
                                  empty_text="Aucun commit hors MR sur cette période",
                                  widths=app.column_widths("commits"),
                                  on_widths_changed=lambda w: app.save_column_widths("commits", w))
        self.grid_view.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.grid_view.set_sort(self._sort_key, self._ascending)
        app.filters.subscribe(self._filters_changed)
        self._update_period()

    def _repos_changed(self, keys: list[str]) -> None:
        self.app.filters.repos = [int(k) for k in keys]
        self.app.filters.changed("repos")

    def _authors_changed(self, keys: list[str]) -> None:
        self.app.filters.authors = keys
        self.app.filters.changed("authors")

    def _filters_changed(self, what: str) -> None:
        self._update_period()
        if what == "authors":
            self.authors.set_selected(self.app.filters.authors)
            self._apply_view()
        elif what in ("period", "repos"):
            self.repos.set_selected([str(r) for r in self.app.filters.repos])
            self.request_reload()

    def _update_period(self) -> None:
        self._period.configure(text=self.app.filters.period_text())

    def request_reload(self) -> None:
        self.dirty = True
        if self.app.is_visible(self):
            self.reload()

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
        self._progress.pack(anchor="w", pady=(2, 0))
        self._progress_text.configure(text="Recherche des commits…")
        self._progress.configure(value=0, maximum=1)

        def task(progress: Callable[[int, int], None]) -> tuple[list[OrphanCommit], list[Exception]]:
            errors: list[Exception] = []
            orphans = find_orphan_commits(client, cache, projects, period, progress=progress, on_error=errors.append)
            return orphans, errors

        self.app.runner.run("commits", task, self._loaded, self._failed, on_progress=self._on_progress)

    def _on_progress(self, done: int, total: int) -> None:
        self._progress.configure(maximum=max(total, 1), value=done)
        self._progress_text.configure(text=f"Analyse des commits : {done} / {total}")

    def _failed(self, exc: BaseException) -> None:
        self._progress.pack_forget()
        self._progress_text.configure(text="")
        self.app.report_error(exc)

    def _loaded(self, result: tuple[list[OrphanCommit], list[Exception]]) -> None:
        orphans, errors = result
        self._progress.pack_forget()
        self._progress_text.configure(text="")
        if errors:
            self.app.report_error(errors[0], extra=len(errors) - 1)
        self._items = [(o, self.app.people.for_git(o.commit.author_name, o.commit.author_email)) for o in orphans]
        self.app.register_people((p.key, p.name) for _, p in self._items)
        self._apply_view()

    def _apply_view(self) -> None:
        authors = set(self.app.filters.authors)
        items = [i for i in self._items if not authors or i[1].key in authors]
        items = sort_rows(items, SORT_KEYS[self._sort_key], self._ascending)
        self._count.configure(text=f"{len(items)} commit(s) poussé(s) sans MR")
        self.grid_view.set_rows([{
            "repo": o.project.path.split("/")[-1],
            "branch": o.project.branch,
            "sha": (o.commit.short_id, o.commit.web_url),
            "message": (o.commit.title, o.commit.web_url),
            "author": person.name,
            "date": format_datetime(o.commit.committed_date),
        } for o, person in items])

    def _sort_by(self, key: str) -> None:
        self._ascending = not self._ascending if key == self._sort_key else True
        self._sort_key = key
        self.grid_view.set_sort(key, self._ascending)
        self._apply_view()

    def restyle(self) -> None:
        self.grid_view.redraw()

    def update_repo_items(self) -> None:
        self.repos.set_items([(str(p.id), p.path) for p in self.app.settings.projects])
