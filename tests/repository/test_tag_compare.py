"""Comparer sub-tab: commits between two references and their MRs (TC-02..TC-10)."""

from __future__ import annotations

import unittest
from typing import Any

from gitective.database.store import MEMORY, Store
from gitective.database.sync import ForgeData
from gitective.forge.models import Branch, Commit, MergeRequest, Tag
from gitective.repository.tag_compare import CompareError, compare, copied_text, ref_choices
from gitective.review.rules import RuleSet
from gitective.settings.config_file import TrackedProject
from gitective.shared.people import PersonDirectory
from tests.factories import commit_json, mr_json

BILLING = TrackedProject(id=10, path="acme/billing-api")
RULES = RuleSet([], "", "", {})
PEOPLE = PersonDirectory([])


def commit(sha: str, title: str = "work") -> Commit:
    return Commit.from_json(commit_json(sha, title))


def merged(iid: int, merge_sha: str | None = None, title: str = "Feature", merged_at: str = "2026-10-07T10:00:00Z",
           state: str = "merged") -> MergeRequest:
    data: dict[str, Any] = mr_json(iid=iid, title=title, state=state, merged_at=merged_at)
    data.update(merge_commit_sha=merge_sha, sha=None)
    return MergeRequest.from_json(data)


class Forge:
    """Commits per range, MRs per commit; records the requests."""

    def __init__(self) -> None:
        self.ranges: dict[str, list[Commit]] = {}
        self.links: dict[str, list[MergeRequest]] = {}
        self.calls: list[str] = []

    def list_commits(self, project_id: int, ref_name: str, since: Any = None, until: Any = None) -> list[Commit]:
        self.calls.append(f"range {ref_name}")
        return self.ranges.get(ref_name, [])

    def list_commit_merge_requests(self, project_id: int, sha: str) -> list[MergeRequest]:
        self.calls.append(f"mrs {sha}")
        return self.links.get(sha, [])


class CompareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Store(MEMORY)
        self.forge = Forge()
        self.data = ForgeData(self.forge, self.store)  # type: ignore[arg-type]
        self.store.replace_named("tags", 10, [Tag("v1", "", "s1"), Tag("v2", "", "s2")], 1.0)
        self.store.replace_named("branches", 10, [Branch("main", "s3", None)], 1.0)

    def run_compare(self, current: str = "v2", reference: str = "v1") -> Any:
        return compare(self.data, BILLING, current, reference, RULES, PEOPLE)

    def test_mrs_from_the_base_then_one_request_per_unknown_commit(self) -> None:
        # !1 is known by its merge commit, !2 by a stored commit, !3 only through GitLab, c4 has no MR.
        self.store.put_merge_requests(10, [merged(1, "m1"), merged(2, "m2", merged_at="2026-10-09T10:00:00Z")])
        self.store.put_mr_commits(10, 2, None, [commit("c2")])
        self.forge.links = {"c3" * 5: [merged(3, "m3", merged_at="2026-10-08T10:00:00Z"), merged(9, state="opened")]}
        self.forge.ranges = {"s1..s2": [Commit.from_json({**commit_json("m1", "Merge"), "id": "m1"}),
                                        commit("c2"), commit("c2b"), commit("c3"), commit("c4", "hotfix")]}
        self.forge.links["c2b" * 5] = [merged(2, "m2")]
        result = self.run_compare()
        self.assertEqual([m.iid for m in result.ahead.mrs], [2, 3, 1])  # once each, newest merge first
        self.assertEqual([o.short_id for o in result.ahead.orphans], ["c4"])
        self.assertEqual(result.ahead.commits, 5)
        self.assertTrue(result.behind.empty)
        asked = [c for c in self.forge.calls if c.startswith("mrs")]
        self.assertEqual(asked, [f"mrs {'c2b' * 5}", f"mrs {'c3' * 5}", f"mrs {'c4' * 5}"])
        self.assertEqual(len(result.evaluations), 3)

    def test_second_compare_reads_nothing(self) -> None:
        """TC-10: the couple of SHAs and the MRs of each commit are stored for good."""
        self.forge.ranges = {"s1..s2": [commit("c4")]}
        self.run_compare()
        before = len(self.forge.calls)
        self.run_compare()
        self.assertEqual(len(self.forge.calls), before)

    def test_divergence_and_branch_as_current(self) -> None:
        self.forge.ranges = {"s1..s3": [commit("c5")], "s3..s1": [commit("c6", "hotfix on v1")]}
        result = self.run_compare("main", "v1")
        self.assertTrue(result.current.is_branch)
        self.assertEqual([o.short_id for o in result.behind.orphans], ["c6"])
        # The branch moved (new head after a synchronisation): computed again.
        self.store.replace_named("branches", 10, [Branch("main", "s4", None)], 2.0)
        self.run_compare("main", "v1")
        self.assertIn("range s1..s4", self.forge.calls)

    def test_missing_reference(self) -> None:
        with self.assertRaisesRegex(CompareError, "v0 introuvable"):
            self.run_compare("v2", "v0")
        with self.assertRaisesRegex(CompareError, "main introuvable"):
            self.run_compare("v1", "main")  # an unprotected branch is never a reference

    def test_protected_branch_as_reference(self) -> None:
        self.store.replace_named("branches", 10, [Branch("main", "s3", None, protected=True),
                                                 Branch("feature", "s5", None)], 2.0)
        self.forge.ranges = {"s3..s5": [commit("c7")], "s5..s3": []}
        result = self.run_compare("feature", "main")
        self.assertTrue(result.reference.protected)
        self.assertEqual([o.short_id for o in result.ahead.orphans], ["c7"])
        _, branches = ref_choices(self.store, 10)
        self.assertEqual({b.name: b.protected for b in branches}, {"main": True, "feature": False})

    def test_choices_leave_deleted_out(self) -> None:
        self.store.replace_named("tags", 10, [Tag("v2", "", "s2")], 3.0)
        tags, branches = ref_choices(self.store, 10)
        self.assertEqual(([t.name for t in tags], [b.name for b in branches]), (["v2"], ["main"]))

    def test_copied_markdown(self) -> None:
        self.forge.ranges = {"s1..s2": [commit("c4", "hotfix")]}
        self.forge.links = {"c4" * 5: [merged(7, "m7", title="PROJ-7 Export")]}
        first = self.run_compare()
        self.forge.ranges["s2..s2"] = []
        same = self.run_compare("v2", "v2")
        self.assertEqual(copied_text([first, same], PEOPLE),
                         "## billing-api : v1 → v2\n\n- !7 PROJ-7 Export — Alice\n\n"
                         "## billing-api : v2 → v2\n\nAucune différence.\n")


if __name__ == "__main__":
    unittest.main()
