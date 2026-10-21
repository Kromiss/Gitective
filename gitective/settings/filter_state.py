"""Filters of the Merge Requests tab, independent of the interface (FI-01..FI-19)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from gitective.shared.i18n import t
from gitective.settings.config_file import DRAFT_MODES, Filters
from gitective.shared.dates import Period, day_range, format_date, now_local, parse_date, since_yesterday

Listener = Callable[[str], None]

# "direct" lists the commits pushed without a merge request (CO-01).
# "all" lists merged, open and closed MRs together (FI-21); "direct" the commits pushed without a merge request (CO-01).
STATES = (("merged", t("Mergées")), ("opened", t("Ouvertes")), ("closed", t("Fermées")), ("all", t("Toutes")),
          ("direct", t("Commits directs")))
DATED_STATES = ("merged", "all", "direct")  # "all" filters on the creation date (FI-21)
MERGER_STATES = ("merged", "all")  # merger filter (FI-13)
PEOPLE_STATES = ("merged", "opened", "closed", "all")  # assignee and reviewer filters (FI-14, FI-15)
DRAFT_STATES = ("opened", "closed", "all")  # a merged MR is never a draft (FI-17)
DRAFT_LABELS = {"all": t("Inclus"), "exclude": t("Exclus"), "only": t("Seulement")}


class FilterState:
    """Filters of the Merge Requests tab, partly shared with the Statistics tab.

    Listeners receive the name of what changed: 'state', 'period',
    'authors', 'mergers', 'assignees', 'reviewers', 'drafts', 'repos', or
    'badge' / 'reset' / 'focus' when a badge, the reset button or a merge
    clicked on the overview changed several of them at once (BA-02, FI-18, VE-14).
    """

    def __init__(self, saved: Filters) -> None:
        self.state = saved.state if saved.state in dict(STATES) else "merged"
        self.since_yesterday = saved.since_yesterday
        self.total = saved.total and not saved.since_yesterday  # no date limit (FI-19)
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

    def period(self) -> Period | None:
        """Current date range, None for "Total"; raises ValueError on a malformed date."""
        if self.total:
            return None
        if self.since_yesterday:
            return since_yesterday()
        return day_range(parse_date(self.date_from), parse_date(self.date_to))

    def period_text(self) -> str:
        if self.total:
            return t("Total (sans limite de date)")
        if self.since_yesterday:
            return t("Depuis hier (hier 00:00 → maintenant)")
        return f"{self.date_from} → {self.date_to}"

    def to_settings(self) -> Filters:
        return Filters(state=self.state, since_yesterday=self.since_yesterday, date_from=self.date_from,
                       date_to=self.date_to, total=self.total, authors=list(self.authors), mergers=list(self.mergers),
                       assignees=list(self.assignees), reviewers=list(self.reviewers), drafts=self.drafts,
                       repos=list(self.repos), page_size=self.page_size)

    def reset(self) -> None:
        """Every filter back to "all", dates to "Depuis hier"; state, page size and sort kept (FI-18)."""
        self.authors, self.mergers, self.assignees, self.reviewers, self.repos = [], [], [], [], []
        self.drafts = "all"
        self.since_yesterday, self.total = True, False
        self.changed("reset")

    def show_mine(self, role: str, me_key: str) -> None:
        """Open MRs where the user has `role`, every other filter reset (BA-02)."""
        self.state = "opened"
        self.repos, self.mergers = [], []
        self.authors = [me_key] if role == "author" else []
        self.assignees = [me_key] if role == "assignee" else []
        self.reviewers = [me_key] if role == "reviewer" else []
        self.drafts = "all"
        self.changed("badge")

    def show_merged_on(self, day: date) -> None:
        """Merged MRs of one day, every other filter reset: a merge clicked on the overview (VE-14)."""
        self.state = "merged"
        self.authors, self.mergers, self.assignees, self.reviewers, self.repos = [], [], [], [], []
        self.drafts = "all"
        self.since_yesterday = self.total = False
        self.date_from = self.date_to = format_date(day)
        self.changed("focus")
