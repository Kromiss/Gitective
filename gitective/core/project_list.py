"""Disk cache of the projects visible to the token, so the repository picker opens instantly."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from gitective.api.models import Project
from gitective.config.settings import APP_DIR
from gitective.core.dates import format_datetime, now_local

CACHE_PATH = APP_DIR / "projects_cache.json"


def load_cached(gitlab_url: str, path: Path = CACHE_PATH) -> tuple[list[Project], str] | None:
    """Cached projects and their save date, or None when absent or saved for another instance."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("gitlab_url") != gitlab_url:
            return None
        return [Project.from_json(p) for p in data["projects"]], str(data.get("saved_at", ""))
    except (OSError, ValueError, TypeError, KeyError):
        return None


def save_cached(gitlab_url: str, projects: list[Project], path: Path = CACHE_PATH) -> str:
    """Write the project list; return its save date. A write failure only loses the cache."""
    saved_at = format_datetime(now_local())
    payload = {"gitlab_url": gitlab_url, "saved_at": saved_at, "projects": [asdict(p) for p in projects]}
    try:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass
    return saved_at
