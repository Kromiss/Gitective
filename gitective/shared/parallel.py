"""Run independent GitLab lookups concurrently (P1)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


def run_parallel(
    func: Callable[[T], R],
    items: Sequence[T],
    workers: int,
    progress: Callable[[int, int], None] | None = None,
) -> list[R]:
    """Apply func to every item with up to `workers` threads; results keep the input order.

    The first exception is re-raised and pending calls are cancelled.
    """
    total = len(items)
    if progress:
        progress(0, total)
    results: list[R] = [None] * total  # type: ignore[list-item]
    pool = ThreadPoolExecutor(max_workers=max(1, workers))
    try:
        futures = {pool.submit(func, item): index for index, item in enumerate(items)}
        for done, future in enumerate(as_completed(futures), start=1):
            results[futures[future]] = future.result()
            if progress:
                progress(done, total)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    return results
