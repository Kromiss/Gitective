"""Load merge requests from GitLab (with caching) and evaluate them."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from gitective.api.client import GitLabClient
from gitective.api.errors import GitLabError
from gitective.api.models import Commit, MergeRequest
from gitective.config.settings import TrackedProject
from gitective.core.cache import SessionCache
from gitective.core.dates import Period, in_period
from gitective.core.parallel import run_parallel
from gitective.core.people import PersonDirectory
from gitective.core.rules import Evaluation, RuleSet

# Application state names mapped to GitLab API states.
API_STATES = {"merged": "merged", "opened": "opened", "closed": "closed"}

Pair = tuple[TrackedProject, MergeRequest]
Progress = Callable[[int, int], None]


def load_merge_requests(
    client: GitLabClient,
    cache: SessionCache,
    project: TrackedProject,
    state: str,
    period: Period | None,
) -> list[MergeRequest]:
    """MRs of one project in a given state, drafts excluded (FI-08).

    Merged MRs are filtered on their merge date. GitLab has no reliable
    "merged after" filter, so updated_after narrows the query (a merge always
    updates the MR) and the exact merge date is checked locally.
    """
    if state == "merged":
        key = ("mr", project.id, state, period)
        mrs = cache.get_or_load(key, lambda: client.list_merge_requests(
            project.id, state="merged", updated_after=period[0] if period else None))
        mrs = [m for m in mrs if in_period(m.merged_at, period)]
    else:
        key = ("mr", project.id, state, None)
        mrs = cache.get_or_load(key, lambda: client.list_merge_requests(project.id, state=API_STATES[state]))
    return [m for m in mrs if not m.draft]


def load_all_states(
    client: GitLabClient,
    cache: SessionCache,
    project: TrackedProject,
    period: Period | None,
) -> list[MergeRequest]:
    """MRs of every state created within period (None = all time), drafts excluded."""
    key = ("mr-all", project.id, period)
    mrs = cache.get_or_load(key, lambda: client.list_merge_requests(
        project.id,
        created_after=period[0] if period else None,
        created_before=period[1] if period else None,
    ))
    return [m for m in mrs if not m.draft and in_period(m.created_at, period)]


def load_pairs(
    projects: Sequence[TrackedProject],
    loader: Callable[[TrackedProject], list[MergeRequest]],
) -> tuple[list[Pair], list[GitLabError]]:
    """Load the MRs of each project; a failing project is reported, not fatal (ER-03)."""
    pairs: list[Pair] = []
    errors: list[GitLabError] = []
    for project in projects:
        try:
            pairs.extend((project, mr) for mr in loader(project))
        except GitLabError as exc:
            errors.append(exc)
    return pairs, errors


def evaluate_all(
    client: GitLabClient,
    cache: SessionCache,
    pairs: Sequence[Pair],
    rules: RuleSet,
    people: PersonDirectory,
    progress: Progress | None = None,
    workers: int = 1,
    merged_commits: bool = False,
) -> list[Evaluation]:
    """Evaluate every (project, MR) pair.

    Commits are fetched when a rule inspects commit messages (RP-04), and for
    merged MRs when `merged_commits` is set (merge delay, ST-12): one request
    per MR, run `workers` at a time and cached for the session.
    """
    def load(pair: Pair) -> list[Commit] | None:
        project, mr = pair
        if not (rules.needs_commits or (merged_commits and mr.merged_at)):
            return None
        return cache.get_or_load(("mr-commits", project.id, mr.iid),
                                 lambda: client.list_merge_request_commits(project.id, mr.iid))

    commits: list[list[Commit] | None] = [None] * len(pairs)
    if rules.needs_commits or merged_commits:
        commits = run_parallel(load, pairs, workers, progress)
    return [rules.evaluate(mr, project.path, people, mr_commits)
            for (project, mr), mr_commits in zip(pairs, commits)]
