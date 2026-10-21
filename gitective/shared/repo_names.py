"""Short repository names: the last segment of the path, more segments only when two repositories share it."""

from __future__ import annotations

from collections.abc import Iterable


def _suffix(path: str, depth: int) -> str:
    return "/".join(path.split("/")[-depth:])


def short_names(paths: Iterable[str]) -> dict[str, str]:
    """path → shown name: "auth-service", or the shortest ending that tells it apart ("identity/auth-service")."""
    unique = list(dict.fromkeys(p for p in paths if p))
    names = {}
    for path in unique:
        depth = 1
        while depth < path.count("/") + 1 and any(
                o != path and _suffix(o, depth) == _suffix(path, depth) for o in unique):
            depth += 1
        names[path] = _suffix(path, depth)
    return names


def short_name(path: str, paths: Iterable[str]) -> str:
    """Shown name of one path among `paths` (the path itself counts even when missing from them)."""
    return short_names([*paths, path]).get(path, path)
