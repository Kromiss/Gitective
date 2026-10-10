"""Per-person statistics, lead time and weekly score series."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from gitective.core.dates import week_key
from gitective.core.people import PersonRef
from gitective.core.rules import KO, Evaluation

GLOBAL_KEY = "__all__"


@dataclass
class PersonStats:
    """Aggregated figures for one person (one row of the Statistics tab)."""

    person: PersonRef
    mr_count: int = 0
    score_avg: float = 0.0
    ko_counts: dict[str, int] = field(default_factory=dict)
    lead_time_days: float | None = None


def average(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def per_person(evaluations: Sequence[Evaluation]) -> list[PersonStats]:
    """One PersonStats per MR author, sorted by name."""
    groups: dict[str, list[Evaluation]] = defaultdict(list)
    refs: dict[str, PersonRef] = {}
    for ev in evaluations:
        groups[ev.author.key].append(ev)
        refs[ev.author.key] = ev.author
    rows: list[PersonStats] = []
    for key, evs in groups.items():
        row = PersonStats(person=refs[key], mr_count=len(evs), score_avg=average(e.score for e in evs))
        for ev in evs:
            for criterion, result in ev.results.items():
                row.ko_counts.setdefault(criterion, 0)
                if result.status == KO:
                    row.ko_counts[criterion] += 1
        # Lead time only on merged MRs (ST-08).
        delays = [(e.mr.merged_at - e.mr.created_at).total_seconds() / 86400
                  for e in evs if e.mr.merged_at is not None]
        row.lead_time_days = average(delays) if delays else None
        rows.append(row)
    return sorted(rows, key=lambda r: r.person.name.casefold())


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
