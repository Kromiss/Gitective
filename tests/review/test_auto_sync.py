"""One synchronisation round: token owner, own MRs and which desktop notifications to show (CH-13, NO-04)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

from gitective.database.store import MEMORY, Store
from gitective.database.sync import ForgeData
from gitective.forge.errors import AuthenticationError, NetworkError
from gitective.forge.models import Branch, MergeRequest, Tag, User
from gitective.review.auto_sync import synchronise
from gitective.review.my_mrs import ASSIGNEE, REVIEWER
from gitective.review.rules import RuleSet
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


def opened(iid: int, draft: bool = False, author: dict[str, Any] | None = None) -> MergeRequest:
    data = mr_json(iid=iid, state="opened", draft=draft, created_at=iso(60), author=author)
    data["updated_at"] = iso(1)
    return MergeRequest.from_json(data)


class Forge:
    """GitLab stand-in: the token owner, MRs per project, own open MRs."""

    base_url = "https://gitlab.test"

    def __init__(self) -> None:
        self.mrs: dict[int, list[MergeRequest]] = {10: [], 11: [], 12: []}
        self.assigned: list[MergeRequest] = []
        self.reviewing: list[MergeRequest] = []
        self.fail_user: Exception | None = None
        self.down: set[int] = set()
        self.my_calls = 0
        self.branches: dict[int, list[Branch]] = {}
        self.tags: dict[int, list[Tag]] = {}

    def current_user(self) -> User:
        if self.fail_user:
            raise self.fail_user
        return User.from_json(ME)

    def list_merge_requests(self, project_id: int, state: str | None = None, **_: Any) -> list[MergeRequest]:
        if project_id in self.down:
            raise NetworkError("down")
        return [m for m in self.mrs[project_id] if state is None or m.state == state]

    def list_branches(self, project_id: int) -> list[Branch]:
        if project_id in self.down:
            raise NetworkError("down")
        return self.branches.get(project_id, [])

    def list_tags(self, project_id: int) -> list[Tag]:
        return self.tags.get(project_id, [])

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
        self.user: User | None = None

    def run_sync(self, projects: list[TrackedProject] | None = None) -> Any:
        data = ForgeData(self.forge, self.store)  # type: ignore[arg-type]
        outcome = synchronise(data, self.store, projects or [BILLING, PORTAL], self.settings, self.people,
                              self.user)
        self.user = outcome.user
        return outcome

    def test_first_synchronisation_reads_everything_but_notifies_nothing(self) -> None:
        self.forge.mrs[10] = [merged(1)]
        self.forge.assigned = [opened(5)]
        outcome = self.run_sync()
        self.assertEqual(outcome.user, User.from_json(ME))
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

    def test_notifications_carry_the_mr_score(self) -> None:
        self.forge.assigned = [opened(5)]
        self.run_sync()
        self.forge.mrs[10] = [merged(1)]
        self.forge.assigned = [opened(5), opened(6)]
        notices = self.run_sync().notices
        rules = RuleSet.from_settings(self.settings)
        for notice in notices:
            expected = rules.evaluate(notice.mr, "acme/billing", self.people).score
            self.assertEqual((notice.mr.iid, notice.score), (notice.mr.iid, expected))
        self.assertEqual(sorted(n.mr.iid for n in notices), [1, 6])
        self.assertTrue(all(n.score is not None for n in notices))

    def test_switches_turn_notifications_off(self) -> None:
        self.run_sync()
        self.settings.notify_merges = self.settings.notify_assigned = self.settings.notify_own_merged = False
        self.forge.mrs[10] = [merged(1), merged(2, author=ME)]
        self.forge.assigned = [opened(6)]
        self.assertEqual(self.run_sync().notices, [])

    def test_my_merged_mr_is_notified_once(self) -> None:
        self.run_sync()
        self.settings.notify_merges = False
        self.forge.mrs[10] = [merged(1), merged(2, author=ME), merged(3, author=ME, merger=ME)]
        outcome = self.run_sync()
        self.assertEqual([(n.kind, n.mr.iid, n.title, n.merger) for n in outcome.notices],
                         [("own", 2, "Votre MR a été mergée", "Bob")])

    def test_new_mrs_notified_only_when_switched_on(self) -> None:
        self.run_sync()
        self.forge.mrs[10] = [opened(1, author=BOB)]
        self.assertEqual(self.run_sync().notices, [])  # off by default (NO-11)
        self.settings.notify_new_mrs = True
        self.forge.mrs[10] += [opened(2, author=BOB), opened(3, author=ME), opened(4, draft=True, author=BOB),
                               opened(5, author=BOB)]
        self.forge.assigned = [opened(5, author=BOB)]
        notices = self.run_sync().notices
        self.assertEqual(sorted((n.kind, n.mr.iid) for n in notices), [("new", 2), ("role", 5)])
        self.assertEqual(self.run_sync().notices, [])  # already known

    def test_my_merged_mr_replaces_new_merge(self) -> None:
        self.run_sync()
        self.forge.mrs[10] = [merged(1), merged(2, author=ME)]
        self.assertEqual(sorted((n.kind, n.mr.iid) for n in self.run_sync().notices), [("merge", 1), ("own", 2)])
        self.settings.notify_own_merged = False
        self.forge.mrs[10].append(merged(4, author=ME))
        self.assertEqual(self.run_sync().notices, [])  # switched off: no "new merge" in its place either

    def test_failures_are_reported_and_last_user_kept(self) -> None:
        self.forge.assigned = [opened(5)]
        self.run_sync()
        self.forge.fail_user = AuthenticationError("401")
        self.forge.down = {11, 12}  # 11 is in the base (offline mode), 12 was never read
        new_repo = TrackedProject(id=12, path="acme/new", branch="main")
        outcome = self.run_sync([BILLING, PORTAL, new_repo])
        self.assertEqual(outcome.user, User.from_json(ME))  # previous user kept
        self.assertEqual(sorted(type(e).__name__ for e in outcome.errors), ["AuthenticationError", "NetworkError"])
        self.assertEqual([m.iid for m, _ in outcome.my_mrs], [5])  # still read for the known user

    def test_roles_reported_with_both_roles(self) -> None:
        self.forge.assigned = [opened(5)]
        self.forge.reviewing = [opened(5)]
        self.assertEqual(self.run_sync().my_mrs[0][1], frozenset({ASSIGNEE, REVIEWER}))

    def test_branches_and_tags_compared_with_the_base(self) -> None:
        """BR-10, TG-08: new ones stored, missing ones kept as deleted, a recreated one active again."""
        feature, old = Branch("feature/a", "s1", None), Branch("feature/old", "s2", None)
        self.forge.branches = {10: [feature, old]}
        self.forge.tags = {10: [Tag("v1.0", "", "s1")]}
        self.run_sync()
        self.assertEqual({b.name: d for _, b, d in self.store.branches([10])}, {"feature/a": None, "feature/old": None})
        self.forge.branches = {10: [feature]}
        self.forge.tags = {10: []}
        self.run_sync()
        deleted = {b.name: d for _, b, d in self.store.branches([10])}
        self.assertIsNone(deleted["feature/a"])
        self.assertIsNotNone(deleted["feature/old"])
        self.assertIsNotNone(self.store.tags([10])[0][2])
        self.forge.branches = {10: [feature, old]}
        self.run_sync()
        self.assertIsNone({b.name: d for _, b, d in self.store.branches([10])}["feature/old"])

    def test_branches_kept_when_offline(self) -> None:
        self.forge.branches = {11: [Branch("feature/a", "s1", None)]}
        self.run_sync()
        self.forge.down = {11}
        outcome = self.run_sync()
        self.assertEqual([b.name for _, b, d in self.store.branches([11]) if d is None], ["feature/a"])
        self.assertNotIn("NetworkError", [type(e).__name__ for e in outcome.errors])


if __name__ == "__main__":
    unittest.main()
