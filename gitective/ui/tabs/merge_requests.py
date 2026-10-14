"""Merge Requests tab: filters, colored grid, average score, pagination, detail panel, direct commits."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from gitective.reporting.statistics import average
from gitective.review.mr_evaluation import Pair, evaluate_all, load_merge_requests, load_pairs
from gitective.review.mr_filters import names, people_cell, people_choices, step_selection, visible
from gitective.review.rules import Evaluation, score_level
from gitective.settings.config_file import TrackedProject
from gitective.shared.dates import format_datetime
from gitective.ui.components.filter_bar import MrFilterBar
from gitective.ui.components.grid import Column, sort_rows
from gitective.ui.components.pagination import Pager
from gitective.ui.components.widgets import search_box
from gitective.ui.tabs.data_tab import DataTab
from gitective.ui.tabs.direct_commits import CommitsView
from gitective.ui.tabs.mr_detail_panel import MrDetailPanel

if TYPE_CHECKING:
    from gitective.ui.app import App

STATE_WORDS = {"merged": "mergée(s)", "opened": "ouverte(s)", "closed": "fermée(s)", "direct": ""}
STATUS_ORDER = {"ok": 0, "na": 1, "ko": 2}
NOT_TRACKED = " (non suivi)"

NEW_COLUMN = Column("new", "Nouvelle", 30, kind="dot", align="center")
BASE_COLUMNS = [
    Column("repo", "Dépôt", 120),
    Column("title", "Titre", 260, kind="link", stretch=True),
    Column("author", "Auteur", 115),
    Column("assignees", "Assignés", 120, kind="people"),
    Column("reviewers", "Relecteurs", 120, kind="people"),
    Column("merger", "Mergeur", 115, kind="flag"),
    Column("created", "Créée", 142, kind="mono"),
    Column("merged", "Mergée", 142, kind="mono"),
]
SCORE_COLUMN = Column("score", "Score", 66, kind="score", align="center")


BASE_SORT: dict[str, Callable[[Evaluation], Any]] = {
    "repo": lambda e: e.project_path.casefold(),
    "title": lambda e: e.mr.title.casefold(),
    "author": lambda e: e.author.name.casefold(),
    "assignees": lambda e: names(e.assignees).casefold() or None,
    "reviewers": lambda e: names(e.reviewers).casefold() or None,
    "merger": lambda e: e.merger.name.casefold() if e.merger else None,
    "created": lambda e: e.mr.created_at,
    "merged": lambda e: e.mr.merged_at,
    "score": lambda e: e.score,
}

Loaded = tuple[list[Evaluation], list[Exception]]
Key = tuple[int, int]


def _key(ev: Evaluation) -> Key:
    return ev.mr.project_id, ev.mr.iid


class MrTab(DataTab):
    """Lists the merge requests of the tracked repositories with their checks."""

    table = "mr"

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master, app, sort_key="merged", ascending=False)
        self._evaluations: list[Evaluation] = []
        self._visible_rows: list[Evaluation] = []
        self._tracked: set[int] = set()
        self._selected: Key | None = None
        self._soft = False  # reload after a synchronisation: keep page and selection

        self.bar = MrFilterBar(self, app.filters, app.get_theme, app.refresh, lambda m: app.notify("error", m))
        self.bar.pack(fill="x")
        self.repos, self.authors = self.bar.repos, self.bar.authors
        # Two interchangeable views under the shared filter bar.
        self._mr_view = ttk.Frame(self)
        self.commits = CommitsView(self, app, self.repos, self.authors)
        summary = ttk.Frame(self._mr_view, padding=(16, 10, 16, 6))
        summary.pack(fill="x")
        self._count = ttk.Label(summary, style="Title.TLabel")
        self._count.pack(side="left")
        ttk.Label(summary, text="Score moyen", style="Muted.TLabel").pack(side="left", padx=(18, 6))
        self._avg = tk.Label(summary, padx=8, pady=1)
        self._avg.pack(side="left")
        self._progress_text = ttk.Label(summary, style="Muted.TLabel")
        self._progress_text.pack(side="left", padx=(18, 0))
        self._search = search_box(summary, lambda: self._apply_view(reset_page=True))
        ttk.Label(summary, text="Clic sur un titre : ouvre GitLab · sur la ligne : détail",
                  style="Muted.TLabel").pack(side="right")

        # Table on the left, detail panel on the right when a row is selected (DE-02).
        self._split = ttk.PanedWindow(self._mr_view, orient="horizontal")
        self._split.pack(fill="both", expand=True, padx=16)
        left = ttk.Frame(self._split)
        self._split.add(left, weight=1)
        self.grid_view = self.make_grid(BASE_COLUMNS, "Aucune merge request pour ces filtres", links=True,
                                        master=left, on_select=self._row_selected)
        self.grid_view.pack(fill="both", expand=True)
        self.pager = Pager(left, self._page_changed, page_size=app.filters.page_size)
        self.pager.pack(fill="x", pady=10)
        self.panel = MrDetailPanel(self._split, app, self.close_detail)
        self._split.bind("<ButtonRelease-1>", lambda e: self._panel_resized())
        body = self.grid_view.body
        body.bind("<Up>", lambda e: self._move(-1))
        body.bind("<Down>", lambda e: self._move(1))
        body.bind("<Escape>", lambda e: self.close_detail())

        self.update_columns()
        app.filters.subscribe(self._filters_changed)
        self._show_view()
        self._show_summary()

    @property
    def _direct(self) -> bool:
        return self.app.filters.state == "direct"

    @property
    def _panel_open(self) -> bool:
        return str(self.panel) in {str(p) for p in self._split.panes()}

    def _show_view(self) -> None:
        """Show the commits view for the "Commits directs" state, the MR view otherwise."""
        shown, hidden = (self.commits, self._mr_view) if self._direct else (self._mr_view, self.commits)
        hidden.pack_forget()
        shown.pack(fill="both", expand=True)

    # ------------------------------------------------------------ Columns

    def update_columns(self) -> None:
        """One status column per active rule, then the fixed criteria (RP-06).

        The rule columns step aside while the detail panel shows them (DE-03);
        the "Nouvelle" column exists for the Merger's open MRs (AM-04).
        """
        rules = self.app.rules
        criteria = rules.criteria if rules else []
        self._criteria_ids = [c.id for c in criteria]
        shown = [] if self._panel_open else criteria
        new = [NEW_COLUMN] if self._shows_new else []
        columns = [*new, *BASE_COLUMNS,
                   *(Column(f"c:{c.id}", c.label, 60, kind="status", align="center") for c in shown),
                   SCORE_COLUMN]
        if self._sort_key not in self._sort_keys():
            self._sort_key, self._ascending = "merged", False
        self.grid_view.set_columns(columns)
        self.grid_view.set_sort(self._sort_key, self._ascending)

    @property
    def _shows_new(self) -> bool:
        return self.app.profile.merger and self.app.filters.state == "opened"

    def _sort_keys(self) -> dict[str, Callable[[Evaluation], Any]]:
        keys = dict(BASE_SORT)
        new = self.app.new_mr_keys()
        keys["new"] = lambda e: 0 if _key(e) in new else 1
        for cid in self._criteria_ids:
            keys[f"c:{cid}"] = lambda e, c=cid: STATUS_ORDER[e.results[c].status] if c in e.results else None
        return keys

    def update_repo_items(self) -> None:
        """Tracked repositories, plus the untracked ones holding the Merger's open MRs (AM-08)."""
        items = [(str(p.id), p.path) for p in self.app.settings.projects]
        tracked = {p.id for p in self.app.settings.projects}
        if self.app.profile.merger:
            extra = {mr.project_id: mr.project_path for mr, _ in self.app.my_mrs if mr.project_id not in tracked}
            items += [(str(pid), path + NOT_TRACKED) for pid, path in extra.items()]
        self.repos.set_items(items)

    # ------------------------------------------------------------- Loading

    def _filters_changed(self, what: str) -> None:
        self.app.persist_filters()
        if what in ("state", "badge"):
            self._show_view()
            self.update_columns()
        if what in ("authors", "mergers", "assignees", "reviewers", "drafts"):
            (self.commits if self._direct else self)._apply_view(reset_page=True)
        else:
            self.request_reload()

    def soft_reload(self) -> None:
        """Reload after a synchronisation without losing the page or the selected MR."""
        self._soft = True
        self.request_reload()

    def reload(self) -> None:
        self.dirty = False
        soft, self._soft = self._soft, False
        if self._direct:
            self.commits.reload()
            return
        if not self.app.ensure_connection():
            return
        state = self.app.filters.state
        try:
            period = self.app.filters.period() if state == "merged" else None
        except ValueError:
            self.app.notify("error", "Dates invalides : utilisez le format JJ/MM/AAAA.")
            return
        projects = self.app.selected_projects()
        tracked_ids = {p.id for p in self.app.settings.projects}
        # The Merger's open MRs of untracked repositories join the open MRs (AM-08).
        wanted = set(self.app.filters.repos)
        extra: list[Pair] = []
        if state == "opened" and self.app.profile.merger:
            extra = [(TrackedProject(id=mr.project_id, path=mr.project_path), mr) for mr, _ in self.app.my_mrs
                     if mr.project_id not in tracked_ids and (not wanted or mr.project_id in wanted)]
        data, rules, people = self.app.data, self.app.rules, self.app.people
        assert rules is not None
        self._progress_text.configure(text="Chargement…")
        workers = self.app.settings.parallel_requests

        def task(progress: Callable[[int, int], None]) -> Loaded:
            pairs, errors = load_pairs(projects, lambda p: load_merge_requests(data, p, state, period))
            return evaluate_all(data, [*pairs, *extra], rules, people, progress, workers), list(errors)

        self.app.runner.run("mr", task, lambda r: self._loaded(r, tracked_ids, soft), self._failed,
                            on_progress=self._on_progress)

    def _on_progress(self, done: int, total: int) -> None:
        self._progress_text.configure(text=f"Lecture des commits des MR : {done} / {total}")

    def _failed(self, exc: BaseException) -> None:
        self._progress_text.configure(text="")
        self.app.report_error(exc)

    def _loaded(self, result: Loaded, tracked: set[int], soft: bool) -> None:
        evaluations, errors = result
        self._progress_text.configure(text="")
        self.absorb(evaluations, errors)
        self.app.register_people((p.key, p.name) for e in evaluations for p in (*e.assignees, *e.reviewers))
        self._tracked = tracked
        self.bar.mergers.set_items(sorted({(e.merger.key, e.merger.name) for e in evaluations if e.merger}))
        self._set_people_items(evaluations)
        self._evaluations = evaluations
        self.update_columns()
        self._apply_view(reset_page=not soft)
        if self._panel_open and self._selected is not None:
            current = next((e for e in evaluations if _key(e) == self._selected), None)
            if current is not None:
                self.panel.show(current, _key(current) in self.app.new_mr_keys())

    def _set_people_items(self, evaluations: list[Evaluation]) -> None:
        """Assignee and reviewer choices: the user first as "Moi", then everyone seen, then nobody."""
        me, name = self.app.me_key(), self.app.me_name()
        self.bar.assignees.set_items(people_choices(evaluations, "assignees", me, name), keep_order=True)
        self.bar.reviewers.set_items(people_choices(evaluations, "reviewers", me, name), keep_order=True)

    # ---------------------------------------------------------------- View

    def _apply_view(self, reset_page: bool = False) -> None:
        rows = visible(self._evaluations, self.app.filters, self._search.get())
        self._visible_rows = sort_rows(rows, self._sort_keys()[self._sort_key], self._ascending)
        self.pager.update_total(len(self._visible_rows), reset=reset_page)
        self._show_summary()
        self._render_page(keep_scroll=not reset_page)

    def _show_summary(self) -> None:
        theme = self.app.get_theme()
        count = len(self._visible_rows)
        self._count.configure(text=f"{count} MR {STATE_WORDS[self.app.filters.state]}")
        # Drafts are shown but never counted in the average (FI-08).
        scores = [e.score for e in self._visible_rows if not e.mr.draft]
        if scores:
            avg = average(scores)
            bg, fg = theme.level_colors(score_level(round(avg, 6), self.app.settings.green_threshold,
                                                    self.app.settings.orange_threshold))
            self._avg.configure(text=f"{avg:.0f} %", background=bg, foreground=fg,
                                font=(theme.font[0], theme.font[1] + 1, "bold"))
        else:
            self._avg.configure(text="—", background=theme.bg, foreground=theme.muted, font=theme.font)

    def _page_rows(self) -> list[Evaluation]:
        return self._visible_rows[self.pager.slice()]

    def _render_page(self, keep_scroll: bool = False) -> None:
        settings = self.app.settings
        me = self.app.me_key()
        new = self.app.new_mr_keys() if self._shows_new else set()
        rows = []
        for ev in self._page_rows():
            mr = ev.mr
            repo = ev.project_path.split("/")[-1] + ("" if mr.project_id in self._tracked else NOT_TRACKED)
            row: dict[str, Any] = {
                "new": _key(ev) in new or None,
                "repo": repo,
                "title": (mr.title, mr.web_url),
                "author": ev.author.name,
                "assignees": people_cell(ev.assignees, me),
                "reviewers": people_cell(ev.reviewers, me),
                "merger": (ev.merger.name, ev.merger_not_assignee) if ev.merger else "",
                "created": format_datetime(mr.created_at),
                "merged": format_datetime(mr.merged_at),
                "score": (f"{ev.score:.0f} %", score_level(ev.score, settings.green_threshold, settings.orange_threshold)),
                "_selected": _key(ev) == self._selected,
            }
            if mr.draft:
                row["_muted"], row["_tag"] = True, "BROUILLON"
            for cid in self._criteria_ids:
                result = ev.results.get(cid)
                if result:
                    row[f"c:{cid}"] = (result.status, result.detail)
            rows.append(row)
        self.grid_view.set_rows(rows, keep_scroll=keep_scroll)

    def _page_changed(self, _page: int, size: int) -> None:
        if size != self.app.filters.page_size:
            self.app.filters.page_size = size
            self.app.persist_filters()
        self._render_page()

    # ---------------------------------------------------------- Detail panel

    def _row_selected(self, index: int) -> None:
        rows = self._page_rows()
        if 0 <= index < len(rows):
            self.open_detail(rows[index])

    def open_detail(self, ev: Evaluation) -> None:
        """Select an MR and show it in the side panel (DE-01)."""
        self._selected = _key(ev)
        if not self._panel_open:
            self._split.add(self.panel, weight=0)
            self.update_columns()
            self._place_sash()
        self._render_page(keep_scroll=True)
        self.panel.show(ev, _key(ev) in self.app.new_mr_keys())

    def close_detail(self) -> None:
        if self._panel_open:
            self._split.forget(self.panel)
        self._selected = None
        self.update_columns()
        self._render_page(keep_scroll=True)

    def _place_sash(self) -> None:
        """Give the panel its saved width; the table keeps the rest."""
        self._split.update_idletasks()
        total = self._split.winfo_width()
        if self._panel_open and total > 1:
            self._split.sashpos(0, max(300, total - self.app.settings.detail_width))

    def _panel_resized(self) -> None:
        if self._panel_open:
            self.app.save_detail_width(self.panel.winfo_width())

    def _move(self, step: int) -> None:
        """Arrow keys: previous / next MR of the filtered list, changing page when needed."""
        size = self.pager.page_size
        target = step_selection([_key(e) for e in self._visible_rows], self._selected, step, size)
        if target is None:
            return
        index, page = target
        if page != self.pager.page:
            self.pager.page = page
            self.pager.update_total(len(self._visible_rows))
        self.open_detail(self._visible_rows[index])
        self.grid_view.see(index % size)

    def restyle(self) -> None:
        self._show_summary()
        self.commits.restyle()
        if self._panel_open:
            self.panel.render()
        super().restyle()
