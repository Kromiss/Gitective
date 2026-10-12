"""Per-person statistics, lead time, merge delay and weekly score series."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from statistics import median

from gitective.core.dates import business_days, week_key
from gitective.core.people import PersonRef
from gitective.core.rules import KO, Evaluation

GLOBAL_KEY = "__all__"


@dataclass
class PersonStats:
    """Aggregated figures for one person (one row of the Statistics tab).

    Delays are in business days (weekends excluded).
    """

    person: PersonRef
    mr_count: int = 0
    score_avg: float | None = None  # None when the person authored no MR
    ko_counts: dict[str, int] = field(default_factory=dict)
    merged_count: int = 0  # MRs this person merged (ST-13)
    lead_times: list[float] = field(default_factory=list)  # creation → merge of authored MRs (ST-08)
    merge_delays: list[float] = field(default_factory=list)  # last commit → merge of merged MRs (ST-12)

    @property
    def lead_time_days(self) -> float | None:
        return median(self.lead_times) if self.lead_times else None

    @property
    def merge_delay_days(self) -> float | None:
        return median(self.merge_delays) if self.merge_delays else None


def average(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def per_person(evaluations: Sequence[Evaluation]) -> list[PersonStats]:
    """One PersonStats per MR author or merger, sorted by name."""
    rows: dict[str, PersonStats] = {}

    def row(person: PersonRef) -> PersonStats:
        return rows.setdefault(person.key, PersonStats(person=person))

    scores: dict[str, list[float]] = defaultdict(list)
    for ev in evaluations:
        author = row(ev.author)
        author.mr_count += 1
        scores[ev.author.key].append(ev.score)
        for criterion, result in ev.results.items():
            author.ko_counts.setdefault(criterion, 0)
            if result.status == KO:
                author.ko_counts[criterion] += 1
        merged_at = ev.mr.merged_at
        if merged_at is None:
            continue
        author.lead_times.append(business_days(ev.mr.created_at, merged_at))
        if ev.merger is None:
            continue
        merger = row(ev.merger)
        merger.merged_count += 1
        if ev.last_commit_at is not None:
            merger.merge_delays.append(business_days(ev.last_commit_at, merged_at))
    for key, values in scores.items():
        rows[key].score_avg = average(values)
    return sorted(rows.values(), key=lambda r: r.person.name.casefold())


def delay_details(values: Sequence[float]) -> str:
    """Tooltip of a delay cell: average, minimum and maximum."""
    if not values:
        return ""
    return (f"Moyenne : {format_days(average(values))}\nMin : {format_days(min(values))}\n"
            f"Max : {format_days(max(values))}\nSur {len(values)} MR")


def weekly_scores(
    evaluations: Sequence[Evaluation],
    person_keys: Sequence[str],
) -> tuple[list[tuple[int, int]], dict[str, list[float | None]]]:
    """Average score per ISO week of creation (ST-09, ST-10).

    Returns the sorted weeks and, for the global series and each requested
    person, one value per week (None when that person had no MR that week).
    """
    buckets: dict[str, dict[tuple[int, int], list[float]]] = defaultdict(lambda: defaultdict(list))
    wanted = set(person_keys)
    for ev in evaluations:
        week = week_key(ev.mr.created_at)
        buckets[GLOBAL_KEY][week].append(ev.score)
        if ev.author.key in wanted:
            buckets[ev.author.key][week].append(ev.score)
    weeks = sorted(buckets[GLOBAL_KEY].keys())
    series: dict[str, list[float | None]] = {}
    for key in [GLOBAL_KEY, *person_keys]:
        per_week = buckets.get(key, {})
        series[key] = [average(per_week[w]) if per_week.get(w) else None for w in weeks]
    return weeks, series


def format_days(value: float | None) -> str:
    """Days with one decimal and a French comma, e.g. '2,2 j'."""
    return "—" if value is None else f"{value:.1f} j".replace(".", ",")
