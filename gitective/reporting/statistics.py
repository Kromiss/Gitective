"""Per-person and per-repository statistics, lead time, merge delay and weekly score series."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from statistics import median

from gitective.shared.i18n import t
from gitective.shared.dates import business_days, week_key
from gitective.review.rules import KO, Evaluation
# admin:begin
from gitective.shared.people import PersonRef
# admin:end

GLOBAL_KEY = "__all__"


def average(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


# admin:begin
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
    direct_commits: int = 0  # commits pushed without MR (ST-15)

    @property
    def lead_time_days(self) -> float | None:
        return median(self.lead_times) if self.lead_times else None

    @property
    def merge_delay_days(self) -> float | None:
        return median(self.merge_delays) if self.merge_delays else None


def per_person(evaluations: Sequence[Evaluation], direct_authors: Sequence[PersonRef] = ()) -> list[PersonStats]:
    """One PersonStats per MR author or merger, or author of a direct commit, sorted by name."""
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
    for person in direct_authors:
        row(person).direct_commits += 1
    return sorted(rows.values(), key=lambda r: r.person.name.casefold())
# admin:end


@dataclass
class RepoStats:
    """Aggregated figures for one repository (SR-02)."""

    path: str
    mr_count: int = 0
    merged_count: int = 0
    score_avg: float | None = None  # None when no MR was created
    ko_counts: dict[str, int] = field(default_factory=dict)
    direct_commits: int = 0
    lead_times: list[float] = field(default_factory=list)

    @property
    def lead_time_days(self) -> float | None:
        return median(self.lead_times) if self.lead_times else None


def per_repo(
    evaluations: Sequence[Evaluation],
    repo_paths: Sequence[str],
    direct_repos: Sequence[str] = (),
) -> list[RepoStats]:
    """One RepoStats per repository of repo_paths, in that order (SR-01)."""
    rows = {path: RepoStats(path=path) for path in repo_paths}
    scores: dict[str, list[float]] = defaultdict(list)
    for ev in evaluations:
        row = rows.get(ev.project_path)
        if row is None:
            continue
        row.mr_count += 1
        scores[ev.project_path].append(ev.score)
        for criterion, result in ev.results.items():
            row.ko_counts[criterion] = row.ko_counts.get(criterion, 0) + (result.status == KO)
        if ev.mr.merged_at is not None:
            row.merged_count += 1
            row.lead_times.append(business_days(ev.mr.created_at, ev.mr.merged_at))
    for path, values in scores.items():
        rows[path].score_avg = average(values)
    for path in direct_repos:
        if path in rows:
            rows[path].direct_commits += 1
    return list(rows.values())


def delay_details(values: Sequence[float]) -> str:
    """Tooltip of a delay cell: average, minimum and maximum."""
    if not values:
        return ""
    return t("Moyenne : {average}\nMin : {min}\nMax : {max}\nSur {count} MR", average=format_days(average(values)),
             min=format_days(min(values)), max=format_days(max(values)), count=len(values))


def by_author(ev: Evaluation) -> str:
    return ev.author.key


def by_repo(ev: Evaluation) -> str:
    return ev.project_path


def weekly_scores(
    evaluations: Sequence[Evaluation],
    person_keys: Sequence[str],
    key_of: Callable[[Evaluation], str] = by_author,
) -> tuple[list[tuple[int, int]], dict[str, list[float | None]]]:
    """Average score per ISO week of creation (ST-09, ST-10, SR-04).

    Returns the sorted weeks and, for the global series and each requested
    key (a person by default, or a repository with key_of=by_repo), one value
    per week (None when that key had no MR that week).
    """
    buckets: dict[str, dict[tuple[int, int], list[float]]] = defaultdict(lambda: defaultdict(list))
    wanted = set(person_keys)
    for ev in evaluations:
        week = week_key(ev.mr.created_at)
        buckets[GLOBAL_KEY][week].append(ev.score)
        if key_of(ev) in wanted:
            buckets[key_of(ev)][week].append(ev.score)
    weeks = sorted(buckets[GLOBAL_KEY].keys())
    series: dict[str, list[float | None]] = {}
    for key in [GLOBAL_KEY, *person_keys]:
        per_week = buckets.get(key, {})
        series[key] = [average(per_week[w]) if per_week.get(w) else None for w in weeks]
    return weeks, series


def format_days(value: float | None) -> str:
    """Days with one decimal and a comma in both languages, e.g. '2,2 j' (LG-04)."""
    return "—" if value is None else t("{days} j", days=f"{value:.1f}".replace(".", ","))
