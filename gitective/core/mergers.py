"""Who can merge into the watched branch of each tracked repository (ST-11)."""

from __future__ import annotations

import fnmatch
from collections.abc import Sequence

from gitective.api.client import GitLabClient
from gitective.api.errors import GitLabError
from gitective.api.models import ProtectedBranch, User
from gitective.config.settings import TrackedProject
from gitective.core.cache import SessionCache
from gitective.core.parallel import run_parallel

DEVELOPER = 30  # GitLab role allowed to merge into an unprotected branch


def can_merge(members: Sequence[tuple[User, int]], protections: Sequence[ProtectedBranch], branch: str) -> list[User]:
    """Members allowed to merge into `branch`, according to its protection rules."""
    rules = [r for r in protections if fnmatch.fnmatchcase(branch, r.name)]
    if not rules:
        return [user for user, level in members if level >= DEVELOPER]
    # Several matching rules: GitLab applies the most permissive one.
    levels = [level for r in rules for level in r.merge_levels if level > 0]
    users = {uid for r in rules for uid in r.merge_user_ids}
    # shortcut: group-based merge rights (Premium) are ignored; add them if a team relies on them.
    return [user for user, level in members if (levels and level >= min(levels)) or user.id in users]


def merge_rights(
    client: GitLabClient,
    cache: SessionCache,
    projects: Sequence[TrackedProject],
    workers: int,
) -> tuple[dict[User, list[str]], list[GitLabError]]:
    """Account → paths of the projects whose watched branch it can merge into.

    Projects without a watched branch are skipped; a failing project is
    reported, not fatal (ER-03).
    """
    def load(project: TrackedProject) -> list[User] | GitLabError:
        try:
            members, protections = cache.get_or_load(
                ("merge_rights", project.id),
                lambda: (client.list_project_members(project.id), client.list_protected_branches(project.id)))
        except GitLabError as exc:
            return exc
        return can_merge(members, protections, project.branch)

    targets = [p for p in projects if p.branch]
    rights: dict[User, list[str]] = {}
    errors: list[GitLabError] = []
    for project, result in zip(targets, run_parallel(load, targets, workers)):
        if isinstance(result, GitLabError):
            errors.append(result)
            continue
        for user in result:
            rights.setdefault(user, []).append(project.path)
    return rights, errors
