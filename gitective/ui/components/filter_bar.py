"""Shared filter state and the Merge Requests filter bar (FI-01..FI-17)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from gitective.settings.config_file import DRAFT_MODES, Filters
from gitective.shared.dates import Period, day_range, format_date, now_local, parse_date, since_yesterday
from gitective.ui.themes import Theme
from gitective.ui.components.widgets import MultiSelect

Listener = Callable[[str], None]

# "direct" lists the commits pushed without a merge request (CO-01).
STATES = (("merged", "Mergées"), ("opened", "Ouvertes"), ("closed", "Fermées"), ("direct", "Commits directs"))
DATED_STATES = ("merged", "direct")
PEOPLE_STATES = ("merged", "opened", "closed")  # assignee and reviewer filters (FI-14, FI-15)
DRAFT_STATES = ("opened", "closed")  # a merged MR is never a draft (FI-17)
DRAFT_LABELS = {"all": "Inclus", "exclude": "Exclus", "only": "Seulement"}


class FilterState:
    """Filters of the Merge Requests tab, partly shared with the Statistics tab.

    Listeners receive the name of what changed: 'state', 'period',
    'authors', 'mergers', 'assignees', 'reviewers', 'drafts', 'repos', or
    'badge' when a badge reset several of them at once (BA-02).
    """

    def __init__(self, saved: Filters) -> None:
        self.state = saved.state if saved.state in dict(STATES) else "merged"
        self.since_yesterday = saved.since_yesterday
        today = format_date(now_local().date())
        self.date_from = saved.date_from or today
        self.date_to = saved.date_to or today
        self.authors: list[str] = list(saved.authors)
        self.mergers: list[str] = list(saved.mergers)
        self.assignees: list[str] = list(saved.assignees)
        self.reviewers: list[str] = list(saved.reviewers)
        self.drafts = saved.drafts if saved.drafts in DRAFT_MODES else "all"
        self.repos: list[int] = [int(r) for r in saved.repos]
        self.page_size = saved.page_size
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def changed(self, what: str) -> None:
        for listener in list(self._listeners):
            listener(what)

    def period(self) -> Period:
        """Current date range; raises ValueError on a malformed date."""
        if self.since_yesterday:
            return since_yesterday()
        return day_range(parse_date(self.date_from), parse_date(self.date_to))

    def period_text(self) -> str:
        if self.since_yesterday:
            return "Depuis hier (hier 00:00 → maintenant)"
        return f"{self.date_from} → {self.date_to}"

    def to_settings(self) -> Filters:
        return Filters(state=self.state, since_yesterday=self.since_yesterday, date_from=self.date_from,
                       date_to=self.date_to, authors=list(self.authors), mergers=list(self.mergers),
                       assignees=list(self.assignees), reviewers=list(self.reviewers), drafts=self.drafts,
                       repos=list(self.repos), page_size=self.page_size)

    def show_mine(self, role: str, me_key: str) -> None:
        """Open MRs where the user has `role`, every other filter reset (BA-02)."""
        self.state = "opened"
        self.authors, self.repos, self.mergers = [], [], []
        self.assignees = [me_key] if role == "assignee" else []
        self.reviewers = [me_key] if role == "reviewer" else []
        self.drafts = "all"
        self.changed("badge")


class MrFilterBar(ttk.Frame):
    """State, dates and Refresh on the first row; repositories, people and drafts on the second."""

    def __init__(
        self,
        master: tk.Misc,
        filters: FilterState,
        get_theme: Callable[[], Theme],
        on_refresh: Callable[[], None],
        on_invalid: Callable[[str], None],
    ) -> None:
        super().__init__(master, style="Bar.TFrame", padding=(16, 10))
        self.filters = filters
        self._on_invalid = on_invalid
        top = ttk.Frame(self, style="Bar.TFrame")
        top.pack(fill="x")
        bottom = ttk.Frame(self, style="Bar.TFrame")
        bottom.pack(fill="x", pady=(10, 0))

        self._state = tk.StringVar(value=filters.state)
        states = ttk.Frame(top, style="Bar.TFrame")
        states.pack(side="left")
        ttk.Label(states, text="État", style="BarMuted.TLabel").pack(anchor="w")
        row = ttk.Frame(states, style="Bar.TFrame")
        row.pack()
        for value, text in STATES:
            ttk.Radiobutton(row, text=text, value=value, variable=self._state, style="Toolbutton",
                            command=self._state_changed).pack(side="left")

        self._from = tk.StringVar(value=filters.date_from)
        self._to = tk.StringVar(value=filters.date_to)
        self._date_entries: list[ttk.Entry] = []
        for label, var in (("Du", self._from), ("Au", self._to)):
            box = ttk.Frame(top, style="Bar.TFrame")
            box.pack(side="left", padx=(16, 0))
            ttk.Label(box, text=label, style="BarMuted.TLabel").pack(anchor="w")
            entry = ttk.Entry(box, textvariable=var, width=11)
            entry.pack()
            entry.bind("<Return>", lambda e: self._apply_dates())
            self._date_entries.append(entry)
        self._apply = ttk.Button(top, text="Appliquer", command=self._apply_dates)
        self._apply.pack(side="left", padx=(8, 0), anchor="s")
        self._yesterday = ttk.Button(top, text="Depuis hier", command=self._since_yesterday)
        self._yesterday.pack(side="left", padx=(8, 0), anchor="s")
        ttk.Button(top, text="⟳  Rafraîchir (F5)", style="Accent.TButton", command=on_refresh).pack(
            side="right", anchor="s")

        self.repos = MultiSelect(bottom, "Dépôts", self._repos_changed, get_theme)
        self.repos.pack(side="left")
        self.authors = MultiSelect(bottom, "Auteurs", self._authors_changed, get_theme, all_text="Toutes")
        self.authors.pack(side="left", padx=(8, 0))
        self.mergers = MultiSelect(bottom, "Mergeurs", self._mergers_changed, get_theme, all_text="Toutes")
        self.mergers.pack(side="left", padx=(8, 0))
        self.assignees = MultiSelect(bottom, "Assigné", self._assignees_changed, get_theme)
        self.assignees.pack(side="left", padx=(8, 0))
        self.reviewers = MultiSelect(bottom, "Relecteur", self._reviewers_changed, get_theme)
        self.reviewers.pack(side="left", padx=(8, 0))
        self._drafts = ttk.Menubutton(bottom)
        menu = tk.Menu(self._drafts, tearoff=False)
        self._draft_var = tk.StringVar(value=filters.drafts)
        for value, text in DRAFT_LABELS.items():
            menu.add_radiobutton(label=text, value=value, variable=self._draft_var, command=self._drafts_changed)
        self._drafts.configure(menu=menu)
        self._drafts.pack(side="left", padx=(8, 0))

        filters.subscribe(self._sync)
        if filters.since_yesterday:
            self._show_yesterday_dates()
        self._sync("state")

    def _state_changed(self) -> None:
        self.filters.state = self._state.get()
        self.filters.changed("state")

    def _apply_dates(self) -> None:
        try:
            day_range(parse_date(self._from.get()), parse_date(self._to.get()))
        except ValueError:
            self._on_invalid("Dates invalides : utilisez le format JJ/MM/AAAA, la date de fin après la date de début.")
            return
        self.filters.date_from = self._from.get().strip()
        self.filters.date_to = self._to.get().strip()
        self.filters.since_yesterday = False
        self.filters.changed("period")

    def _since_yesterday(self) -> None:
        self.filters.since_yesterday = True
        self._show_yesterday_dates()
        self.filters.changed("period")

    def _show_yesterday_dates(self) -> None:
        """Fill the date fields with yesterday and today for readability."""
        start, end = since_yesterday()
        self.filters.date_from = format_date(start.date())
        self.filters.date_to = format_date(end.date())
        self._from.set(self.filters.date_from)
        self._to.set(self.filters.date_to)

    def _repos_changed(self, keys: list[str]) -> None:
        self.filters.repos = [int(k) for k in keys]
        self.filters.changed("repos")

    def _authors_changed(self, keys: list[str]) -> None:
        self.filters.authors = keys
        self.filters.changed("authors")

    def _mergers_changed(self, keys: list[str]) -> None:
        self.filters.mergers = keys
        self.filters.changed("mergers")

    def _assignees_changed(self, keys: list[str]) -> None:
        self.filters.assignees = keys
        self.filters.changed("assignees")

    def _reviewers_changed(self, keys: list[str]) -> None:
        self.filters.reviewers = keys
        self.filters.changed("reviewers")

    def _drafts_changed(self) -> None:
        self.filters.drafts = self._draft_var.get()
        self.filters.changed("drafts")

    def _sync(self, what: str) -> None:
        """Reflect the shared state (also changed from other tabs or by a badge)."""
        state = self.filters.state
        self._state.set(state)
        dated = state in DATED_STATES
        for widget in (*self._date_entries, self._apply, self._yesterday):
            widget.state(["!disabled"] if dated else ["disabled"])
        # Only merged MRs have a merger (FI-13); direct commits have no assignee or reviewer (FI-14, FI-15).
        self.mergers.state(["!disabled"] if state == "merged" else ["disabled"])
        for widget in (self.assignees, self.reviewers):
            widget.state(["!disabled"] if state in PEOPLE_STATES else ["disabled"])
        self._drafts.state(["!disabled"] if state in DRAFT_STATES else ["disabled"])
        self._draft_var.set(self.filters.drafts)
        active = self.filters.drafts != "all" and state in DRAFT_STATES
        self._drafts.configure(text=f"Brouillons : {DRAFT_LABELS[self.filters.drafts]}  ▾",
                               style="Active.TMenubutton" if active else "TMenubutton")
        self._yesterday.configure(style="Accent.TButton" if self.filters.since_yesterday and dated else "TButton")
        self.authors.set_selected(self.filters.authors)
        self.mergers.set_selected(self.filters.mergers)
        self.assignees.set_selected(self.filters.assignees)
        self.reviewers.set_selected(self.filters.reviewers)
        self.repos.set_selected([str(r) for r in self.filters.repos])
