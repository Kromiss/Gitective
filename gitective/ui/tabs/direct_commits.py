"""Direct commits view of the Merge Requests tab (CO-01..CO-09)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from gitective.shared.i18n import t
from gitective.shared.dates import HISTORY_START, format_datetime, now_local
from gitective.review.direct_commits import OrphanCommit, find_orphan_commits
from gitective.shared.people import PersonRef
from gitective.ui.tabs.data_tab import DataTab
from gitective.ui.components.grid import Column, sort_rows
from gitective.ui.components.pagination import Pager
from gitective.shared.search import matches
from gitective.ui.components.widgets import MultiSelect

if TYPE_CHECKING:
    from gitective.ui.app import App

COLUMNS = [
    Column("repo", t("Dépôt"), 150),
    Column("branch", t("Branche"), 110, kind="mono"),
    Column("sha", t("SHA"), 96, kind="link"),
    Column("message", t("Message"), 300, kind="link", stretch=True),
    Column("author", t("Auteur"), 160),
    Column("date", t("Date de commit"), 130, kind="mono"),
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


class CommitsView(DataTab):
    """Commits pushed on the watched branches without any merge request.

    Shown inside the Merge Requests tab when the "Commits directs" state is
    selected; it reuses that tab's filter bar (dates, repositories, authors).
    """

    table = "commits"

    def __init__(self, master: tk.Misc, app: App, repos: MultiSelect, authors: MultiSelect,
                 search: tk.StringVar) -> None:
        super().__init__(master, app, sort_key="date", ascending=False)
        self._items: list[Item] = []
        self._visible: list[Item] = []
        self.repos, self.authors = repos, authors
        self._search = search  # the filter bar's search field (FI-12)

        card = ttk.Frame(self, style="Card.TFrame", padding=(10, 8, 10, 10))
        card.pack(fill="both", expand=True, padx=16, pady=(12, 0))
        summary = ttk.Frame(card, style="Bar.TFrame", padding=(6, 2, 6, 8))
        summary.pack(fill="x")
        self._count = ttk.Label(summary, style="Section.TLabel")
        self._count.pack(side="left")
        self._progress_text = ttk.Label(summary, style="BarMuted.TLabel")
        self._progress_text.pack(side="left", padx=(18, 6))
        self._progress = ttk.Progressbar(summary, length=200, mode="determinate")
        ttk.Label(summary, text=t("Clic sur un commit : ouvre sa page GitLab"), style="BarMuted.TLabel").pack(side="right")
        self.grid_view = self.make_grid(COLUMNS, t("Aucun commit direct sur cette période"), links=True, master=card)
        self.grid_view.pack(fill="both", expand=True)
        self.pager = Pager(self, self._page_changed, page_size=app.filters.page_size)
        self.pager.pack(fill="x", padx=16, pady=10)

    def _page_changed(self, _page: int, size: int) -> None:
        if size != self.app.filters.page_size:
            self.app.filters.page_size = size
            self.app.persist_filters()
        self._render_page()

    def reload(self) -> None:
        self.dirty = False
        if not self.app.ensure_connection():
            return
        try:
            # "Total": the whole history of the watched branches (FI-19).
            period = self.app.filters.period() or (HISTORY_START, now_local())
        except ValueError:
            self.app.notify("error", t("Dates invalides : utilisez le format JJ/MM/AAAA."))
            return
        projects = [p for p in self.app.selected_projects() if p.branch]
        if not projects:
            self.app.notify("info", t("Aucune branche surveillée : définissez une branche par dépôt dans l'onglet Config."))
        data = self.app.data
        workers = self.app.settings.parallel_requests
        self._progress.pack(side="left")
        self._progress_text.configure(text=t("Recherche des commits…"))
        self._progress.configure(value=0, maximum=1)

        def task(progress: Callable[[int, int], None]) -> tuple[list[OrphanCommit], list[Exception]]:
            errors: list[Exception] = []
            orphans = find_orphan_commits(data, projects, period, progress=progress,
                                          on_error=errors.append, workers=workers)
            return orphans, errors

        self.app.runner.run("commits", task, self._loaded, self._failed, on_progress=self._on_progress)

    def _on_progress(self, done: int, total: int) -> None:
        self._progress.configure(maximum=max(total, 1), value=done)
        self._progress_text.configure(text=t("Analyse des commits : {done} / {total}", done=done, total=total))

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
        else:
            self.app.report_offline()
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
        self._count.configure(text=t("{count} commit(s) direct(s)", count=len(self._visible)))
        self.pager.update_total(len(self._visible), reset=reset_page)
        self._render_page()

    def _render_page(self) -> None:
        """Only the current page is drawn, so long lists stay fluid (P2)."""
        self.grid_view.set_rows([{
            "repo": self.app.repo_label(o.project.path),
            "branch": o.project.branch,
            "sha": (o.commit.short_id, o.commit.web_url),
            "message": (o.commit.title, o.commit.web_url),
            "author": person.name,
            "date": format_datetime(o.commit.committed_date),
        } for o, person in self._visible[self.pager.slice()]])
