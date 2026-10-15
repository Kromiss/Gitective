"""Read merge requests through the local store and evaluate them."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from gitective.forge.errors import ForgeError
from gitective.forge.models import Commit, CommitStatus, MergeRequest
from gitective.settings.config_file import TrackedProject
from gitective.shared.dates import Period, in_period, now_local
from gitective.shared.parallel import run_parallel
from gitective.shared.people import PersonDirectory
from gitective.review.rules import Evaluation, RuleSet
from gitective.database.sync import ForgeData

Pair = tuple[TrackedProject, MergeRequest]
Progress = Callable[[int, int], None]


def load_merge_requests(
    data: ForgeData,
    project: TrackedProject,
    state: str,
    period: Period | None,
) -> list[MergeRequest]:
    """MRs of one project in a given state.

    Merged MRs are filtered on their merge date; open and closed MRs are the
    complete lists (FI-05), drafts included: the tab marks and filters them
    (FI-08, FI-16). A merge always updates the MR, so the MRs updated since
    the start of the period include every MR merged in it.
    """
    since = period[0] if state == "merged" and period else now_local()
    start = period[0] if state == "merged" and period else None
    mrs = data.merge_requests(project.id, since, state=state, merged_after=start)
    if state == "merged":
        return [m for m in mrs if m.state == "merged" and not m.draft and in_period(m.merged_at, period)]
    return [m for m in mrs if m.state == state]


def load_all_states(
    data: ForgeData,
    project: TrackedProject,
    period: Period | None,
) -> list[MergeRequest]:
    """MRs of every state created within period (None = all time), drafts excluded."""
    start = period[0] if period else None
    mrs = data.merge_requests(project.id, start, created_after=start)
    return [m for m in mrs if not m.draft and in_period(m.created_at, period)]


def load_pairs(
    projects: Sequence[TrackedProject],
    loader: Callable[[TrackedProject], list[MergeRequest]],
) -> tuple[list[Pair], list[ForgeError]]:
    """Load the MRs of each project; a failing project is reported, not fatal (ER-03)."""
    pairs: list[Pair] = []
    errors: list[ForgeError] = []
    for project in projects:
        try:
            pairs.extend((project, mr) for mr in loader(project))
        except ForgeError as exc:
            errors.append(exc)
    return pairs, errors


def evaluate_all(
    data: ForgeData,
    pairs: Sequence[Pair],
    rules: RuleSet,
    people: PersonDirectory,
    progress: Progress | None = None,
    workers: int = 1,
    merged_commits: bool = False,
) -> list[Evaluation]:
    """Evaluate every (project, MR) pair.

    Extra data is read per MR, `workers` at a time, and kept in the store:
    commits when a rule inspects commit messages (RP-04) or, for merged MRs,
    when `merged_commits` is set (merge delay, ST-12); CI statuses of merged
    MRs of repositories expecting a CI (RC-05).
    """
    def load(pair: Pair) -> tuple[list[Commit] | None, list[CommitStatus] | None]:
        project, mr = pair
        commits = statuses = None
        if rules.needs_commits or (merged_commits and mr.merged_at):
            commits = data.mr_commits(project.id, mr)
        if project.ci_expected and mr.merged_at:
            statuses = data.mr_statuses(project.id, mr)
        return commits, statuses

    extras: list[tuple[list[Commit] | None, list[CommitStatus] | None]] = [(None, None)] * len(pairs)
    if any(rules.needs_commits or (p.ci_expected or merged_commits) and m.merged_at for p, m in pairs):
        extras = run_parallel(load, pairs, workers, progress)
    return [rules.evaluate(mr, project.path, people, commits, statuses, project.ci_expected)
            for (project, mr), (commits, statuses) in zip(pairs, extras)]
