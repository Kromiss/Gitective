"""Branches tab: state priority, exclusions, related MRs and the copied list (BR-02..BR-08)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from gitective.database.store import MEMORY, LinkedMr, Store
from gitective.forge.models import Branch, MergeRequest
from gitective.repository.branches import (
    ACTIVE,
    DEAD,
    DELETED,
    MERGED,
    age_in_days,
    branch_state,
    build_rows,
    copied_list,
    is_excluded,
    exclusion_pattern,
    last_commit_text,
    related_mrs,
)
from gitective.settings.config_file import DEFAULT_BRANCH_EXCLUDE, Person, TrackedProject
from gitective.shared.people import PersonDirectory
from tests.factories import mr_json

NOW = datetime(2026, 10, 16, 10, 0).astimezone()
BILLING = TrackedProject(id=10, path="acme/billing-api", web_url="https://gitlab.test/acme/billing-api")
PEOPLE = PersonDirectory([Person(name="Léa Martin", git_identities=["lea@acme.test"])])


def branch(name: str, days: int = 1, **flags: bool) -> Branch:
    return Branch(name=name, commit_sha="a" * 40, committed_date=NOW - timedelta(days=days),
                  author_name="lea", author_email="lea@acme.test", **flags)


def linked(iid: int, state: str, created: float, source: str = "feature/a", project_id: int = 10) -> LinkedMr:
    return LinkedMr(project_id, iid, state, f"MR {iid}", f"https://gitlab.test/mr/{iid}", created, source)


class StateTests(unittest.TestCase):
    def test_priority_deleted_merged_dead_active(self) -> None:
        old = branch("feature/a", days=90, merged=True)
        self.assertEqual(branch_state(old, [], 90, 30, deleted=True), DELETED)
        self.assertEqual(branch_state(old, [], 90, 30, deleted=False), MERGED)
        self.assertEqual(branch_state(branch("x", 90), [linked(1, "merged", 1)], 90, 30, False), MERGED)
        self.assertEqual(branch_state(branch("x", 90), [linked(1, "opened", 1)], 90, 30, False), DEAD)
        self.assertEqual(branch_state(branch("x", 30), [], 30, 30, False), ACTIVE)  # dead strictly beyond

    def test_age_in_calendar_days(self) -> None:
        self.assertEqual(age_in_days(NOW - timedelta(days=34, hours=1), NOW), 34)
        self.assertIsNone(age_in_days(None, NOW))

    def test_exclusions(self) -> None:
        pattern = exclusion_pattern(DEFAULT_BRANCH_EXCLUDE)
        self.assertTrue(is_excluded(branch("Main"), pattern))
        self.assertTrue(is_excluded(branch("develop-2"), pattern))
        self.assertFalse(is_excluded(branch("feature/main-menu"), pattern))
        self.assertTrue(is_excluded(branch("release", default=True), None))
        self.assertTrue(is_excluded(branch("release/1", protected=True), None))
        self.assertIsNone(exclusion_pattern("[broken"))

    def test_related_mrs_open_first_then_newest(self) -> None:
        mrs = [linked(1, "merged", 3), linked(2, "opened", 1), linked(3, "closed", 5), linked(4, "opened", 2),
               linked(5, "opened", 9, source="other"), linked(6, "opened", 9, project_id=11)]
        self.assertEqual([m.iid for m in related_mrs(mrs, 10, "feature/a")], [4, 2, 3, 1])


class RowsTests(unittest.TestCase):
    def test_rows_text_and_copied_list(self) -> None:
        stored = [(10, branch("feature/a", 34), None), (10, branch("main"), None),
                  (10, branch("feature/gone", 2), NOW.timestamp()), (99, branch("untracked"), None)]
        rows = build_rows(stored, [BILLING], [linked(7, "opened", 1)], PEOPLE, DEFAULT_BRANCH_EXCLUDE, 30, NOW)
        self.assertEqual([(r.branch.name, r.state) for r in rows], [("feature/a", DEAD), ("feature/gone", DELETED)])
        self.assertEqual(rows[0].author.name, "Léa Martin")
        self.assertEqual(last_commit_text(rows[0]), "12/09/2026 (34 j)")
        self.assertEqual(copied_list(rows[:1]),
                         "## Léa Martin\n\n- billing-api · feature/a · 12/09/2026 (34 j) · Morte · !7\n")
        self.assertEqual(copied_list([]), "")


class StoreTests(unittest.TestCase):
    def test_linked_mrs_and_mr_of_commit_read_from_sql(self) -> None:
        store = Store(MEMORY)
        data = mr_json(iid=3, source_branch="feature/a")
        data.update(merge_commit_sha="m" * 40, squash_commit_sha=None, sha="h" * 40)
        store.put_merge_requests(10, [MergeRequest.from_json(data)])
        self.assertEqual([(m.iid, m.source_branch, m.state) for m in store.linked_mrs([10])],
                         [(3, "feature/a", "merged")])
        self.assertEqual(store.mr_of_commit(10, "h" * 40).iid, 3)  # type: ignore[union-attr]
        self.assertEqual(store.mr_of_commit(10, "m" * 40).iid, 3)  # type: ignore[union-attr]
        self.assertIsNone(store.mr_of_commit(10, "x" * 40))
        self.assertIsNone(store.mr_of_commit(11, "h" * 40))


if __name__ == "__main__":
    unittest.main()
