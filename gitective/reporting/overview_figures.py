"""Figures of the Overview tab: latest merges, daily merges, scores and weekly trends (VE-05..VE-11)."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from gitective.forge.models import MergeRequest
from gitective.shared.dates import start_of_day, to_local, week_key, week_label
from gitective.review.rules import KO, Criterion, Evaluation, score_level
from gitective.reporting.statistics import average

FEED_SIZE = 40  # enough for a busy day (10 to 15 merges) plus the previous ones
# Latest merges rows (VE-05): two lines per merge, or one line when today's merges would not all fit.
GROUP_H, ROW_H, COMPACT_ROW_H = 28, 58, 30
TITLE_MAX = 45  # characters of an MR title in the feed, so the repository and people always show
SCORE_DAYS = 30
WEEKS = 12


@dataclass(frozen=True)
class WeekQuality:
    """Merged MRs of one week split by score level (VE-08)."""

    label: str
    green: int
    orange: int
    red: int

    @property
    def total(self) -> int:
        return self.green + self.orange + self.red


@dataclass
class OverviewData:
    """Everything the Overview tab draws, computed from evaluated merged MRs."""

    feed: list[Evaluation] = field(default_factory=list)
    today_count: int = 0
    this_week: list[int | None] = field(default_factory=list)  # Monday → Sunday, None = day to come
    last_week: list[int] = field(default_factory=list)
    score: float | None = None
    previous_score: float | None = None
    merged_count: int = 0
    quality: list[WeekQuality] = field(default_factory=list)
    repos: list[tuple[str, float | None]] = field(default_factory=list)  # best first, no MR last
    kos: list[tuple[str, int]] = field(default_factory=list)  # most frequent first
    week_labels: list[str] = field(default_factory=list)
    created: list[int] = field(default_factory=list)
    merged: list[int] = field(default_factory=list)


def week_start(now: datetime) -> datetime:
    """Monday 00:00 (local time) of the week containing now."""
    today = to_local(now).date()
    return start_of_day(today - timedelta(days=today.weekday()))


def load_start(now: datetime) -> datetime:
    """Oldest date needed: Monday of the first of the WEEKS complete weeks."""
    return week_start(now) - timedelta(weeks=WEEKS)


def build_overview(
    merged: Sequence[Evaluation],
    created: Sequence[MergeRequest],
    repo_paths: Sequence[str],
    criteria: Sequence[Criterion],
    green: float,
    orange: float,
    now: datetime,
) -> OverviewData:
    """Aggregate merged MR evaluations and created MRs into the overview figures."""
    data = OverviewData()
    done = sorted((e for e in merged if e.mr.merged_at), key=lambda e: e.mr.merged_at, reverse=True)  # type: ignore[arg-type, return-value]
    today = to_local(now).date()
    monday = week_start(now).date()

    def day_of(ev: Evaluation) -> date:
        return to_local(ev.mr.merged_at).date()  # type: ignore[arg-type]

    # Latest merges and merges per day (VE-05, VE-06).
    data.feed = done[:FEED_SIZE]
    per_day = Counter(day_of(e) for e in done)
    data.today_count = per_day[today]
    data.this_week = [per_day[d] if d <= today else None for d in (monday + timedelta(days=i) for i in range(7))]
    data.last_week = [per_day[monday - timedelta(days=7 - i)] for i in range(7)]

    # Average score over the last SCORE_DAYS days and the period before (VE-07).
    recent_start = now - timedelta(days=SCORE_DAYS)
    previous_start = recent_start - timedelta(days=SCORE_DAYS)
    recent = [e for e in done if e.mr.merged_at >= recent_start]  # type: ignore[operator]
    previous = [e for e in done if previous_start <= e.mr.merged_at < recent_start]  # type: ignore[operator]
    data.score = average(e.score for e in recent) if recent else None
    data.previous_score = average(e.score for e in previous) if previous else None
    data.merged_count = len(recent)

    # Repository ranking (VE-09) and broken rules (VE-10) over the same window.
    by_repo: dict[str, list[float]] = defaultdict(list)
    for ev in recent:
        by_repo[ev.project_path].append(ev.score)
    ranked = sorted(((p, average(by_repo[p])) for p in repo_paths if by_repo.get(p)), key=lambda r: -r[1])
    data.repos = [*ranked, *((p, None) for p in repo_paths if not by_repo.get(p))]
    ko = Counter(c for ev in recent for c, r in ev.results.items() if r.status == KO)
    data.kos = sorted(((c.label, ko[c.id]) for c in criteria), key=lambda k: -k[1])

    # Weekly quality and flow over the WEEKS complete weeks (VE-08, VE-11).
    weeks = [week_key(start_of_day(monday - timedelta(weeks=WEEKS - i))) for i in range(WEEKS)]
    levels: dict[tuple[int, int], Counter[str]] = defaultdict(Counter)
    for ev in done:
        levels[week_key(ev.mr.merged_at)][score_level(round(ev.score, 6), green, orange)] += 1  # type: ignore[arg-type]
    created_per_week = Counter(week_key(mr.created_at) for mr in created if not mr.draft)
    data.week_labels = [week_label(w) for w in weeks]
    data.quality = [WeekQuality(week_label(w), levels[w]["green"], levels[w]["orange"], levels[w]["red"])
                    for w in weeks]
    data.merged = [levels[w].total() for w in weeks]
    data.created = [created_per_week[w] for w in weeks]
    return data


def feed_row_height(today_count: int, room: float) -> int:
    """Row height of the latest merges feed: compact as soon as two-line rows would hide some of today's merges."""
    return ROW_H if GROUP_H + today_count * ROW_H <= room else COMPACT_ROW_H


def short_title(title: str, limit: int = TITLE_MAX) -> str:
    """MR title cut to `limit` characters with an ellipsis, on a word boundary when one is close."""
    title = " ".join(title.split())
    if len(title) <= limit:
        return title
    cut = title[: limit - 1]
    space = cut.rfind(" ")
    if space >= limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" -:·") + "…"
