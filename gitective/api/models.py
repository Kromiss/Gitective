"""Typed GitLab objects returned by GitLabClient."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def parse_datetime(value: str | None) -> datetime | None:
    """Parse a GitLab ISO 8601 timestamp into an aware datetime."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class User:
    """A GitLab user account."""

    id: int
    username: str
    name: str
    avatar_url: str | None = None
    web_url: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> User:
        return cls(
            id=int(data["id"]),
            username=data.get("username", ""),
            name=data.get("name", "") or data.get("username", ""),
            avatar_url=data.get("avatar_url"),
            web_url=data.get("web_url"),
        )


@dataclass(frozen=True)
class Project:
    """A GitLab project (repository)."""

    id: int
    name: str
    path_with_namespace: str
    web_url: str
    default_branch: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Project:
        return cls(
            id=int(data["id"]),
            name=data.get("name", ""),
            path_with_namespace=data.get("path_with_namespace", data.get("name", "")),
            web_url=data.get("web_url", ""),
            default_branch=data.get("default_branch"),
        )


@dataclass(frozen=True)
class MergeRequest:
    """A GitLab merge request."""

    id: int
    iid: int
    project_id: int
    title: str
    description: str
    state: str
    draft: bool
    author: User
    merged_by: User | None
    created_at: datetime
    merged_at: datetime | None
    closed_at: datetime | None
    updated_at: datetime | None
    web_url: str
    source_branch: str = ""
    target_branch: str = ""
    merge_commit_sha: str | None = None
    squash_commit_sha: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> MergeRequest:
        # "merge_user" replaces the deprecated "merged_by" on recent GitLab versions.
        merger = data.get("merge_user") or data.get("merged_by")
        created = parse_datetime(data.get("created_at"))
        assert created is not None
        return cls(
            id=int(data["id"]),
            iid=int(data["iid"]),
            project_id=int(data["project_id"]),
            title=data.get("title", "") or "",
            description=data.get("description", "") or "",
            state=data.get("state", ""),
            draft=bool(data.get("draft", data.get("work_in_progress", False))),
            author=User.from_json(data["author"]),
            merged_by=User.from_json(merger) if merger else None,
            created_at=created,
            merged_at=parse_datetime(data.get("merged_at")),
            closed_at=parse_datetime(data.get("closed_at")),
            updated_at=parse_datetime(data.get("updated_at")),
            web_url=data.get("web_url", ""),
            source_branch=data.get("source_branch", "") or "",
            target_branch=data.get("target_branch", "") or "",
            merge_commit_sha=data.get("merge_commit_sha"),
            squash_commit_sha=data.get("squash_commit_sha"),
        )


@dataclass(frozen=True)
class Commit:
    """A Git commit as exposed by GitLab."""

    id: str
    short_id: str
    title: str
    message: str
    author_name: str
    author_email: str
    committed_date: datetime
    web_url: str
    parent_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_merge(self) -> bool:
        """True for merge commits (more than one parent)."""
        return len(self.parent_ids) > 1

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Commit:
        committed = parse_datetime(data.get("committed_date") or data.get("created_at"))
        assert committed is not None
        return cls(
            id=data["id"],
            short_id=data.get("short_id", data["id"][:8]),
            title=data.get("title", "") or "",
            message=data.get("message", "") or "",
            author_name=data.get("author_name", "") or "",
            author_email=data.get("author_email", "") or "",
            committed_date=committed,
            web_url=data.get("web_url", ""),
            parent_ids=tuple(data.get("parent_ids") or ()),
        )
