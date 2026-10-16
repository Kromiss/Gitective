"""Forge-neutral typed objects returned by every ForgeClient (API-04)."""

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
    is_admin: bool = False  # only reported for the token owner (PR-01)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> User:
        return cls(
            id=int(data["id"]),
            username=data.get("username", ""),
            name=data.get("name", "") or data.get("username", ""),
            avatar_url=data.get("avatar_url"),
            web_url=data.get("web_url"),
            is_admin=bool(data.get("is_admin", False)),
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
    sha: str | None = None  # head commit of the source branch (RC-05)
    assignees: tuple[User, ...] = ()
    reviewers: tuple[User, ...] = ()
    project_path: str = ""  # "group/repo", known even for repositories that are not tracked

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
            sha=data.get("sha"),
            assignees=_users(data.get("assignees") or ([data["assignee"]] if data.get("assignee") else [])),
            reviewers=_users(data.get("reviewers")),
            project_path=((data.get("references") or {}).get("full") or "").rsplit("!", 1)[0],
        )


def _users(items: Any) -> tuple[User, ...]:
    return tuple(User.from_json(u) for u in items or [])


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


@dataclass(frozen=True)
class ProtectedBranch:
    """A branch protection rule; `name` may contain wildcards (e.g. "release/*")."""

    name: str
    merge_levels: tuple[int, ...] = ()  # roles allowed to merge; 0 means no one
    merge_user_ids: tuple[int, ...] = ()  # individual users allowed (Premium / Ultimate)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ProtectedBranch:
        rules = data.get("merge_access_levels") or []
        return cls(
            name=data.get("name", ""),
            merge_levels=tuple(int(r["access_level"]) for r in rules if r.get("access_level") is not None
                               and not r.get("user_id") and not r.get("group_id")),
            merge_user_ids=tuple(int(r["user_id"]) for r in rules if r.get("user_id")),
        )


@dataclass(frozen=True)
class CommitStatus:
    """A CI result published on a commit (GitLab CI, Jenkins through its GitLab plugin...)."""

    name: str
    status: str  # success, failed, canceled, running, pending, created, skipped, manual
    created_at: datetime
    finished_at: datetime | None = None
    allow_failure: bool = False

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> CommitStatus:
        created = parse_datetime(data.get("created_at"))
        assert created is not None
        return cls(
            name=data.get("name", "") or "default",
            status=data.get("status", ""),
            created_at=created,
            finished_at=parse_datetime(data.get("finished_at")),
            allow_failure=bool(data.get("allow_failure", False)),
        )


# ---------------------------------------------------------------- MR detail panel (6.6)


@dataclass(frozen=True)
class PipelineRef:
    """Latest pipeline of an MR head commit."""

    id: int
    status: str
    updated_at: datetime | None = None
    web_url: str = ""

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PipelineRef:
        return cls(id=int(data["id"]), status=data.get("status", ""),
                   updated_at=parse_datetime(data.get("updated_at") or data.get("created_at")),
                   web_url=data.get("web_url", "") or "")


@dataclass(frozen=True)
class MergeState:
    """What the forge says about merging an open MR (DE-05)."""

    merge_status: str  # GitLab detailed_merge_status: "mergeable", "conflict", "ci_must_pass", ...
    has_conflicts: bool = False
    behind_by: int | None = None  # commits of the target branch missing from the source branch
    blocking_discussions_resolved: bool = True
    pipeline: PipelineRef | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> MergeState:
        pipeline = data.get("head_pipeline") or data.get("pipeline")
        behind = data.get("diverged_commits_count")
        return cls(
            merge_status=data.get("detailed_merge_status") or data.get("merge_status") or "",
            has_conflicts=bool(data.get("has_conflicts", False)),
            behind_by=int(behind) if behind is not None else None,
            blocking_discussions_resolved=bool(data.get("blocking_discussions_resolved", True)),
            pipeline=PipelineRef.from_json(pipeline) if pipeline else None,
        )


