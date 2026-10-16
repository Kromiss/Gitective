"""Tags tab: rows, filters and what the detail panel shows (TG-02..TG-07)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from gitective.forge.models import Tag
from gitective.settings.config_file import TrackedProject
from gitective.shared.dates import Period, in_period
from gitective.shared.people import PersonDirectory, PersonRef
from gitective.shared.search import matches, sha_hit


@dataclass(frozen=True)
class TagRow:
    """One line of the Tags tab."""

    project: TrackedProject
    tag: Tag
    author: PersonRef
    deleted_at: datetime | None = None

    @property
    def web_url(self) -> str:
        return f"{self.project.web_url.rstrip('/')}/-/tags/{self.tag.name}" if self.project.web_url else ""

    @property
    def commit_url(self) -> str:
        return f"{self.project.web_url.rstrip('/')}/-/commit/{self.tag.commit_sha}" if self.project.web_url else ""


def first_line(text: str) -> str:
    """First non-empty line, for the Message and Notes columns (TG-03)."""
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def build_rows(stored: Iterable[tuple[int, Tag, float | None]], projects: Sequence[TrackedProject],
               people: PersonDirectory) -> list[TagRow]:
    """Tags of the tracked repositories, deleted ones included (TG-05)."""
    by_id = {p.id: p for p in projects}
    return [TagRow(project=by_id[pid], tag=tag, author=people.for_git(tag.author_name, tag.author_email),
                   deleted_at=datetime.fromtimestamp(deleted).astimezone() if deleted is not None else None)
            for pid, tag, deleted in stored if pid in by_id]


def visible_tags(rows: Iterable[TagRow], repos: Sequence[int], needle: str, period: Period | None) -> list[TagRow]:
    """Tags kept by the repository, text (name, message, notes, SHA prefix) and period filters (TG-04)."""
    wanted = set(repos)
    folded = needle.strip().casefold()
    return [r for r in rows
            if (not wanted or r.project.id in wanted)
            and (period is None or in_period(r.tag.committed_date, period))
            and (matches(folded, r.tag.name, r.tag.message, r.tag.release_notes, r.tag.release_name)
                 or sha_hit(folded, [("commit", r.tag.commit_sha)]) is not None)]
