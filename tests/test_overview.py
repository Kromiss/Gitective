"""Tests of the Overview tab figures (VE-05..VE-11)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from gitective.api.models import MergeRequest
from gitective.core.overview import FEED_SIZE, WEEKS, build_overview, load_start, week_start
from gitective.core.people import PersonDirectory
from gitective.core.rules import Evaluation
from tests.factories import mr_json, user_json
from tests.test_rules import make_rules

# Monday 12 October 2026, 21:20 local time.
NOW = datetime(2026, 10, 12, 21, 20).astimezone()
GOOD = "[PROJ-1] Feature"


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def merged(iid: int, when: datetime, title: str = GOOD, repo: str = "group/api",
           merger: int = 2, created: datetime | None = None) -> Evaluation:
    mr = MergeRequest.from_json(mr_json(iid=iid, title=title, merger=user_json(merger, f"user{merger}"),
                                        created_at=iso(created or when - timedelta(hours=5)),
                                        merged_at=iso(when)))
    return make_rules().evaluate(mr, repo, PersonDirectory([]))


def build(evaluations: list[Evaluation], created: list[MergeRequest] | None = None,
          repos: tuple[str, ...] = ("group/api", "group/web")):
    rules = make_rules()
    return build_overview(evaluations, created or [], list(repos), rules.criteria, 100.0, 50.0, NOW)


class WindowTests(unittest.TestCase):
    def test_week_start_and_load_start(self) -> None:
        self.assertEqual(week_start(NOW), datetime(2026, 10, 12).astimezone())
        self.assertEqual(load_start(NOW), datetime(2026, 10, 12).astimezone() - timedelta(weeks=WEEKS))


class FeedTests(unittest.TestCase):
    def test_latest_first_and_capped(self) -> None:
        evaluations = [merged(i, NOW - timedelta(hours=i)) for i in range(1, FEED_SIZE + 6)]
        data = build(evaluations)
        self.assertEqual(len(data.feed), FEED_SIZE)
        self.assertEqual(data.feed[0].mr.iid, 1)
        self.assertEqual(data.today_count, 21)  # 1 h to 21 h before 21:20 are all today

    def test_days_of_this_week_and_last_week(self) -> None:
        data = build([merged(1, NOW - timedelta(hours=1)), merged(2, NOW - timedelta(days=1)),
                      merged(3, NOW - timedelta(days=3)), merged(4, NOW - timedelta(days=3, hours=1))])
        self.assertEqual(data.this_week, [1, None, None, None, None, None, None])
        self.assertEqual(data.last_week, [0, 0, 0, 0, 2, 0, 1])  # Friday 9 and Sunday 11


class ScoreTests(unittest.TestCase):
    def test_score_trend_ranking_and_kos(self) -> None:
        good = merged(1, NOW - timedelta(days=2))
        bad = merged(2, NOW - timedelta(days=3), title="no ticket", repo="group/web")
        old = merged(3, NOW - timedelta(days=40))
        data = build([good, bad, old])
        self.assertAlmostEqual(data.score, (good.score + bad.score) / 2)
        self.assertAlmostEqual(data.previous_score, old.score)
        self.assertEqual(data.merged_count, 2)
        self.assertEqual([r[0] for r in data.repos], ["group/api", "group/web"])
        self.assertGreater(data.kos[0][1], 0)

    def test_repository_without_merge_is_last(self) -> None:
        data = build([merged(1, NOW - timedelta(days=1), repo="group/web")], repos=("group/api", "group/web"))
        self.assertEqual(data.repos[-1], ("group/api", None))


class WeeklyTests(unittest.TestCase):
    def test_complete_weeks_only(self) -> None:
        last_week = NOW - timedelta(days=4)
        current_week = NOW - timedelta(hours=2)
        created = [MergeRequest.from_json(mr_json(iid=9, state="opened", created_at=iso(last_week)))]
        data = build([merged(1, last_week), merged(2, current_week)], created)
        self.assertEqual(len(data.week_labels), WEEKS)
        self.assertEqual(data.week_labels[-1], "S41")
        self.assertEqual(data.merged[-1], 1)
        self.assertEqual(data.created[-1], 1)
        self.assertEqual(data.quality[-1].total, 1)


if __name__ == "__main__":
    unittest.main()
