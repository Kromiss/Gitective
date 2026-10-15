"""One synchronisation round: profile, own MRs and which desktop notifications to show (CH-13, NO-04)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

from gitective.database.store import MEMORY, Store
from gitective.database.sync import ForgeData
from gitective.forge.errors import AuthenticationError, NetworkError
from gitective.forge.models import MergeRequest, ProtectedBranch, User
from gitective.review.auto_sync import synchronise
from gitective.review.profile import ASSIGNEE, REVIEWER, Profile
from gitective.settings.config_file import Settings, TrackedProject
from gitective.shared.people import PersonDirectory
from tests.factories import mr_json, user_json

ME = user_json(7, "me", "Moi")
BOB = user_json(2, "bob", "Bob")
BILLING = TrackedProject(id=10, path="acme/billing", branch="main")
PORTAL = TrackedProject(id=11, path="acme/portal", branch="main")
NOW = datetime.now(timezone.utc)


def iso(minutes_ago: float) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


def merged(iid: int, project_id: int = 10, merger: dict[str, Any] = BOB,
           author: dict[str, Any] | None = None) -> MergeRequest:
    data = mr_json(iid=iid, project_id=project_id, merger=merger, author=author, created_at=iso(600),
                   merged_at=iso(1))
    data["updated_at"] = iso(1)
    return MergeRequest.from_json(data)


def opened(iid: int, draft: bool = False) -> MergeRequest:
    data = mr_json(iid=iid, state="opened", draft=draft, created_at=iso(60))
    data["updated_at"] = iso(1)
    return MergeRequest.from_json(data)


class Forge:
    """GitLab stand-in: the token owner, MRs per project, own open MRs, merge rights."""

    base_url = "https://gitlab.test"

    def __init__(self, level: int = 40) -> None:
        self.level = level
        self.mrs: dict[int, list[MergeRequest]] = {10: [], 11: [], 12: []}
        self.assigned: list[MergeRequest] = []
        self.reviewing: list[MergeRequest] = []
        self.fail_user: Exception | None = None
        self.down: set[int] = set()
        self.my_calls = 0

    def current_user(self) -> User:
        if self.fail_user:
            raise self.fail_user
        return User.from_json(ME)

    def list_merge_requests(self, project_id: int, state: str | None = None, **_: Any) -> list[MergeRequest]:
        if project_id in self.down:
            raise NetworkError("down")
        return [m for m in self.mrs[project_id] if state is None or m.state == state]

    def list_project_members(self, project_id: int) -> list[tuple[User, int]]:
        return [(User.from_json(ME), self.level)]

    def list_protected_branches(self, project_id: int) -> list[ProtectedBranch]:
        return [ProtectedBranch("main", merge_levels=(40,))]

    def list_my_open_merge_requests(self, user_id: int, role: str) -> list[MergeRequest]:
        self.my_calls += 1
        return self.assigned if role == ASSIGNEE else self.reviewing


class AutoSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.forge = Forge()
        self.store = Store(MEMORY)
        # One worker: the shared in-memory test base has no busy timeout between threads.
        self.settings = Settings(projects=[BILLING, PORTAL], parallel_requests=1)
        self.people = PersonDirectory([])
        self.profile = Profile()

    def run_sync(self, projects: list[TrackedProject] | None = None) -> Any:
        data = ForgeData(self.forge, self.store)  # type: ignore[arg-type]
        outcome = synchronise(data, self.store, projects or [BILLING, PORTAL], self.settings, self.people,
                              self.profile)
        self.profile = outcome.profile
        return outcome

    def test_first_synchronisation_reads_everything_but_notifies_nothing(self) -> None:
        self.forge.mrs[10] = [merged(1)]
        self.forge.assigned = [opened(5)]
        outcome = self.run_sync()
        self.assertTrue(outcome.profile.merger)
        self.assertEqual([(m.iid, r) for m, r in outcome.my_mrs], [(5, frozenset({ASSIGNEE}))])
        self.assertEqual((outcome.notices, outcome.errors), ([], []))

    def test_new_merges_are_notified_once_except_own_ones(self) -> None:
        self.run_sync()
        self.forge.mrs[10] = [merged(1), merged(2, merger=ME)]
        outcome = self.run_sync()
        self.assertEqual([(n.kind, n.mr.iid, n.merger) for n in outcome.notices], [("merge", 1, "Bob")])
        self.assertEqual(self.run_sync().notices, [])  # already known at the next round

    def test_repository_tracked_since_the_last_round_does_not_flood(self) -> None:
        self.run_sync([BILLING])
        self.forge.mrs[11] = [merged(3, project_id=11)]
        self.assertEqual(self.run_sync([BILLING, PORTAL]).notices, [])

    def test_new_assignment_and_review_request_are_notified(self) -> None:
        self.forge.assigned = [opened(5)]
        self.run_sync()
        self.forge.assigned = [opened(5), opened(6)]
        self.forge.reviewing = [opened(5), opened(7, draft=True)]
        notices = self.run_sync().notices
        self.assertEqual(sorted((n.mr.iid, n.title) for n in notices),
                         [(5, "Relecture demandée"), (6, "MR assignée")])

    def test_switches_turn_notifications_off(self) -> None:
        self.run_sync()
        self.settings.notify_merges = self.settings.notify_assigned = self.settings.notify_own_merged = False
        self.forge.mrs[10] = [merged(1), merged(2, author=ME)]
        self.forge.assigned = [opened(6)]
        self.assertEqual(self.run_sync().notices, [])

    def test_developer_gets_no_own_mrs_and_no_notifications(self) -> None:
        self.forge.level = 30
        self.run_sync()
        self.forge.mrs[10] = [merged(1)]
        outcome = self.run_sync()
        self.assertFalse(outcome.profile.merger)
        self.assertEqual((outcome.my_mrs, outcome.notices, self.forge.my_calls), ([], [], 0))

    def test_my_merged_mr_is_notified_once_for_every_profile(self) -> None:
        self.forge.level = 30  # Developer
        self.run_sync()
        self.forge.mrs[10] = [merged(1), merged(2, author=ME), merged(3, author=ME, merger=ME)]
        outcome = self.run_sync()
        self.assertFalse(outcome.profile.merger)
        self.assertEqual([(n.kind, n.mr.iid, n.title, n.merger) for n in outcome.notices],
                         [("own", 2, "Votre MR a été mergée", "Bob")])

    def test_merger_gets_my_merged_mr_instead_of_new_merge(self) -> None:
        self.run_sync()
        self.forge.mrs[10] = [merged(1), merged(2, author=ME)]
        self.assertEqual(sorted((n.kind, n.mr.iid) for n in self.run_sync().notices), [("merge", 1), ("own", 2)])
        self.settings.notify_own_merged = False
        self.forge.mrs[10].append(merged(4, author=ME))
        self.assertEqual(self.run_sync().notices, [])  # switched off: no "new merge" in its place either

    def test_failures_are_reported_and_last_profile_kept(self) -> None:
        self.forge.assigned = [opened(5)]
        self.run_sync()
        self.forge.fail_user = AuthenticationError("401")
        self.forge.down = {11, 12}  # 11 is in the base (offline mode), 12 was never read
        new_repo = TrackedProject(id=12, path="acme/new", branch="main")
        outcome = self.run_sync([BILLING, PORTAL, new_repo])
        self.assertTrue(outcome.profile.merger)  # previous profile kept
        self.assertEqual(sorted(type(e).__name__ for e in outcome.errors), ["AuthenticationError", "NetworkError"])
        self.assertEqual([m.iid for m, _ in outcome.my_mrs], [5])  # still read for the known profile

    def test_roles_reported_with_both_roles(self) -> None:
        self.forge.assigned = [opened(5)]
        self.forge.reviewing = [opened(5)]
        self.assertEqual(self.run_sync().my_mrs[0][1], frozenset({ASSIGNEE, REVIEWER}))


if __name__ == "__main__":
    unittest.main()
