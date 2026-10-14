"""Projects visible to the token, kept in the local store so the picker opens instantly (SD-04)."""

from __future__ import annotations

from collections.abc import Sequence

from gitective.forge.models import Project
from gitective.shared.dates import format_datetime, now_local
from gitective.database.store import Store


def load_cached(store: Store) -> tuple[list[Project], str] | None:
    """Stored projects and their read date, or None when the list was never read."""
    read_at = store.get_meta("projects_read_at")
    if read_at is None:
        return None
    return store.projects(), read_at


def save_cached(store: Store, projects: Sequence[Project]) -> str:
    """Store the project list; return its read date."""
    read_at = format_datetime(now_local())
    store.put_projects(projects, read_at)
    return read_at