@dataclass(frozen=True)
class Approvals:
    """Approvals of an MR; required is None when the forge edition does not tell (DE-13)."""

    approved_by: tuple[User, ...] = ()
    required: int | None = None
    left: int | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Approvals:
        required, left = data.get("approvals_required"), data.get("approvals_left")
        return cls(
            approved_by=tuple(User.from_json(a["user"]) for a in data.get("approved_by") or [] if a.get("user")),
            required=int(required) if required is not None else None,
            left=int(left) if left is not None else None,
        )


@dataclass(frozen=True)
class Discussion:
    """A resolvable discussion thread of an MR, summed up by its first note."""

    author: User
    body: str
    resolved: bool
    path: str = ""  # file of a code comment, empty for a general comment
    line: int | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Discussion | None:
        """None for threads that cannot be resolved (system notes, plain comments)."""
        notes = [n for n in data.get("notes") or [] if n.get("resolvable")]
        if not notes:
            return None
        first = notes[0]
        position = first.get("position") or {}
        line = position.get("new_line") or position.get("old_line")
        return cls(
            author=User.from_json(first["author"]),
            body=first.get("body", "") or "",
            resolved=all(n.get("resolved") for n in notes),
            path=position.get("new_path") or position.get("old_path") or "",
            line=int(line) if line is not None else None,
        )


@dataclass(frozen=True)
class ChangedFile:
    """A file changed by an MR, with its added and removed line counts."""

    path: str
    added: int
    removed: int

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ChangedFile:
        added = removed = 0
        for line in (data.get("diff") or "").splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1
        return cls(path=data.get("new_path") or data.get("old_path") or "", added=added, removed=removed)


@dataclass(frozen=True)
class Job:
    """A CI job of a pipeline."""

    id: int
    name: str
    status: str
    duration: float | None = None  # seconds
    web_url: str = ""

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Job:
        duration = data.get("duration")
        return cls(id=int(data["id"]), name=data.get("name", ""), status=data.get("status", ""),
                   duration=float(duration) if duration is not None else None, web_url=data.get("web_url", "") or "")


# ---------------------------------------------------------------- Branches and tags (11, 12)


@dataclass(frozen=True)
class Branch:
    """A branch with its last commit and GitLab flags (BR-10)."""

    name: str
    commit_sha: str
    committed_date: datetime | None
    author_name: str = ""
    author_email: str = ""
    merged: bool = False
    protected: bool = False
    default: bool = False
    web_url: str = ""

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Branch:
        commit = data.get("commit") or {}
        return cls(
            name=data.get("name", ""),
            commit_sha=commit.get("id", "") or "",
            committed_date=parse_datetime(commit.get("committed_date") or commit.get("created_at")),
            author_name=commit.get("author_name", "") or "",
            author_email=commit.get("author_email", "") or "",
            merged=bool(data.get("merged", False)),
            protected=bool(data.get("protected", False)),
            default=bool(data.get("default", False)),
            web_url=data.get("web_url", "") or "",
        )


@dataclass(frozen=True)
class Tag:
    """A tag, its pointed commit and its GitLab release (TG-08)."""

    name: str
    message: str
    commit_sha: str
    commit_title: str = ""
    committed_date: datetime | None = None
    author_name: str = ""
    author_email: str = ""
    annotated: bool = False  # annotated tag (own tag object) or lightweight tag
    release_name: str = ""
    release_notes: str = ""
    has_release: bool = False

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Tag:
        commit = data.get("commit") or {}
        release = data.get("release") or {}
        sha = commit.get("id", "") or ""
        target = data.get("target") or sha
        return cls(
            name=data.get("name", ""),
            message=(data.get("message") or "").strip(),
            commit_sha=sha,
            commit_title=commit.get("title", "") or "",
            committed_date=parse_datetime(commit.get("committed_date") or commit.get("created_at")),
            author_name=commit.get("author_name", "") or "",
            author_email=commit.get("author_email", "") or "",
            annotated=bool(data.get("message")) or target != sha,
            release_name=release.get("name") or release.get("tag_name") or "",
            release_notes=(release.get("description") or "").strip(),
            has_release=bool(release),
        )
