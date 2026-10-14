"""Detect commits pushed to a watched branch without any merge request."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from gitective.forge.models import Commit
from gitective.settings.config_file import TrackedProject
from gitective.shared.dates import Period
from gitective.shared.parallel import run_parallel
from gitective.database.sync import ForgeData

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
    data: ForgeData,
    projects: Sequence[TrackedProject],
    period: Period,
    progress: ProgressCallback | None = None,
    on_error: Callable[[Exception], None] | None = None,
    workers: int = 1,
) -> list[OrphanCommit]:
    """Check every commit of each watched branch within period.

    Only commits never checked before are sent to the forge, one request
    each, `workers` at a time; the answer is stored for good (CO-08).
    Projects without a branch are skipped. A missing branch is reported
    through on_error and the other projects still run.
    """
    pending: list[tuple[TrackedProject, Commit]] = []
    for project in projects:
        if not project.branch:
            continue
        try:
            if not data.branch_exists(project.id, project.branch):
                raise BranchNotFoundError(project.path, project.branch)
            commits = data.branch_commits(project.id, project.branch, period[0], period[1])
        except BranchNotFoundError as exc:
            if on_error is None:
                raise
            on_error(exc)
            continue
        # GitLab merge commits ("See merge request ...") belong to an MR (CO-05).
        pending.extend((project, c) for c in commits if not (c.is_merge and MERGE_MARKER in c.message))

    def has_mr(item: tuple[TrackedProject, Commit]) -> bool:
        project, commit = item
        return data.commit_has_mr(project.id, commit.id)

    flags = run_parallel(has_mr, pending, workers, progress)
    return [OrphanCommit(project, commit) for (project, commit), flag in zip(pending, flags) if not flag]
