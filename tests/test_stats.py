"""Tests of the delays of the Statistics tab (ST-12, ST-14)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from gitective.api.models import Commit, MergeRequest
from gitective.core.dates import business_days
from gitective.core.people import PersonDirectory
from gitective.core.people import PersonRef
from gitective.core.stats import by_repo, delay_details, per_person, per_repo, weekly_scores
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


class RepositoryStatsTests(unittest.TestCase):
    def test_per_repository_rows_and_direct_commits(self) -> None:
        rules, people = make_rules(), PersonDirectory([])
        merged = MergeRequest.from_json(mr_json(iid=1, merger=user_json(2, "bob")))
        opened = MergeRequest.from_json(mr_json(iid=2, state="opened", title="bad"))
        evs = [rules.evaluate(merged, "g/api", people), rules.evaluate(opened, "g/api", people)]
        rows = {r.path: r for r in per_repo(evs, ["g/api", "g/web"], ["g/web", "g/web"])}
        self.assertEqual((rows["g/api"].mr_count, rows["g/api"].merged_count), (2, 1))
        self.assertGreater(rows["g/api"].ko_counts["r_title"], 0)
        self.assertEqual((rows["g/web"].mr_count, rows["g/web"].score_avg, rows["g/web"].direct_commits), (0, None, 2))
        weeks, series = weekly_scores(evs, ["g/api"], key_of=by_repo)
        self.assertEqual(len(series["g/api"]), len(weeks))

    def test_direct_commit_authors_get_a_row(self) -> None:
        stats = per_person([], [PersonRef("g:carol", "Carol")])
        self.assertEqual((stats[0].person.name, stats[0].direct_commits, stats[0].score_avg), ("Carol", 1, None))


if __name__ == "__main__":
    unittest.main()
