"""Tests of the delays of the Statistics tab (ST-12, ST-14)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from gitective.api.models import Commit, MergeRequest
from gitective.core.dates import business_days
from gitective.core.people import PersonDirectory
from gitective.core.stats import delay_details, per_person
from tests.factories import commit_json, mr_json, user_json
from tests.test_rules import make_rules

FRIDAY_NOON = datetime(2026, 10, 9, 12, 0).astimezone()


class BusinessDaysTests(unittest.TestCase):
    def test_weekend_is_skipped(self) -> None:
        # Friday 12:00 → Monday 12:00: half of Friday + half of Monday.
        self.assertAlmostEqual(business_days(FRIDAY_NOON, FRIDAY_NOON + timedelta(days=3)), 1.0)

    def test_same_day_and_reversed(self) -> None:
        self.assertAlmostEqual(business_days(FRIDAY_NOON, FRIDAY_NOON + timedelta(hours=6)), 0.25)
        self.assertEqual(business_days(FRIDAY_NOON, FRIDAY_NOON - timedelta(hours=1)), 0.0)


class MergeDelayTests(unittest.TestCase):
    def test_merger_delay_from_last_commit(self) -> None:
        rules, people = make_rules(), PersonDirectory([])
        mr = MergeRequest.from_json(mr_json(merger=user_json(2, "bob"), merged_at="2026-10-07T10:00:00Z"))
        commits = [Commit.from_json({**commit_json("a", "x"), "committed_date": "2026-10-06T10:00:00Z"}),
                   Commit.from_json({**commit_json("b", "y"), "committed_date": "2026-10-07T04:00:00Z"})]
        stats = {s.person.key: s for s in per_person([rules.evaluate(mr, "g/r", people, commits)])}
        self.assertAlmostEqual(stats["u:2"].merge_delay_days, 0.25)  # last commit 04:00 → merge 10:00
        self.assertIsNone(stats["u:1"].merge_delay_days)
        self.assertIn("Sur 1 MR", delay_details(stats["u:2"].merge_delays))


if __name__ == "__main__":
    unittest.main()
