"""Merge Requests tab: filters, colored grid, average score, pagination."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from gitective.core.dates import format_datetime
from gitective.core.merge_requests import evaluate_all, load_merge_requests, load_pairs
from gitective.core.rules import Evaluation, score_level
from gitective.core.stats import average
from gitective.ui.data_tab import DataTab
from gitective.ui.filters import MrFilterBar
from gitective.ui.grid import Column, sort_rows
from gitective.ui.pagination import Pager
from gitective.core.search import matches
from gitective.ui.widgets import search_box

if TYPE_CHECKING:
    from gitective.ui.app import App

STATE_WORDS = {"merged": "mergée(s)", "opened": "ouverte(s)", "closed": "fermée(s)"}
STATUS_ORDER = {"ok": 0, "na": 1, "ko": 2}

BASE_COLUMNS = [
    Column("repo", "Dépôt", 120),
    Column("title", "Titre", 260, kind="link", stretch=True),
    Column("author", "Auteur", 115),
    Column("merger", "Mergeur", 115),
    Column("created", "Créée", 142, kind="mono"),
    Column("merged", "Mergée", 142, kind="mono"),
]
SCORE_COLUMN = Column("score", "Score", 66, kind="score", align="center")

BASE_SORT: dict[str, Callable[[Evaluation], Any]] = {
    "repo": lambda e: e.project_path.casefold(),
    "title": lambda e: e.mr.title.casefold(),
    "author": lambda e: e.author.name.casefold(),
    "merger": lambda e: e.merger.name.casefold() if e.merger else None,
    "created": lambda e: e.mr.created_at,
    "merged": lambda e: e.mr.merged_at,
    "score": lambda e: e.score,
}

Loaded = tuple[list[Evaluation], list[Exception]]


class MrTab(DataTab):
    """Lists the merge requests of the tracked repositories with their checks."""

    table = "mr"

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master, app, sort_key="merged", ascending=False)
        self._evaluations: list[Evaluation] = []
        self._visible_rows: list[Evaluation] = []

        self.bar = MrFilterBar(self, app.filters, app.get_theme, app.refresh, lambda m: app.notify("error", m))
        self.bar.pack(fill="x")
        self.repos, self.authors = self.bar.repos, self.bar.authors
        summary = ttk.Frame(self, padding=(16, 10, 16, 6))
        summary.pack(fill="x")
        self._count = ttk.Label(summary, style="Title.TLabel")
        self._count.pack(side="left")
        ttk.Label(summary, text="Score moyen", style="Muted.TLabel").pack(side="left", padx=(18, 6))
        self._avg = tk.Label(summary, padx=8, pady=1)
        self._avg.pack(side="left")
        self._progress_text = ttk.Label(summary, style="Muted.TLabel")
        self._progress_text.pack(side="left", padx=(18, 0))
        self._search = search_box(summary, lambda: self._apply_view(reset_page=True))
        ttk.Label(summary, text="Clic sur un titre : ouvre la MR dans le navigateur",
                  style="Muted.TLabel").pack(side="right")

        self.grid_view = self.make_grid(BASE_COLUMNS, "Aucune merge request pour ces filtres", links=True)
        self.grid_view.pack(fill="both", expand=True, padx=16)
        self.pager = Pager(self, self._page_changed, page_size=app.filters.page_size)
        self.pager.pack(fill="x", padx=16, pady=10)
        self.update_columns()
        app.filters.subscribe(self._filters_changed)
        self._show_summary()

    # ------------------------------------------------------------ Columns

    def update_columns(self) -> None:
        """One status column per active rule, then the fixed criteria (RP-06)."""
        rules = self.app.rules
        criteria = rules.criteria if rules else []
        columns = [*BASE_COLUMNS,
                   *(Column(f"c:{c.id}", c.label, 60, kind="status", align="center") for c in criteria),
                   SCORE_COLUMN]
        self._criteria_ids = [c.id for c in criteria]
        if self._sort_key not in self._sort_keys():
            self._sort_key, self._ascending = "merged", False
        self.grid_view.set_columns(columns)
        self.grid_view.set_sort(self._sort_key, self._ascending)

    def _sort_keys(self) -> dict[str, Callable[[Evaluation], Any]]:
        keys = dict(BASE_SORT)
        for cid in self._criteria_ids:
            keys[f"c:{cid}"] = lambda e, c=cid: STATUS_ORDER[e.results[c].status] if c in e.results else None
        return keys

    # ------------------------------------------------------------- Loading

    def _filters_changed(self, what: str) -> None:
        self.app.persist_filters()
        if what == "authors":
            self._apply_view(reset_page=True)
        else:
            self.request_reload()

    def reload(self) -> None:
        self.dirty = False
        if not self.app.ensure_connection():
            return
        state = self.app.filters.state
        try:
            period = self.app.filters.period() if state == "merged" else None
        except ValueError:
            self.app.notify("error", "Dates invalides : utilisez le format JJ/MM/AAAA.")
            return
        projects = self.app.selected_projects()
        client, cache, rules, people = self.app.client, self.app.cache, self.app.rules, self.app.people
        assert client is not None and rules is not None
        self._progress_text.configure(text="Chargement…")

        workers = self.app.settings.parallel_requests

        def task(progress: Callable[[int, int], None]) -> Loaded:
            pairs, errors = load_pairs(projects, lambda p: load_merge_requests(client, cache, p, state, period))
            return evaluate_all(client, cache, pairs, rules, people, progress, workers), list(errors)

        self.app.runner.run("mr", task, self._loaded, self._failed, on_progress=self._on_progress)

    def _on_progress(self, done: int, total: int) -> None:
        self._progress_text.configure(text=f"Lecture des commits des MR : {done} / {total}")

    def _failed(self, exc: BaseException) -> None:
        self._progress_text.configure(text="")
        self.app.report_error(exc)

    def _loaded(self, result: Loaded) -> None:
        evaluations, errors = result
        self._progress_text.configure(text="")
        self.absorb(evaluations, errors)
        self._evaluations = evaluations
        self._apply_view(reset_page=True)

    # ---------------------------------------------------------------- View

    def _apply_view(self, reset_page: bool = False) -> None:
        authors = set(self.app.filters.authors)
        needle = self._search.get().strip().casefold()
        rows = [e for e in self._evaluations
                if (not authors or e.author.key in authors)
                and matches(needle, e.mr.title, e.mr.description, e.author.name, e.merger.name if e.merger else None,
                            e.project_path, e.mr.source_branch, e.mr.target_branch)]
        self._visible_rows = sort_rows(rows, self._sort_keys()[self._sort_key], self._ascending)
        self.pager.update_total(len(self._visible_rows), reset=reset_page)
        self._show_summary()
        self._render_page()

    def _show_summary(self) -> None:
        theme = self.app.get_theme()
        count = len(self._visible_rows)
        self._count.configure(text=f"{count} MR {STATE_WORDS[self.app.filters.state]}")
        if count:
            avg = average(e.score for e in self._visible_rows)
            bg, fg = theme.level_colors(score_level(round(avg, 6), self.app.settings.green_threshold,
                                                    self.app.settings.orange_threshold))
            self._avg.configure(text=f"{avg:.0f} %", background=bg, foreground=fg,
                                font=(theme.font[0], theme.font[1] + 1, "bold"))
        else:
            self._avg.configure(text="—", background=theme.bg, foreground=theme.muted, font=theme.font)

    def _render_page(self) -> None:
        settings = self.app.settings
        rows = []
        for ev in self._visible_rows[self.pager.slice()]:
            mr = ev.mr
            row: dict[str, Any] = {
                "repo": ev.project_path.split("/")[-1],
                "title": (mr.title, mr.web_url),
                "author": ev.author.name,
                "merger": ev.merger.name if ev.merger else "",
                "created": format_datetime(mr.created_at),
                "merged": format_datetime(mr.merged_at),
                "score": (f"{ev.score:.0f} %", score_level(ev.score, settings.green_threshold, settings.orange_threshold)),
            }
            for cid in self._criteria_ids:
                result = ev.results.get(cid)
                if result:
                    row[f"c:{cid}"] = (result.status, result.detail)
            rows.append(row)
        self.grid_view.set_rows(rows)

    def _page_changed(self, _page: int, size: int) -> None:
        if size != self.app.filters.page_size:
            self.app.filters.page_size = size
            self.app.persist_filters()
        self._render_page()

    def restyle(self) -> None:
        self._show_summary()
        super().restyle()
