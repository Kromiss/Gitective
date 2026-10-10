"""Builders of fake GitLab JSON payloads shared by the tests."""

from __future__ import annotations

from typing import Any


def user_json(user_id: int, username: str, name: str | None = None) -> dict[str, Any]:
    return {"id": user_id, "username": username, "name": name or username.title(),
            "avatar_url": None, "web_url": f"https://gitlab.test/{username}"}


def mr_json(
    iid: int = 1,
    title: str = "[PROJ-1] Feature",
    description: str = "See https://jira.test/browse/PROJ-1",
    state: str = "merged",
    author: dict[str, Any] | None = None,
    merger: dict[str, Any] | None = None,
    created_at: str = "2026-10-06T08:00:00Z",
    merged_at: str | None = "2026-10-07T10:00:00Z",
    draft: bool = False,
    source_branch: str = "feature/PROJ-1-thing",
    target_branch: str = "main",
    project_id: int = 10,
) -> dict[str, Any]:
    return {
        "id": 1000 + iid, "iid": iid, "project_id": project_id, "title": title, "description": description,
        "state": state, "draft": draft, "author": author or user_json(1, "alice"),
        "merge_user": merger if state == "merged" else None,
        "created_at": created_at, "merged_at": merged_at if state == "merged" else None,
        "closed_at": None, "updated_at": created_at,
        "web_url": f"https://gitlab.test/group/repo/-/merge_requests/{iid}",
        "source_branch": source_branch, "target_branch": target_branch,
    }


def commit_json(sha: str, message: str, parents: int = 1) -> dict[str, Any]:
    return {
        "id": sha * 5, "short_id": sha, "title": message.splitlines()[0], "message": message,
        "author_name": "Alice", "author_email": "alice@test", "committed_date": "2026-10-07T09:00:00Z",
        "web_url": f"https://gitlab.test/group/repo/-/commit/{sha}",
        "parent_ids": [f"p{i}" for i in range(parents)],
    }
