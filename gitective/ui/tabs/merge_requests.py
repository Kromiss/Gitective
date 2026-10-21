"""Merge Requests tab: filters, colored grid, average score, pagination, detail panel, direct commits."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from datetime import date
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from gitective.shared.i18n import t
from gitective.reporting.statistics import average
from gitective.review.mr_evaluation import Pair, evaluate_all, load_merge_requests, load_pairs
from gitective.review.mr_filters import mr_shas, names, people_cell, people_choices, step_selection, visible
from gitective.review.rules import Evaluation, score_level
from gitective.settings.config_file import TrackedProject
from gitective.shared.dates import format_datetime
from gitective.shared.search import sha_hit
from gitective.ui.components.filter_bar import MrFilterBar
from gitective.ui.components.grid import Column, sort_rows
from gitective.ui.components.pagination import Pager
from gitective.ui.tabs.data_tab import DataTab
from gitective.ui.tabs.direct_commits import CommitsView
from gitective.ui.tabs.mr_detail_panel import MrDetailPanel

if TYPE_CHECKING:
    from gitective.ui.app import App

STATE_WORDS = {"merged": t("{count} MR mergée(s)"), "opened": t("{count} MR ouverte(s)"), "closed": t("{count} MR fermée(s)"),
               "direct": "{count} MR"}
STATUS_ORDER = {"ok": 0, "na": 1, "ko": 2}
NOT_TRACKED = t(" (non suivi)")

NEW_COLUMN = Column("new", t("Nouvelle"), 30, kind="dot", align="center")
BASE_COLUMNS = [
    Column("repo", t("Dépôt"), 120),
    Column("title", t("Titre"), 260, kind="link", stretch=True),
    Column("author", t("Auteur"), 115),
    Column("assignees", t("Assignés"), 120, kind="people"),
    Column("reviewers", t("Relecteurs"), 120, kind="people"),
    Column("merger", t("Mergeur"), 115, kind="flag"),
    Column("created", t("Créée"), 142, kind="mono"),
    Column("merged", t("Mergée"), 142, kind="mono"),
]
SCORE_COLUMN = Column("score", t("Score"), 66, kind="score", align="center")


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

Key = tuple[int, int]
Loaded = tuple[list[Evaluation], list[Exception], dict[Key, list[str]]]


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
        self._commit_shas: dict[Key, list[str]] = {}  # stored commits of the loaded MRs, for the SHA search
        self._soft = False  # reload after a synchronisation: keep page and selection
        self._focus: Key | None = None  # MR to select once loaded (VE-14)

        self.bar = MrFilterBar(self, app.filters, app.get_theme, app.refresh, lambda m: app.notify("error", m),
                               self._search_changed)
        self.bar.pack(fill="x", padx=16, pady=(12, 0))
        self.repos, self.authors = self.bar.repos, self.bar.authors
        self._search = self.bar.search
        # Two interchangeable views under the shared filter bar.
        self._mr_view = ttk.Frame(self)
        self.commits = CommitsView(self, app, self.repos, self.authors, self._search)

        # Table card on the left, detail panel on the right when a row is selected (DE-02).
        self._split = ttk.PanedWindow(self._mr_view, orient="horizontal")
        self._split.pack(fill="both", expand=True, padx=16, pady=(12, 0))
        left = ttk.Frame(self._split)
        self._split.add(left, weight=1)
        card = ttk.Frame(left, style="Card.TFrame", padding=(10, 8, 10, 10))
        card.pack(fill="both", expand=True)
        summary = ttk.Frame(card, style="Bar.TFrame", padding=(6, 2, 6, 8))
        summary.pack(fill="x")
        self._count = ttk.Label(summary, style="Section.TLabel")
        self._count.pack(side="left")
        ttk.Label(summary, text=t("Score moyen"), style="BarMuted.TLabel").pack(side="left", padx=(18, 6))
        self._avg = tk.Label(summary, padx=8, pady=1)
        self._avg.pack(side="left")
        self._progress_text = ttk.Label(summary, style="BarMuted.TLabel")
        self._progress_text.pack(side="left", padx=(18, 6))
        self._progress = ttk.Progressbar(summary, length=220, mode="determinate")
        ttk.Label(summary, text=t("Clic sur un titre : ouvre GitLab · sur la ligne : détail"),
                  style="BarMuted.TLabel").pack(side="right")
        self.grid_view = self.make_grid(BASE_COLUMNS, t("Aucune merge request pour ces filtres"), links=True,
                                        master=card, on_select=self._row_selected)
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
        the "Nouvelle" column exists for the open MRs (AM-04).
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
        return self.app.filters.state == "opened"

    def _sort_keys(self) -> dict[str, Callable[[Evaluation], Any]]:
        keys = dict(BASE_SORT)
        new = self.app.new_mr_keys()
        keys["new"] = lambda e: 0 if _key(e) in new else 1
        for cid in self._criteria_ids:
            keys[f"c:{cid}"] = lambda e, c=cid: STATUS_ORDER[e.results[c].status] if c in e.results else None
        return keys

    def update_repo_items(self) -> None:
        """Tracked repositories, plus the untracked ones holding the user's open MRs (AM-08)."""
        items = [(str(p.id), p.path) for p in self.app.settings.projects]
        tracked = {p.id for p in self.app.settings.projects}
        extra = {mr.project_id: mr.project_path for mr, _ in self.app.my_mrs if mr.project_id not in tracked}
        items += [(str(pid), path + NOT_TRACKED) for pid, path in extra.items()]
        self.repos.set_items(items)

    # ------------------------------------------------------------- Loading

    def _search_changed(self) -> None:
        (self.commits if self._direct else self)._apply_view(reset_page=True)

    def _filters_changed(self, what: str) -> None:
        self.app.persist_filters()
        if what == "badge":
            self._search.set("")  # BA-02
        if what in ("state", "badge", "reset", "focus"):
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
            self.app.notify("error", t("Dates invalides : utilisez le format JJ/MM/AAAA."))
            return
        projects = self.app.selected_projects()
        tracked_ids = {p.id for p in self.app.settings.projects}
        # The user's open MRs of untracked repositories join the open MRs (AM-08).
        wanted = set(self.app.filters.repos)
        extra: list[Pair] = []
        if state == "opened":
            extra = [(TrackedProject(id=mr.project_id, path=mr.project_path), mr) for mr, _ in self.app.my_mrs
                     if mr.project_id not in tracked_ids and (not wanted or mr.project_id in wanted)]
        data, rules, people = self.app.data, self.app.rules, self.app.people
        assert rules is not None
        workers = self.app.settings.parallel_requests
        # "Total" reads the history missing from the base, repository by repository (FI-19).
        phase = [t("Chargement de l'historique absent de la base") if period is None and state == "merged"
                 else t("Chargement des MR")]
        self._show_progress(phase[0], 0, len(projects))
        store = self.app.store

        def task(progress: Callable[[int, int], None]) -> Loaded:
            pairs, errors = load_pairs(projects, lambda p: load_merge_requests(data, p, state, period), progress)
            phase[0] = t("Lecture des commits des MR")
            evaluations = evaluate_all(data, [*pairs, *extra], rules, people, progress, workers)
            return evaluations, list(errors), store.mr_commit_shas({e.mr.project_id for e in evaluations})

        self.app.runner.run("mr", task, lambda r: self._loaded(r, tracked_ids, soft), self._failed,
                            on_progress=lambda done, total: self._show_progress(phase[0], done, total))

    def _show_progress(self, text: str, done: int, total: int) -> None:
        self._progress_text.configure(text=t("{label} : {value}", label=text, value=f"{done} / {total}") if total else text)
        self._progress.configure(maximum=max(total, 1), value=done)
        if not self._progress.winfo_ismapped():
            self._progress.pack(side="left", after=self._progress_text)

    def _hide_progress(self) -> None:
        self._progress.pack_forget()
        self._progress_text.configure(text="")

    def _failed(self, exc: BaseException) -> None:
        self._hide_progress()
        self.app.report_error(exc)

    def _loaded(self, result: Loaded, tracked: set[int], soft: bool) -> None:
        evaluations, errors, self._commit_shas = result
        self._hide_progress()
        self.absorb(evaluations, errors)
        self.app.register_people((p.key, p.name) for e in evaluations for p in (*e.assignees, *e.reviewers))
        self._tracked = tracked
        self.bar.mergers.set_items(sorted({(e.merger.key, e.merger.name) for e in evaluations if e.merger}))
        self._set_people_items(evaluations)
        self._evaluations = evaluations
        self.update_columns()
        self._apply_view(reset_page=not soft)
        focus, self._focus = self._focus, None
        target = next((e for e in self._visible_rows if _key(e) == focus), None)
        if target is not None:
            self._reveal(target)
        elif self._panel_open and self._selected is not None:
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
        rows = visible(self._evaluations, self.app.filters, self._search.get(), self._commit_shas)
        self._visible_rows = sort_rows(rows, self._sort_keys()[self._sort_key], self._ascending)
        self.pager.update_total(len(self._visible_rows), reset=reset_page)
        self._show_summary()
        self._render_page(keep_scroll=not reset_page)

    def _show_summary(self) -> None:
        theme = self.app.get_theme()
        count = len(self._visible_rows)
        self._count.configure(text=STATE_WORDS[self.app.filters.state].format(count=count))
        # Drafts are shown but never counted in the average (FI-08).
        scores = [e.score for e in self._visible_rows if not e.mr.draft]
        if scores:
            avg = average(scores)
            bg, fg = theme.level_colors(score_level(round(avg, 6), self.app.settings.green_threshold,
                                                    self.app.settings.orange_threshold))
            self._avg.configure(text=f"{avg:.0f} %", background=bg, foreground=fg,
                                font=(theme.font[0], theme.font[1] + 1, "bold"))
        else:
            self._avg.configure(text="—", background=theme.surface, foreground=theme.muted, font=theme.font)

    def _page_rows(self) -> list[Evaluation]:
        return self._visible_rows[self.pager.slice()]

    def _render_page(self, keep_scroll: bool = False) -> None:
        settings = self.app.settings
        me = self.app.me_key()
        new = self.app.new_mr_keys() if self._shows_new else set()
        needle = self._search.get()
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
                row["_muted"], row["_tag"] = True, t("BROUILLON")
            else:
                # Which SHA the search found: "merge 4f1a9c2e" before the title (FI-20).
                row["_tag"] = sha_hit(needle, mr_shas(ev, self._commit_shas))
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

    def focus_mr(self, project_id: int, iid: int, day: date) -> None:
        """Show a merged MR: its day, newest merges first, its page, selected with its panel (VE-14)."""
        self._focus = (project_id, iid)
        self._sort_key, self._ascending = "merged", False
        self.app.filters.show_merged_on(day)

    def _reveal(self, ev: Evaluation) -> None:
        index = self._visible_rows.index(ev)
        self.pager.page = index // self.pager.page_size + 1
        self.pager.update_total(len(self._visible_rows))
        self.open_detail(ev)
        self.grid_view.see(index % self.pager.page_size)

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
