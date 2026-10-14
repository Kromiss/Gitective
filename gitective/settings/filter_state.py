"""Filters of the Merge Requests tab, independent of the interface (FI-01..FI-17)."""

from __future__ import annotations

from collections.abc import Callable

from gitective.settings.config_file import DRAFT_MODES, Filters
from gitective.shared.dates import Period, day_range, format_date, now_local, parse_date, since_yesterday

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
