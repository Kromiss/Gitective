"""Statistics tab: per-person and per-repository figures, delays, avatars and weekly chart (ST-01..ST-15, SR-01..SR-05)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from datetime import datetime
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from gitective.shared.avatars import badge_color, initials
from gitective.shared.dates import (
    Period,
    current_month,
    current_year,
    day_range,
    format_date,
    last_days,
    now_local,
    parse_date,
    week_label,
)
from gitective.review.mr_evaluation import evaluate_all, load_all_states, load_pairs
from gitective.review.merge_rights import merge_rights
from gitective.review.direct_commits import OrphanCommit, find_orphan_commits
from gitective.shared.people import PersonRef
from gitective.review.rules import Evaluation, score_level
from gitective.reporting.statistics import (
    GLOBAL_KEY,
    PersonStats,
    RepoStats,
    by_repo,
    delay_details,
    format_days,
    per_person,
    per_repo,
    weekly_scores,
)
from gitective.ui.components.chart import Series, WeeklyChart
from gitective.ui.tabs.data_tab import DataTab
from gitective.ui.components.grid import Column, DataGrid, sort_rows
from gitective.ui.components.widgets import MultiSelect

if TYPE_CHECKING:
    from gitective.ui.app import App

AVATAR_PX = 26
PERSON, REPO = "person", "repo"
# "Total" has no start date: direct commits are then searched from this date.
HISTORY_START = datetime(2000, 1, 1).astimezone()

Loaded = tuple[list[Evaluation], dict[str, list[str]], list[OrphanCommit], list[Exception]]

HEAD_COLUMNS = [
    Column("person", "Personne", 220, kind="avatar", stretch=True),
    Column("role", "Rôle", 80, kind="tip"),
    Column("mr", "MR", 60, align="e"),
    Column("merged", "MR mergées", 90, align="e"),
    Column("score", "Score moyen", 96, kind="score", align="center"),
]
# Medians in business days; the tooltip gives average, min and max (ST-14).
DELAY_COLUMNS = [
    Column("direct", "Commits directs", 110, align="e"),
    Column("lead", "Délai création → merge", 150, kind="tip", align="e"),
    Column("merge_delay", "Délai dernier commit → merge", 190, kind="tip", align="e"),
]
REPO_HEAD = [
    Column("repo", "Dépôt", 220, kind="link", stretch=True),
    Column("mr", "MR", 60, align="e"),
    Column("merged", "MR mergées", 90, align="e"),
    Column("score", "Score moyen", 96, kind="score", align="center"),
]
REPO_TAIL = [
    Column("direct", "Commits directs", 110, align="e"),
    Column("lead", "Délai création → merge", 150, kind="tip", align="e"),
]

PERSON_SORT: dict[str, Callable[[PersonStats], Any]] = {
    "person": lambda s: s.person.name.casefold(),
    "mr": lambda s: s.mr_count,
    "merged": lambda s: s.merged_count,
    "score": lambda s: s.score_avg,
    "direct": lambda s: s.direct_commits,
    "lead": lambda s: s.lead_time_days,
}
REPO_SORT: dict[str, Callable[[RepoStats], Any]] = {
    "repo": lambda s: s.path.casefold(),
    "mr": lambda s: s.mr_count,
    "merged": lambda s: s.merged_count,
    "score": lambda s: s.score_avg,
    "direct": lambda s: s.direct_commits,
    "lead": lambda s: s.lead_time_days,
}


class StatsTab(DataTab):
    """Aggregates every MR (any state, drafts excluded) per person or per repository."""

    table = "stats"

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master, app, sort_key="score", ascending=False)
        self._evaluations: list[Evaluation] = []
        self._orphans: list[tuple[OrphanCommit, PersonRef]] = []
        self._person_rows: list[PersonStats] = []
        self._repo_rows: list[RepoStats] = []
        self._merge_repos: dict[str, list[str]] = {}  # person key → repos they can merge into
        self._images: dict[int, tk.PhotoImage] = {}
        self._repos: list[int] = []
        self._view = app.settings.stats_view
        # Each view keeps its own sort; the active one lives in _sort_key / _ascending.
        self._sorts = {PERSON: ("score", False), REPO: ("score", False)}
        start, end = last_days(30)
        self._from = tk.StringVar(value=format_date(start.date()))
        self._to = tk.StringVar(value=format_date(end.date()))
        self._total = False

        bar = ttk.Frame(self, style="Bar.TFrame", padding=(16, 10))
        bar.pack(fill="x")
        self._view_var = tk.StringVar(value=self._view)
        switch = ttk.Frame(bar, style="Bar.TFrame")
        switch.pack(side="left", padx=(0, 18), anchor="s")
        for value, text in ((PERSON, "Par personne"), (REPO, "Par dépôt")):
            ttk.Radiobutton(switch, text=text, value=value, variable=self._view_var, style="Toolbutton",
                            command=lambda: self.set_view(self._view_var.get())).pack(side="left")
        for label, var in (("Du (création)", self._from), ("Au", self._to)):
            box = ttk.Frame(bar, style="Bar.TFrame")
            box.pack(side="left", padx=(0, 10))
            ttk.Label(box, text=label, style="BarMuted.TLabel").pack(anchor="w")
            entry = ttk.Entry(box, textvariable=var, width=11)
            entry.pack()
            entry.bind("<Return>", lambda e: self._apply_dates())
        ttk.Button(bar, text="Appliquer", command=self._apply_dates).pack(side="left", anchor="s")
        shortcuts = ttk.Frame(bar, style="Bar.TFrame")
        shortcuts.pack(side="left", padx=(16, 0), anchor="s")
        for text, period in (("7 jours", lambda: last_days(7)), ("30 jours", lambda: last_days(30)),
                             ("Mois en cours", current_month), ("Année en cours", current_year)):
            ttk.Button(shortcuts, text=text, command=lambda p=period: self._shortcut(p())).pack(side="left", padx=2)
        self._total_button = ttk.Button(shortcuts, text="Total", command=self._set_total)
        self._total_button.pack(side="left", padx=2)
        self.repos = MultiSelect(bar, "Dépôts", self._repos_changed, app.get_theme)
        self.repos.pack(side="left", padx=(16, 0), anchor="s")
        self.authors = self.make_authors(bar, "Personnes")
        self.authors.pack(side="left", padx=(8, 0), anchor="s")
        self.refresh_button(bar, compact=True).pack(side="right", anchor="s")

        status = ttk.Frame(self)
        status.pack(fill="x", padx=16, pady=(8, 0))
        self._progress_text = ttk.Label(status, style="Muted.TLabel")
        self._progress_text.pack(side="left")
        self._progress = ttk.Progressbar(status, length=200, mode="determinate")
        self._hint = ttk.Label(status, style="Muted.TLabel")
        self._hint.pack(side="right")

        self._person_grid = self.make_grid(HEAD_COLUMNS, "Aucune merge request sur cette période")
        self._repo_grid = self.make_grid(REPO_HEAD, "Aucun dépôt", table="stats_repo", on_link=self._open_repo)
        self.grid_view: DataGrid = self._person_grid
        self.update_columns()
        self.chart = WeeklyChart(self, app.get_theme)
        self.chart.pack(side="bottom", fill="x", padx=16, pady=12)
        self._show_view()
        app.filters.subscribe(self._filters_changed)

    # ------------------------------------------------------------ Views

    def set_view(self, view: str) -> None:
        """Switch between the per-person and per-repository tables (ST-01)."""
        if view == self._view:
            return
        self._sorts[self._view] = (self._sort_key, self._ascending)
        self._view = view
        self._view_var.set(view)
        self.app.save_stats_view(view)
        self._show_view()
        self._apply_view()

    def _show_view(self) -> None:
        self._sort_key, self._ascending = self._sorts[self._view]
        self.grid_view.pack_forget()
        self.grid_view = self._person_grid if self._view == PERSON else self._repo_grid
        self.grid_view.set_sort(self._sort_key, self._ascending)
        self.grid_view.pack(fill="both", expand=True, padx=16, pady=(8, 0))
        self._hint.configure(text="Clic sur un dépôt : ses statistiques par personne" if self._view == REPO else "")

    def _open_repo(self, path: str) -> None:
        """SR-05: per-person view restricted to the clicked repository."""
        project = next((p for p in self.app.settings.projects if p.path == path), None)
        if project is None:
            return
        self._repos = [project.id]
        self.repos.set_selected([str(project.id)])
        self.set_view(PERSON)
        self.request_reload()

    # ------------------------------------------------------------ Columns

    def update_columns(self) -> None:
        """One 'KO' column per active criterion (custom rules + fixed), in both views."""
        criteria = self.app.rules.criteria if self.app.rules else []
        self._criteria_ids = [c.id for c in criteria]
        ko = [Column(f"ko:{c.id}", f"KO {c.label}", 60, align="e") for c in criteria]
        self._person_grid.set_columns([*HEAD_COLUMNS, *ko, *DELAY_COLUMNS])
        self._repo_grid.set_columns([*REPO_HEAD, *ko, *REPO_TAIL])
        for view, keys in ((PERSON, self._person_keys()), (REPO, self._repo_keys())):
            if self._sorts[view][0] not in keys:
                self._sorts[view] = ("score", False)
        if self._sort_key not in self._sort_keys():
            self._sort_key, self._ascending = "score", False
        self._person_grid.set_sort(*self._sorts[PERSON])
        self._repo_grid.set_sort(*self._sorts[REPO])
        self.grid_view.set_sort(self._sort_key, self._ascending)

    def _person_keys(self) -> dict[str, Callable[[PersonStats], Any]]:
        keys = dict(PERSON_SORT)
        keys["role"] = lambda s: s.person.key not in self._merge_repos
        keys["merge_delay"] = lambda s: s.merge_delay_days if s.person.key in self._merge_repos else None
        for cid in self._criteria_ids:
            keys[f"ko:{cid}"] = lambda s, c=cid: s.ko_counts.get(c, 0)
        return keys

    def _repo_keys(self) -> dict[str, Callable[[RepoStats], Any]]:
        keys = dict(REPO_SORT)
        for cid in self._criteria_ids:
            keys[f"ko:{cid}"] = lambda s, c=cid: s.ko_counts.get(c, 0)
        return keys

    def _sort_keys(self) -> dict[str, Callable[[Any], Any]]:
        return self._person_keys() if self._view == PERSON else self._repo_keys()  # type: ignore[return-value]

    def _sort_by(self, key: str) -> None:
        super()._sort_by(key)
        self._sorts[self._view] = (self._sort_key, self._ascending)

    # ------------------------------------------------------------ Filters

    def _period(self) -> Period | None:
        if self._total:
            return None
        return day_range(parse_date(self._from.get()), parse_date(self._to.get()))

    def _apply_dates(self) -> None:
        try:
            day_range(parse_date(self._from.get()), parse_date(self._to.get()))
        except ValueError:
            self.app.notify("error", "Dates invalides : utilisez le format JJ/MM/AAAA, la date de fin après la date de début.")
            return
        self._total = False
        self._total_button.configure(style="TButton")
        self.request_reload()

    def _shortcut(self, period: Period) -> None:
        self._from.set(format_date(period[0].date()))
        self._to.set(format_date(period[1].date()))
        self._apply_dates()

    def _set_total(self) -> None:
        self._total = True
        self._total_button.configure(style="Accent.TButton")
        self.request_reload()

    def _repos_changed(self, keys: list[str]) -> None:
        self._repos = [int(k) for k in keys]
        self.request_reload()

    def _filters_changed(self, what: str) -> None:
        if what == "authors":
            self.authors.set_selected(self.app.filters.authors)
            self._apply_view()

    # ------------------------------------------------------------ Loading

    def reload(self) -> None:
        self.dirty = False
        if not self.app.ensure_connection():
            return
        try:
            period = self._period()
        except ValueError:
            self.app.notify("error", "Dates invalides : utilisez le format JJ/MM/AAAA.")
            return
        projects = [p for p in self.app.settings.projects if not self._repos or p.id in self._repos]
        data, rules, people = self.app.data, self.app.rules, self.app.people
        assert rules is not None
        workers = self.app.settings.parallel_requests
        commit_period = period or (HISTORY_START, now_local())
        self._progress.pack(side="left", padx=8)
        self._progress.configure(value=0, maximum=1)
        self._progress_text.configure(text="Chargement…")

        def task(progress: Callable[[int, int], None]) -> Loaded:
            pairs, errors = load_pairs(projects, lambda p: load_all_states(data, p, period))
            evaluations = evaluate_all(data, pairs, rules, people, progress, workers, merged_commits=True)
            rights, rights_errors = merge_rights(data, projects, workers)
            merge_repos: dict[str, set[str]] = {}
            for user, repos in rights.items():
                merge_repos.setdefault(people.for_user(user).key, set()).update(repos)
            # Direct commits of the period (ST-15): only commits never checked go to GitLab.
            commit_errors: list[Exception] = []
            orphans = find_orphan_commits(data, projects, commit_period, progress=progress,
                                          on_error=commit_errors.append, workers=workers)
            return (evaluations, {k: sorted(v) for k, v in merge_repos.items()}, orphans,
                    [*errors, *rights_errors, *commit_errors])

        self.app.runner.run("stats", task, self._loaded, self._failed, on_progress=self._on_progress)

    def _on_progress(self, done: int, total: int) -> None:
        self._progress.configure(maximum=max(total, 1), value=done)
        self._progress_text.configure(text=f"Analyse : {done} / {total}")

    def _hide_progress(self) -> None:
        self._progress.pack_forget()
        self._progress_text.configure(text="")

    def _failed(self, exc: BaseException) -> None:
        self._hide_progress()
        self.app.report_error(exc)

    def _loaded(self, result: Loaded) -> None:
        evaluations, merge_repos, orphans, errors = result
        self._hide_progress()
        self.absorb(evaluations, errors)  # type: ignore[arg-type]
        self._evaluations = evaluations
        self._merge_repos = merge_repos
        self._orphans = [(o, self.app.people.for_git(o.commit.author_name, o.commit.author_email)) for o in orphans]
        self.app.register_people((p.key, p.name) for _, p in self._orphans)
        self._apply_view()
        self._load_avatars()

    def _load_avatars(self) -> None:
        """Fetch avatars in the background, then redraw (AV-01, AV-05)."""
        wanted = {p.avatar_user_id for e in self._evaluations for p in (e.author, e.merger) if p and p.avatar_user_id}
        wanted -= set(self._images)
        if not wanted:
            return
        store = self.app.avatars
        known = self.app.known_users

        def task(_progress: Callable[[int, int], None]) -> dict[int, bytes]:
            found: dict[int, bytes] = {}
            for user_id in wanted:
                user = known.get(user_id)
                content = store.image_for(user_id, user.avatar_url if user else None)
                if content:
                    found[user_id] = content
            return found

        self.app.runner.run("avatars", task, self._avatars_loaded, lambda e: None)

    def _avatars_loaded(self, images: dict[int, bytes]) -> None:
        for user_id, content in images.items():
            image = self.app.load_avatar_image(content, AVATAR_PX)
            if image is not None:
                self._images[user_id] = image
        self._render()

    # --------------------------------------------------------------- View

    def _apply_view(self, reset_page: bool = False) -> None:
        authors = set(self.app.filters.authors)
        evaluations = [e for e in self._evaluations if not authors or e.author.key in authors]
        orphans = [(o, p) for o, p in self._orphans if not authors or p.key in authors]
        if self._view == PERSON:
            # Built from every MR so a merger's delay counts the MRs of all authors (ST-13).
            stats = per_person(self._evaluations, [p for _, p in self._orphans])
            rows = [s for s in stats if not authors or s.person.key in authors]
            self._person_rows = sort_rows(rows, self._person_keys()[self._sort_key], self._ascending)
            weeks, series = weekly_scores(evaluations, sorted(authors))
            names = {e.author.key: e.author.name for e in evaluations}
            curves = [Series("Global", series[GLOBAL_KEY], main=True)]
            curves += [Series(names.get(k, k), series[k]) for k in sorted(authors) if k in names]
        else:
            # The author filter restricts the MRs and commits counted (SR-03).
            paths = [p.path for p in self.app.settings.projects if not self._repos or p.id in self._repos]
            stats_repo = per_repo(evaluations, paths, [o.project.path for o, _ in orphans])
            self._repo_rows = sort_rows(stats_repo, self._repo_keys()[self._sort_key], self._ascending)
            chosen = paths if self._repos else []
            weeks, series = weekly_scores(evaluations, chosen, key_of=by_repo)
            curves = [Series("Global", series[GLOBAL_KEY], main=True)]
            curves += [Series(p.split("/")[-1], series[p]) for p in chosen]
        self._render()
        self.chart.set_data([week_label(w) for w in weeks], curves)

    def _score_cell(self, score: float | None) -> Any:
        settings = self.app.settings
        if score is None:
            return ""
        return f"{score:.0f} %", score_level(round(score, 6), settings.green_threshold, settings.orange_threshold)

    def _render(self) -> None:
        if self._view == REPO:
            self._repo_grid.set_rows([{
                "repo": (stat.path, stat.path),
                "mr": str(stat.mr_count),
                "merged": str(stat.merged_count),
                "score": self._score_cell(stat.score_avg),
                **{f"ko:{c}": str(stat.ko_counts.get(c, 0)) for c in self._criteria_ids},
                "direct": str(stat.direct_commits),
                "lead": (format_days(stat.lead_time_days), delay_details(stat.lead_times)),
            } for stat in self._repo_rows])
            return
        rows = []
        for stat in self._person_rows:
            person = stat.person
            image = self._images.get(person.avatar_user_id) if person.avatar_user_id else None
            rows.append({
                "person": (image, initials(person.name), badge_color(person.key), person.name),
                "role": self._role(person.key),
                "mr": str(stat.mr_count),
                "merged": str(stat.merged_count),
                "score": self._score_cell(stat.score_avg),
                **{f"ko:{c}": str(stat.ko_counts.get(c, 0)) for c in self._criteria_ids},
                "direct": str(stat.direct_commits),
                "lead": (format_days(stat.lead_time_days), delay_details(stat.lead_times)),
                "merge_delay": (format_days(stat.merge_delay_days), delay_details(stat.merge_delays))
                if person.key in self._merge_repos else ("N/A", "Pas de droit de merge"),
            })
        self._person_grid.set_rows(rows)

    def _role(self, key: str) -> tuple[str, str]:
        """'Mergeur' with its repositories as tooltip, or 'Dev'."""
        repos = self._merge_repos.get(key)
        if not repos:
            return "Dev", ""
        return "Mergeur", "Peut merger sur :\n" + "\n".join(repos)

    def forget_avatars(self) -> None:
        self._images.clear()

    def restyle(self) -> None:
        self._person_grid.redraw()
        self._repo_grid.redraw()
        self.chart.redraw()
