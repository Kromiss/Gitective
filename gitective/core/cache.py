"""Thread-safe in-memory cache for the current session."""

from __future__ import annotations

import threading
from collections.abc import Callable, Hashable
from typing import Any, TypeVar

T = TypeVar("T")


class SessionCache:
    """Keeps GitLab responses for the session; cleared by the Refresh button."""

    def __init__(self) -> None:
        self._data: dict[Hashable, Any] = {}
        self._lock = threading.Lock()

    def get_or_load(self, key: Hashable, loader: Callable[[], T]) -> T:
        """Return the cached value, or call loader once and cache its result."""
        with self._lock:
            if key in self._data:
                return self._data[key]
        value = loader()
        with self._lock:
            self._data[key] = value
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
