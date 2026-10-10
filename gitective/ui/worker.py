"""Run GitLab calls in background threads and hand results back to Tk (CH-01)."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from typing import Any

Progress = Callable[[int, int], None]
Task = Callable[[Progress], Any]

POLL_MS = 80


class BackgroundRunner:
    """Executes tasks in daemon threads; callbacks always run in the Tk thread.

    Each task belongs to a channel: starting a new task on a channel makes the
    results of the previous one obsolete, so stale data never overwrites
    fresh data when filters change quickly.
    """

    def __init__(self, root: tk.Misc, on_busy_change: Callable[[bool], None]) -> None:
        self._root = root
        self._queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._generation: dict[str, int] = {}
        self._active = 0
        self._on_busy_change = on_busy_change
        self._root.after(POLL_MS, self._poll)

    def run(
        self,
        channel: str,
        task: Task,
        on_done: Callable[[Any], None],
        on_error: Callable[[BaseException], None],
        on_progress: Progress | None = None,
    ) -> None:
        """Start task(progress) in a thread; route its outcome to the callbacks."""
        generation = self._generation.get(channel, 0) + 1
        self._generation[channel] = generation
        self._set_active(+1)

        def current() -> bool:
            return self._generation.get(channel) == generation

        def progress(done: int, total: int) -> None:
            if on_progress:
                self._queue.put(lambda: current() and on_progress(done, total))

        def worker() -> None:
            try:
                result = task(progress)
            except BaseException as exc:  # noqa: BLE001 - every failure goes to the banner
                # Bind exc now: Python unbinds the name when the except block ends.
                self._queue.put(lambda e=exc: (self._set_active(-1), current() and on_error(e)))
            else:
                self._queue.put(lambda r=result: (self._set_active(-1), current() and on_done(r)))

        threading.Thread(target=worker, daemon=True).start()

    def _set_active(self, delta: int) -> None:
        before = self._active > 0
        self._active += delta
        if before != (self._active > 0):
            self._on_busy_change(self._active > 0)

    def _poll(self) -> None:
        try:
            while True:
                self._queue.get_nowait()()
        except queue.Empty:
            pass
        self._root.after(POLL_MS, self._poll)
