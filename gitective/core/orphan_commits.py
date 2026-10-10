"""Detect commits pushed to a watched branch without any merge request."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from gitective.api.client import GitLabClient
from gitective.api.models import Commit
from gitective.config.settings import TrackedProject
from gitective.core.cache import SessionCache
from gitective.core.dates import Period
from gitective.core.parallel import run_parallel

ProgressCallback = Callable[[int, int], None]
MERGE_MARKER = "See merge request"


class BranchNotFoundError(Exception):
    """The watched branch of a project does not exist."""

    def __init__(self, project_path: str, branch: str) -> None:
        super().__init__(f"Branch '{branch}' not found in {project_path}")
        self.project_path = project_path
        self.branch = branch


@dataclass(frozen=True)
class OrphanCommit:
    """A commit with no associated merge request."""

    project: TrackedProject
    commit: Commit


def find_orphan_commits(
    client: GitLabClient,
    cache: SessionCache,
    projects: Sequence[TrackedProject],
    period: Period,
    progress: ProgressCallback | None = None,
    on_error: Callable[[Exception], None] | None = None,
    workers: int = 1,
) -> list[OrphanCommit]:
    """Check every commit of each watched branch within period.

    GitLab must be queried commit by commit (CO-08), `workers` at a time,
    hence the progress callback (done, total). Projects without a branch are skipped. A missing
    branch is reported through on_error and the other projects still run.
    """
    pending: list[tuple[TrackedProject, Commit]] = []
    for project in projects:
        if not project.branch:
            continue
        try:
            if not cache.get_or_load(("branch", project.id, project.branch),
                                     lambda p=project: client.branch_exists(p.id, p.branch)):
                raise BranchNotFoundError(project.path, project.branch)
            commits = cache.get_or_load(("commits", project.id, project.branch, period),
                                        lambda p=project: client.list_commits(p.id, p.branch, period[0], period[1]))
        except BranchNotFoundError as exc:
            if on_error is None:
                raise
            on_error(exc)
            continue
        # GitLab merge commits ("See merge request ...") belong to an MR (CO-05).
        pending.extend((project, c) for c in commits if not (c.is_merge and MERGE_MARKER in c.message))

    def has_mr(item: tuple[TrackedProject, Commit]) -> bool:
        project, commit = item
        return bool(cache.get_or_load(("commit-mr", project.id, commit.id),
                                      lambda: client.list_commit_merge_requests(project.id, commit.id)))

    flags = run_parallel(has_mr, pending, workers, progress)
    return [OrphanCommit(project, commit) for (project, commit), flag in zip(pending, flags) if not flag]
