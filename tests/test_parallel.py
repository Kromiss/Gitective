"""Tests of the concurrent lookup helper."""

import threading
import time
import unittest

from gitective.core.parallel import run_parallel


class ParallelTests(unittest.TestCase):
    def test_order_progress_and_concurrency(self) -> None:
        running, peak, lock = [0], [0], threading.Lock()

        def slow_double(x: int) -> int:
            with lock:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
            time.sleep(0.02)
            with lock:
                running[0] -= 1
            return x * 2

        progress: list[tuple[int, int]] = []
        result = run_parallel(slow_double, list(range(12)), 4, lambda d, t: progress.append((d, t)))
        self.assertEqual(result, [x * 2 for x in range(12)])
        self.assertEqual(progress[0], (0, 12))
        self.assertEqual(progress[-1], (12, 12))
        self.assertGreater(peak[0], 1)
        self.assertLessEqual(peak[0], 4)

    def test_error_is_raised(self) -> None:
        def boom(x: int) -> int:
            raise ValueError(x)

        with self.assertRaises(ValueError):
            run_parallel(boom, [1, 2, 3], 2)

    def test_empty(self) -> None:
        self.assertEqual(run_parallel(lambda x: x, [], 3), [])


if __name__ == "__main__":
    unittest.main()
