"""Shared filter state and the Merge Requests filter bar (FI-01..FI-11)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from gitective.config.settings import Filters
from gitective.core.dates import Period, day_range, format_date, now_local, parse_date, since_yesterday
from gitective.ui.themes import Theme
from gitective.ui.widgets import MultiSelect

Listener = Callable[[str], None]


class FilterState:
    """Filters shared by the Merge Requests and Commits tabs.

    Listeners receive the name of what changed: 'state', 'period',
    'authors' or 'repos'.
    """

    def __init__(self, saved: Filters) -> None:
        self.state = saved.state if saved.state in ("merged", "opened", "closed") else "merged"
        self.since_yesterday = saved.since_yesterday
        today = format_date(now_local().date())
        self.date_from = saved.date_from or today
        self.date_to = saved.date_to or today
        self.authors: list[str] = list(saved.authors)
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
                       date_to=self.date_to, authors=list(self.authors), repos=list(self.repos),
                       page_size=self.page_size)


class MrFilterBar(ttk.Frame):
    """State, dates, repositories, authors and Refresh controls."""

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

        self._state = tk.StringVar(value=filters.state)
        states = ttk.Frame(self, style="Bar.TFrame")
        states.pack(side="left")
        ttk.Label(states, text="État", style="BarMuted.TLabel").pack(anchor="w")
        row = ttk.Frame(states, style="Bar.TFrame")
        row.pack()
        for value, text in (("merged", "Mergées"), ("opened", "Ouvertes"), ("closed", "Fermées")):
            ttk.Radiobutton(row, text=text, value=value, variable=self._state, style="Toolbutton",
                            command=self._state_changed).pack(side="left")

        self._from = tk.StringVar(value=filters.date_from)
        self._to = tk.StringVar(value=filters.date_to)
        self._date_entries: list[ttk.Entry] = []
        for label, var in (("Du", self._from), ("Au", self._to)):
            box = ttk.Frame(self, style="Bar.TFrame")
            box.pack(side="left", padx=(16, 0))
            ttk.Label(box, text=label, style="BarMuted.TLabel").pack(anchor="w")
            entry = ttk.Entry(box, textvariable=var, width=11)
            entry.pack()
            entry.bind("<Return>", lambda e: self._apply_dates())
            self._date_entries.append(entry)
        self._apply = ttk.Button(self, text="Appliquer", command=self._apply_dates)
        self._apply.pack(side="left", padx=(8, 0), anchor="s")
        self._yesterday = ttk.Button(self, text="Depuis hier", command=self._since_yesterday)
        self._yesterday.pack(side="left", padx=(8, 0), anchor="s")

        self.repos = MultiSelect(self, "Dépôts", self._repos_changed, get_theme)
        self.repos.pack(side="left", padx=(16, 0), anchor="s")
        self.authors = MultiSelect(self, "Auteurs", self._authors_changed, get_theme, all_text="Toutes")
        self.authors.pack(side="left", padx=(8, 0), anchor="s")
        self.repos.set_selected([str(r) for r in filters.repos])
        self.authors.set_selected(filters.authors)

        ttk.Button(self, text="⟳  Rafraîchir (F5)", style="Accent.TButton", command=on_refresh).pack(
            side="right", anchor="s")
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

    def _sync(self, what: str) -> None:
        """Reflect the shared state (also changed from other tabs)."""
        merged = self.filters.state == "merged"
        for widget in (*self._date_entries, self._apply, self._yesterday):
            widget.state(["!disabled"] if merged else ["disabled"])
        self._yesterday.configure(style="Accent.TButton" if self.filters.since_yesterday and merged else "TButton")
        if what == "authors":
            self.authors.set_selected(self.filters.authors)
        if what == "repos":
            self.repos.set_selected([str(r) for r in self.filters.repos])
