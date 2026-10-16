"""Which MRs the Merge Requests tab shows, and its filter state (FI-08..FI-17, AM-07, BA-02, DE-01)."""

from __future__ import annotations

import unittest
from typing import Any

from gitective.forge.models import MergeRequest
from gitective.review.mr_filters import NOBODY, people_cell, people_choices, step_selection, visible
from gitective.review.rules import Evaluation, RuleSet
from gitective.settings.config_file import Filters, Person
from gitective.settings.filter_state import FilterState
from gitective.shared.people import PersonDirectory
from tests.factories import mr_json, user_json

ALICE, BOB, CAROL, ME = (user_json(1, "alice"), user_json(2, "bob"), user_json(3, "carol"),
                         user_json(7, "me", "Kevin"))
PEOPLE = PersonDirectory([Person(name="Kevin", account_ids=[7, 70])])
RULES = RuleSet([], "", "", {})


def evaluation(iid: int, state: str = "opened", draft: bool = False, author: dict[str, Any] = ALICE,
               assignees: tuple[dict[str, Any], ...] = (), reviewers: tuple[dict[str, Any], ...] = (),
               merger: dict[str, Any] | None = None, title: str = "Feature") -> Evaluation:
    data = mr_json(iid=iid, state=state, draft=draft, author=author, merger=merger or BOB, title=title)
    data.update(assignees=list(assignees), reviewers=list(reviewers))
    return RULES.evaluate(MergeRequest.from_json(data), "group/repo", PEOPLE)


def filters(state: str = "opened", **changes: Any) -> FilterState:
    current = FilterState(Filters(state=state))
    for key, value in changes.items():
        setattr(current, key, value)
    return current


def iids(rows: list[Evaluation]) -> list[int]:
    return [e.mr.iid for e in rows]


class ShaSearchTests(unittest.TestCase):
    def test_merge_squash_head_and_stored_commits(self) -> None:
        """FI-20: a SHA prefix finds the MR whatever commit it names."""
        data = mr_json(iid=1, title="Feature")
        data.update(merge_commit_sha="4f1a" + "0" * 36, squash_commit_sha="ab12" + "0" * 36, sha="cd34" + "0" * 36)
        ev = RULES.evaluate(MergeRequest.from_json(data), "group/repo", PEOPLE)
        other = evaluation(2, state="merged")
        merged = filters("merged")
        for needle in ("4", "4F1A", "ab", "cd3", "ef"):
            self.assertEqual(iids(visible([ev, other], merged, needle, {(10, 1): ["ef56" + "0" * 36]})), [1], needle)
        self.assertEqual(iids(visible([ev, other], merged, "ef")), [])  # commits never read: not found
        self.assertEqual(iids(visible([ev, other], merged, "feature")), [1, 2])  # plain text search still works


class ResetAndTotalTests(unittest.TestCase):
    def test_reset_keeps_state_and_page_size(self) -> None:
        """FI-18."""
        state = FilterState(Filters(state="opened", since_yesterday=False, total=True, authors=["u:1"], repos=[3],
                                    drafts="only", reviewers=["none"], page_size=50))
        seen: list[str] = []
        state.subscribe(seen.append)
        state.reset()
        self.assertEqual((state.state, state.page_size, state.authors, state.repos, state.drafts, state.reviewers),
                         ("opened", 50, [], [], "all", []))
        self.assertTrue(state.since_yesterday)
        self.assertFalse(state.total)
        self.assertEqual(seen, ["reset"])

    def test_total_has_no_period_and_is_remembered(self) -> None:
        """FI-19."""
        state = FilterState(Filters(since_yesterday=False, total=True))
        self.assertIsNone(state.period())
        self.assertTrue(state.to_settings().total)
        self.assertIsNotNone(FilterState(Filters(since_yesterday=True, total=True)).period())


class VisibleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.open = [
            evaluation(1, assignees=(ME,), reviewers=(BOB,)),
            evaluation(2, draft=True, assignees=(CAROL,)),
            evaluation(3, author=BOB),
            evaluation(4, reviewers=(user_json(70, "me-old", "Kevin"),), title="Export CSV"),
        ]

    def test_no_filter_keeps_everything(self) -> None:
        self.assertEqual(iids(visible(self.open, filters())), [1, 2, 3, 4])

    def test_draft_filter_on_open_and_closed_only(self) -> None:
        self.assertEqual(iids(visible(self.open, filters(drafts="exclude"))), [1, 3, 4])
        self.assertEqual(iids(visible(self.open, filters(drafts="only"))), [2])
        merged = [evaluation(5, state="merged")]
        self.assertEqual(iids(visible(merged, filters("merged", drafts="only"))), [5])  # ignored when merged

    def test_assignee_and_reviewer_filters_by_person_with_nobody(self) -> None:
        me = PEOPLE.for_user(MergeRequest.from_json(mr_json(author=ME)).author).key
        self.assertEqual(iids(visible(self.open, filters(assignees=[me]))), [1])
        self.assertEqual(iids(visible(self.open, filters(reviewers=[me]))), [4])  # other account, same person
        self.assertEqual(iids(visible(self.open, filters(assignees=[NOBODY]))), [3, 4])
        self.assertEqual(iids(visible(self.open, filters(assignees=[me, NOBODY], reviewers=["u:2"]))), [1])

    def test_merger_filter_only_for_merged_and_combines_with_author(self) -> None:
        rows = [evaluation(5, state="merged", merger=CAROL), evaluation(6, state="merged", author=BOB),
                evaluation(7, state="merged", merger=CAROL, author=BOB)]
        self.assertEqual(iids(visible(rows, filters("merged", mergers=["u:3"]))), [5, 7])
        self.assertEqual(iids(visible(rows, filters("merged", mergers=["u:3"], authors=["u:2"]))), [7])
        self.assertEqual(iids(visible(self.open, filters(mergers=["u:3"]))), [1, 2, 3, 4])  # open: no merger

    def test_direct_commits_state_ignores_people_and_draft_filters(self) -> None:
        self.assertEqual(iids(visible(self.open, filters("direct", assignees=[NOBODY], drafts="only"))),
                         [1, 2, 3, 4])

    def test_search_covers_assignees_and_reviewers(self) -> None:
        self.assertEqual(iids(visible(self.open, filters(), "carol")), [2])
        self.assertEqual(iids(visible(self.open, filters(), "  export ")), [4])


class ChoicesTests(unittest.TestCase):
    def test_me_first_then_people_then_nobody(self) -> None:
        rows = [evaluation(1, assignees=(CAROL, ME)), evaluation(2, assignees=(BOB,))]
        me = "p:kevin"
        self.assertEqual(people_choices(rows, "assignees", me, "Kevin"),
                         [(me, "Moi (Kevin)"), ("u:2", "Bob"), ("u:3", "Carol"), (NOBODY, "Non assignée")])
        self.assertEqual(people_choices(rows, "reviewers", None, ""), [(NOBODY, "Sans relecteur")])

    def test_people_cell_puts_me_apart(self) -> None:
        ev = evaluation(1, assignees=(ME, CAROL))
        self.assertEqual(people_cell(ev.assignees, "p:kevin"), (True, "Carol"))
        self.assertEqual(people_cell(ev.assignees, None), (False, "Kevin, Carol"))
        self.assertEqual(people_cell((), "p:kevin"), "")

    def test_arrow_keys_stop_at_both_ends_and_change_page(self) -> None:
        keys = [(10, i) for i in range(1, 46)]
        self.assertEqual(step_selection(keys, (10, 20), 1, 20), (20, 2))
        self.assertEqual(step_selection(keys, (10, 1), -1, 20), (0, 1))
        self.assertEqual(step_selection(keys, (10, 45), 1, 20), (44, 3))
        self.assertIsNone(step_selection(keys, (99, 1), 1, 20))
        self.assertIsNone(step_selection(keys, None, 1, 20))


class FilterStateTests(unittest.TestCase):
    def test_saved_values_are_sanitised(self) -> None:
        state = FilterState(Filters(state="weird", drafts="maybe", repos=["10"]))  # type: ignore[list-item]
        self.assertEqual((state.state, state.drafts, state.repos), ("merged", "all", [10]))

    def test_round_trip_to_settings(self) -> None:
        saved = Filters(state="opened", assignees=["u:7"], reviewers=["u:2"], drafts="exclude", repos=[10],
                        page_size=50)
        again = FilterState(saved).to_settings()
        self.assertEqual((again.state, again.assignees, again.reviewers, again.drafts, again.repos,
                          again.page_size), ("opened", ["u:7"], ["u:2"], "exclude", [10], 50))

    def test_badge_click_resets_every_filter_and_tells_once(self) -> None:
        state = FilterState(Filters(state="merged", authors=["u:1"], mergers=["u:2"], reviewers=["u:9"],
                                    drafts="only", repos=[10]))
        events: list[str] = []
        state.subscribe(events.append)
        state.show_mine("reviewer", "p:kevin")
        self.assertEqual((state.state, state.authors, state.mergers, state.repos, state.drafts),
                         ("opened", [], [], [], "all"))
        self.assertEqual((state.assignees, state.reviewers), ([], ["p:kevin"]))
        self.assertEqual(events, ["badge"])
        state.show_mine("assignee", "p:kevin")
        self.assertEqual((state.assignees, state.reviewers), (["p:kevin"], []))


if __name__ == "__main__":
    unittest.main()
