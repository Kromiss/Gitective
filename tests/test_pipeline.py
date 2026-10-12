"""Tests of the fixed rule RC-05 "Pipeline vert" (PI-01..PI-06)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from gitective.api.models import CommitStatus, MergeRequest
from gitective.core.people import PersonDirectory
from gitective.core.rules import KO, NA, OK, PIPELINE, check_pipeline
from tests.factories import mr_json, user_json
from tests.test_client import FakeOpener, FakeResponse, make_client
from tests.test_rules import make_rules

MERGED = datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc)


def status(name: str, state: str, created_min: int, finished_min: int | None = None,
           allow_failure: bool = False) -> CommitStatus:
    """Status created `created_min` minutes before the merge (negative = after)."""
    finished = MERGED - timedelta(minutes=finished_min) if finished_min is not None else None
    return CommitStatus(name, state, MERGED - timedelta(minutes=created_min), finished, allow_failure)


class PipelineTests(unittest.TestCase):
    def test_not_applicable(self) -> None:
        self.assertEqual(check_pipeline(None, [], True).status, NA)        # not merged
        self.assertEqual(check_pipeline(MERGED, [], False).status, NA)     # no CI expected (PI-06)

    def test_all_green_before_merge(self) -> None:
        result = check_pipeline(MERGED, [status("jenkins", "success", 30, 10), status("lint", "success", 30, 25)], True)
        self.assertEqual(result.status, OK)

    def test_latest_status_before_merge_wins(self) -> None:
        statuses = [status("jenkins", "failed", 60, 50), status("jenkins", "success", 30, 10),
                    status("jenkins", "failed", -10, -20)]  # a run after the merge does not count
        self.assertEqual(check_pipeline(MERGED, statuses, True).status, OK)

    def test_failed_running_canceled_and_missing(self) -> None:
        failed = check_pipeline(MERGED, [status("jenkins", "failed", 30, 10)], True)
        self.assertEqual((failed.status, failed.detail), (KO, "jenkins : failed"))
        running = check_pipeline(MERGED, [status("jenkins", "running", 5)], True)
        self.assertEqual(running.detail, "jenkins : en cours au merge")
        canceled = check_pipeline(MERGED, [status("jenkins", "canceled", 30, 20)], True)
        self.assertEqual(canceled.detail, "jenkins : annulé")
        self.assertEqual(check_pipeline(MERGED, [], True).detail, "Aucun statut CI")

    def test_allow_failure_is_ignored(self) -> None:
        statuses = [status("jenkins", "success", 30, 10), status("sonar", "failed", 30, 10, allow_failure=True)]
        self.assertEqual(check_pipeline(MERGED, statuses, True).status, OK)

    def test_counts_in_the_score(self) -> None:
        rules = make_rules()  # weights of test_rules: title, link, ticket, self merge (pipeline weight 0 there)
        mr = MergeRequest.from_json(mr_json(merger=user_json(2, "bob"), merged_at="2026-10-07T10:00:00Z"))
        ev = rules.evaluate(mr, "g/r", PersonDirectory([]), statuses=[], ci_expected=True)
        self.assertEqual(ev.results[PIPELINE].status, KO)

    def test_client_reads_every_status(self) -> None:
        opener = FakeOpener(FakeResponse([{"name": "jenkins", "status": "success", "allow_failure": False,
                                           "created_at": "2026-10-07T09:00:00Z",
                                           "finished_at": "2026-10-07T09:30:00Z"}]))
        client, _ = make_client(opener)
        statuses = client.list_commit_statuses(10, "abc")
        self.assertEqual(statuses[0].name, "jenkins")
        self.assertIn("/repository/commits/abc/statuses", opener.requests[0].full_url)
        self.assertEqual(opener.query(0)["all"], ["true"])


if __name__ == "__main__":
    unittest.main()
