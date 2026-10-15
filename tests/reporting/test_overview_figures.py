"""Tests of the Overview tab figures (VE-05..VE-11)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from gitective.forge.models import MergeRequest
from gitective.reporting.overview_figures import (
    COMPACT_ROW_H,
    FEED_SIZE,
    GROUP_H,
    ROW_H,
    WEEKS,
    build_overview,
    feed_row_height,
    load_start,
    short_title,
    week_start,
)
from gitective.shared.people import PersonDirectory
from gitective.review.rules import Evaluation
from tests.factories import mr_json, user_json
from tests.review.test_rules import make_rules

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

    def test_each_day_gets_the_average_score_of_its_merges(self) -> None:
        good, bad = merged(1, NOW - timedelta(days=3)), merged(2, NOW - timedelta(days=3, hours=1), title="no ticket")
        data = build([merged(3, NOW - timedelta(hours=1)), good, bad])
        self.assertEqual(data.this_week_scores, [merged(3, NOW).score, None, None, None, None, None, None])
        self.assertEqual(data.last_week_scores[4], (good.score + bad.score) / 2)  # Friday 9
        self.assertNotEqual(good.score, bad.score)
        self.assertEqual(data.last_week_scores[:4] + data.last_week_scores[5:], [None] * 6)


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


class FeedDensityTests(unittest.TestCase):
    """A busy day must fit in the latest merges feed (VE-05)."""

    def test_two_line_rows_while_today_fits_then_compact(self) -> None:
        room = 560.0
        self.assertEqual(feed_row_height(5, room), ROW_H)
        self.assertEqual(feed_row_height(15, room), COMPACT_ROW_H)
        self.assertLessEqual(GROUP_H + 15 * COMPACT_ROW_H, room)  # 15 merges of the day all visible
        self.assertGreaterEqual(FEED_SIZE, 30)  # the feed keeps enough merges to fill the column


class ShortTitleTests(unittest.TestCase):
    def test_long_titles_are_cut_on_a_word_with_an_ellipsis(self) -> None:
        title = "PROJ-142 Calcul des remises par lot pour les clients grands comptes et les revendeurs"
        short = short_title(title)
        self.assertLessEqual(len(short), 45)
        self.assertTrue(short.endswith("…"))
        self.assertTrue(title.startswith(short[:-1]))
        self.assertNotIn("  ", short)

    def test_short_titles_and_long_words(self) -> None:
        self.assertEqual(short_title("PROJ-1  Fix\tlogin"), "PROJ-1 Fix login")
        self.assertEqual(short_title("x" * 60, 10), "x" * 9 + "…")
