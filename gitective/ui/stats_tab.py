"""Statistics tab: per-person figures, avatars and weekly chart (ST-01..ST-10)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from gitective.core.avatars import badge_color, initials
from gitective.core.dates import (
    Period,
    current_month,
    current_year,
    day_range,
    format_date,
    last_days,
    parse_date,
    week_label,
)
from gitective.core.merge_requests import evaluate_all, load_all_states, load_pairs
from gitective.core.rules import Evaluation, score_level
from gitective.core.stats import GLOBAL_KEY, PersonStats, format_days, per_person, weekly_scores
from gitective.ui.chart import Series, WeeklyChart
from gitective.ui.data_tab import DataTab
from gitective.ui.grid import Column, sort_rows
from gitective.ui.widgets import MultiSelect

if TYPE_CHECKING:
    from gitective.ui.app import App

AVATAR_PX = 26

HEAD_COLUMNS = [
    Column("person", "Personne", 220, kind="avatar", stretch=True),
    Column("mr", "MR", 60, align="e"),
    Column("score", "Score moyen", 96, kind="score", align="center"),
]
LEAD_COLUMN = Column("lead", "Délai création → merge", 150, align="e")

BASE_SORT: dict[str, Callable[[PersonStats], Any]] = {
    "person": lambda s: s.person.name.casefold(),
    "mr": lambda s: s.mr_count,
    "score": lambda s: s.score_avg,
    "lead": lambda s: s.lead_time_days,
}


class StatsTab(DataTab):
    """Aggregates every MR (any state, drafts excluded) per person."""

    table = "stats"

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master, app, sort_key="score", ascending=False)
        self._evaluations: list[Evaluation] = []
        self._stats: list[PersonStats] = []
        self._images: dict[int, tk.PhotoImage] = {}
        self._repos: list[int] = []
        start, end = last_days(30)
        self._from = tk.StringVar(value=format_date(start.date()))
        self._to = tk.StringVar(value=format_date(end.date()))
        self._total = False

        bar = ttk.Frame(self, style="Bar.TFrame", padding=(16, 10))
        bar.pack(fill="x")
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

        self.grid_view = self.make_grid(HEAD_COLUMNS, "Aucune merge request sur cette période")
        self.grid_view.pack(fill="both", expand=True, padx=16, pady=(12, 0))
        self.update_columns()
        self.chart = WeeklyChart(self, app.get_theme)
        self.chart.pack(fill="x", padx=16, pady=12)
        app.filters.subscribe(self._filters_changed)

    # ------------------------------------------------------------ Columns

    def update_columns(self) -> None:
        """One 'KO' column per active criterion (custom rules + fixed)."""
        criteria = self.app.rules.criteria if self.app.rules else []
        self._criteria_ids = [c.id for c in criteria]
        columns = [*HEAD_COLUMNS,
                   *(Column(f"ko:{c.id}", f"KO {c.label}", 60, align="e") for c in criteria),
                   LEAD_COLUMN]
        if self._sort_key not in self._sort_keys():
            self._sort_key, self._ascending = "score", False
        self.grid_view.set_columns(columns)
        self.grid_view.set_sort(self._sort_key, self._ascending)

    def _sort_keys(self) -> dict[str, Callable[[PersonStats], Any]]:
        keys = dict(BASE_SORT)
        for cid in self._criteria_ids:
            keys[f"ko:{cid}"] = lambda s, c=cid: s.ko_counts.get(c, 0)
        return keys

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
        client, cache, rules, people = self.app.client, self.app.cache, self.app.rules, self.app.people
        assert client is not None and rules is not None
        workers = self.app.settings.parallel_requests

        def task(progress: Callable[[int, int], None]) -> tuple[list[Evaluation], list[Exception]]:
            pairs, errors = load_pairs(projects, lambda p: load_all_states(client, cache, p, period))
            return evaluate_all(client, cache, pairs, rules, people, progress, workers), list(errors)

        self.app.runner.run("stats", task, self._loaded, self.app.report_error)

    def _loaded(self, result: tuple[list[Evaluation], list[Exception]]) -> None:
        evaluations, errors = result
        self.absorb(evaluations, errors)
        self._evaluations = evaluations
        self._apply_view()
        self._load_avatars()

    def _load_avatars(self) -> None:
        """Fetch avatars in the background, then redraw (AV-01, AV-05)."""
        wanted = {e.author.avatar_user_id for e in self._evaluations if e.author.avatar_user_id}
        wanted -= set(self._images)
        if not wanted:
            return
        store = self.app.avatars
        known = self.app.known_users

        def task(_progress: Callable[[int, int], None]) -> dict[int, Path]:
            found: dict[int, Path] = {}
            for user_id in wanted:
                user = known.get(user_id)
                path = store.path_for(user_id, user.avatar_url if user else None)
                if path:
                    found[user_id] = path
            return found

        self.app.runner.run("avatars", task, self._avatars_loaded, lambda e: None)

    def _avatars_loaded(self, paths: dict[int, Path]) -> None:
        for user_id, path in paths.items():
            image = self.app.load_avatar_image(path, AVATAR_PX)
            if image is not None:
                self._images[user_id] = image
        self._render()

    # --------------------------------------------------------------- View

    def _apply_view(self, reset_page: bool = False) -> None:
        authors = set(self.app.filters.authors)
        evaluations = [e for e in self._evaluations if not authors or e.author.key in authors]
        self._stats = sort_rows(per_person(evaluations), self._sort_keys()[self._sort_key], self._ascending)
        self._render()
        weeks, series = weekly_scores(evaluations, sorted(authors))
        names = {e.author.key: e.author.name for e in evaluations}
        curves = [Series("Global", series[GLOBAL_KEY], main=True)]
        curves += [Series(names.get(k, k), series[k]) for k in sorted(authors) if k in names]
        self.chart.set_data([week_label(w) for w in weeks], curves)

    def _render(self) -> None:
        settings = self.app.settings
        rows = []
        for stat in self._stats:
            person = stat.person
            image = self._images.get(person.avatar_user_id) if person.avatar_user_id else None
            rows.append({
                "person": (image, initials(person.name), badge_color(person.key), person.name),
                "mr": str(stat.mr_count),
                "score": (f"{stat.score_avg:.0f} %",
                          score_level(round(stat.score_avg, 6), settings.green_threshold, settings.orange_threshold)),
                **{f"ko:{c}": str(stat.ko_counts.get(c, 0)) for c in self._criteria_ids},
                "lead": format_days(stat.lead_time_days),
            })
        self.grid_view.set_rows(rows)

    def forget_avatars(self) -> None:
        self._images.clear()

    def restyle(self) -> None:
        super().restyle()
        self.chart.redraw()
