"""Branches tab: state of each branch, exclusions, related MRs and the copied list (BR-02..BR-08)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from gitective.shared.i18n import t
from gitective.database.store import LinkedMr
from gitective.forge.models import Branch
from gitective.settings.config_file import TrackedProject
from gitective.shared.dates import format_date, to_local
from gitective.shared.people import PersonDirectory, PersonRef
from gitective.shared.repo_names import short_names

ACTIVE, DEAD, MERGED, DELETED = "active", "dead", "merged", "deleted"
STATE_LABELS = {ACTIVE: t("Active"), DEAD: t("Morte"), MERGED: t("Mergée non supprimée"), DELETED: t("Supprimée")}
STATE_ORDER = {DELETED: 0, MERGED: 1, DEAD: 2, ACTIVE: 3}  # priority of BR-04, also the sort order


@dataclass(frozen=True)
class BranchRow:
    """One line of the Branches tab."""

    project: TrackedProject
    branch: Branch
    author: PersonRef
    related: tuple[LinkedMr, ...]
    state: str
    age_days: int | None  # calendar days since the last commit
    deleted_at: datetime | None = None


def age_in_days(committed: datetime | None, now: datetime) -> int | None:
    """Calendar days between the last commit and now, in local time (BR-02)."""
    if committed is None:
        return None
    return (to_local(now).date() - to_local(committed).date()).days


def branch_state(branch: Branch, related: Sequence[LinkedMr], age: int | None, dead_days: int,
                 deleted: bool) -> str:
    """Single state by priority: deleted, merged not deleted, dead, active (BR-04)."""
    if deleted:
        return DELETED
    if branch.merged or any(mr.state == "merged" for mr in related):
        return MERGED
    if age is not None and age > dead_days:
        return DEAD
    return ACTIVE


def is_excluded(branch: Branch, pattern: re.Pattern[str] | None) -> bool:
    """Default branch, protected branches and names matching the exclusion regex are hidden (BR-05)."""
    return branch.default or branch.protected or bool(pattern and pattern.search(branch.name))


def exclusion_pattern(regex: str) -> re.Pattern[str] | None:
    """Case-insensitive exclusion regex; None when empty or invalid (Config refuses invalid ones, OC-07)."""
    try:
        return re.compile(regex, re.IGNORECASE) if regex.strip() else None
    except re.error:
        return None


def related_mrs(mrs: Iterable[LinkedMr], project_id: int, branch: str) -> tuple[LinkedMr, ...]:
    """MRs of the same repository whose source branch is this branch: open first, then newest (BR-03)."""
    found = [m for m in mrs if m.project_id == project_id and m.source_branch == branch]
    found.sort(key=lambda m: m.created_at, reverse=True)
    found.sort(key=lambda m: m.state != "opened")
    return tuple(found)


def build_rows(
    stored: Iterable[tuple[int, Branch, float | None]],
    projects: Sequence[TrackedProject],
    mrs: Sequence[LinkedMr],
    people: PersonDirectory,
    exclude_regex: str,
    dead_days: int,
    now: datetime,
) -> list[BranchRow]:
    """Every shown branch of the tracked repositories, with its state and related MRs."""
    by_id = {p.id: p for p in projects}
    pattern = exclusion_pattern(exclude_regex)
    index: dict[tuple[int, str], list[LinkedMr]] = {}
    for mr in mrs:
        index.setdefault((mr.project_id, mr.source_branch), []).append(mr)
    rows = []
    for project_id, branch, deleted_at in stored:
        project = by_id.get(project_id)
        if project is None or is_excluded(branch, pattern):
            continue
        related = related_mrs(index.get((project_id, branch.name), []), project_id, branch.name)
        age = age_in_days(branch.committed_date, now)
        deleted = datetime.fromtimestamp(deleted_at).astimezone() if deleted_at is not None else None
        rows.append(BranchRow(
            project=project, branch=branch, author=people.for_git(branch.author_name, branch.author_email),
            related=related, state=branch_state(branch, related, age, dead_days, deleted is not None),
            age_days=age, deleted_at=deleted))
    return rows


def last_commit_text(row: BranchRow) -> str:
    """"12/09/2026 (34 j)" (BR-02)."""
    if row.branch.committed_date is None:
        return ""
    return f"{format_date(to_local(row.branch.committed_date).date())} ({t('{days} j', days=row.age_days)})"


def related_text(row: BranchRow) -> str:
    return ", ".join(f"!{mr.iid}" for mr in row.related)


def copied_list(rows: Sequence[BranchRow]) -> str:
    """Markdown text of the filtered branches, grouped by author, to send reminders (BR-08)."""
    names = short_names(r.project.path for r in rows)
    groups: dict[str, list[BranchRow]] = {}
    for row in sorted(rows, key=lambda r: r.author.name.casefold()):
        groups.setdefault(row.author.name, []).append(row)
    blocks = []
    for name, items in groups.items():
        lines = [f"## {name}", ""]
        for row in items:
            parts = [names[row.project.path], row.branch.name, last_commit_text(row),
                     STATE_LABELS[row.state]]
            if row.related:
                parts.append(related_text(row))
            lines.append("- " + " · ".join(p for p in parts if p))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n" if blocks else ""
