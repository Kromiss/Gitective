"""Merge Requests filter bar (FI-01..FI-20); the state it edits lives in settings.filter_state."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from gitective.settings.filter_state import (
    DATED_STATES,
    DRAFT_LABELS,
    DRAFT_STATES,
    PEOPLE_STATES,
    STATES,
    FilterState,
)
from gitective.shared.dates import day_range, format_date, parse_date, since_yesterday
from gitective.ui.themes import Theme
from gitective.ui.components.widgets import MultiSelect


class MrFilterBar(ttk.Frame):
    """Card above the table: state, dates, Reset and Refresh on the first row; repositories,
    people, drafts and the text search on the second (FI-01..FI-20)."""

    def __init__(
        self,
        master: tk.Misc,
        filters: FilterState,
        get_theme: Callable[[], Theme],
        on_refresh: Callable[[], None],
        on_invalid: Callable[[str], None],
        on_search: Callable[[], None],
    ) -> None:
        super().__init__(master, style="Card.TFrame", padding=(14, 12))
        self.filters = filters
        self._on_invalid = on_invalid
        top = ttk.Frame(self, style="Bar.TFrame")
        top.pack(fill="x")
        bottom = ttk.Frame(self, style="Bar.TFrame")
        bottom.pack(fill="x", pady=(10, 0))

        self._state = tk.StringVar(value=filters.state)
        states = ttk.Frame(top, style="Bar.TFrame")
        states.pack(side="left")
        for value, text in STATES:
            ttk.Radiobutton(states, text=text, value=value, variable=self._state, style="Toolbutton",
                            command=self._state_changed).pack(side="left")

        self._from = tk.StringVar(value="" if filters.total else filters.date_from)
        self._to = tk.StringVar(value="" if filters.total else filters.date_to)
        self._date_entries: list[ttk.Entry] = []
        for index, var in enumerate((self._from, self._to)):
            if index:
                ttk.Label(top, text="→", style="BarMuted.TLabel").pack(side="left", padx=4)
            entry = ttk.Entry(top, textvariable=var, width=10)
            entry.pack(side="left", padx=(16 if not index else 0, 0))
            entry.bind("<Return>", lambda e: self._apply_dates())
            self._date_entries.append(entry)
        self._apply = ttk.Button(top, text="Appliquer", command=self._apply_dates)
        self._apply.pack(side="left", padx=(8, 0))
        self._yesterday = ttk.Button(top, text="Depuis hier", command=self._since_yesterday)
        self._yesterday.pack(side="left", padx=(8, 0))
        self._total = ttk.Button(top, text="Total", command=self._set_total)
        self._total.pack(side="left", padx=(6, 0))
        ttk.Button(top, text="⟳  Rafraîchir (F5)", style="Accent.TButton", command=on_refresh).pack(side="right")
        ttk.Button(top, text="↺ Réinitialiser les filtres", command=self._reset).pack(side="right", padx=(0, 8))

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
        # Text search, also by SHA prefix; never remembered (FI-12, FI-20).
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: on_search())
        ttk.Entry(bottom, textvariable=self.search, width=18).pack(side="right")
        ttk.Label(bottom, text="Rechercher", style="BarMuted.TLabel").pack(side="right", padx=(16, 6))

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
        self.filters.since_yesterday = self.filters.total = False
        self.filters.changed("period")

    def _since_yesterday(self) -> None:
        self.filters.since_yesterday, self.filters.total = True, False
        self._show_yesterday_dates()
        self.filters.changed("period")

    def _set_total(self) -> None:
        """No date limit: only the history missing from the base is read (FI-19, CH-04)."""
        self.filters.since_yesterday, self.filters.total = False, True
        self._from.set("")
        self._to.set("")
        self.filters.changed("period")

    def _reset(self) -> None:
        """Every filter back to its default, state, page size and sort kept (FI-18)."""
        self.search.set("")
        self.filters.reset()

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
        if what == "reset":
            self._show_yesterday_dates()
        self._total.state(["!disabled"] if dated else ["disabled"])
        self._yesterday.configure(style="Active.TButton" if self.filters.since_yesterday and dated else "TButton")
        self._total.configure(style="Active.TButton" if self.filters.total and dated else "TButton")
        self.authors.set_selected(self.filters.authors)
        self.mergers.set_selected(self.filters.mergers)
        self.assignees.set_selected(self.filters.assignees)
        self.reviewers.set_selected(self.filters.reviewers)
        self.repos.set_selected([str(r) for r in self.filters.repos])
