"""Tests of the token owner, own open MRs, "new" flags and notifications (5.7, 5.8, 6.4, 6.5)."""

from __future__ import annotations

import json
import unittest
from typing import Any

from gitective.database.store import MEMORY, Store, encode
from gitective.database.sync import ForgeData
from gitective.forge.errors import NetworkError
from gitective.forge.models import MergeRequest, User
from gitective.review.my_mrs import (
    ASSIGNEE,
    REVIEWER,
    BadgeCounts,
    author_counts,
    authored_open_mrs,
    badge_counts,
    badge_tip,
    load_user,
    merge_notices,
    new_count,
    new_mr_notices,
    open_ready_keys,
    role_notices,
    role_title,
    save_user,
    seen_on_click,
)
from gitective.settings.config_file import Person, TrackedProject
from gitective.shared.people import PersonDirectory
from tests.factories import mr_json, user_json

ME_JSON = user_json(7, "me", "Moi Même")
ME = User.from_json(ME_JSON)
PROJECT = TrackedProject(id=10, path="group/repo", branch="main")


def open_mr(iid: int, project_id: int = 10, draft: bool = False, **extra: Any) -> MergeRequest:
    data = mr_json(iid=iid, state="opened", draft=draft, project_id=project_id)
    data["references"] = {"full": f"other/repo{project_id}!{iid}"}
    data.update(extra)
    return MergeRequest.from_json(data)


class AccessForge:
    """Forge listing the token owner's open MRs."""

    base_url = "https://gitlab.test"

    def __init__(self, offline: bool = False) -> None:
        self.offline = offline
        self.assigned: list[MergeRequest] = []
        self.reviewing: list[MergeRequest] = []

    def list_my_open_merge_requests(self, user_id: int, role: str) -> list[MergeRequest]:
        if self.offline:
            raise NetworkError("down")
        return self.assigned if role == ASSIGNEE else self.reviewing


class TokenUserTests(unittest.TestCase):
    def test_user_is_saved_for_offline_use(self) -> None:
        store = Store(MEMORY)
        self.assertIsNone(load_user(store))
        save_user(store, ME)
        self.assertEqual(load_user(store), ME)

    def test_user_of_an_old_profile_is_kept(self) -> None:
        store = Store(MEMORY)
        store.set_meta("profile", json.dumps({"user": encode(ME), "merger": True, "merge_projects": []}))
        self.assertEqual(load_user(store), ME)


class MyMrTests(unittest.TestCase):
    def test_both_roles_merged_and_stored_then_offline_fallback(self) -> None:
        forge = AccessForge()
        forge.assigned = [open_mr(1), open_mr(2, project_id=99)]
        forge.reviewing = [open_mr(2, project_id=99), open_mr(3, draft=True)]
        store = Store(MEMORY)
        items = ForgeData(forge, store).my_open_mrs(ME.id)  # type: ignore[arg-type]
        roles = {(m.project_id, m.iid): r for m, r in items}
        self.assertEqual(roles[(10, 1)], {ASSIGNEE})
        self.assertEqual(roles[(99, 2)], {ASSIGNEE, REVIEWER})
        self.assertEqual(roles[(10, 3)], {REVIEWER})
        self.assertEqual(next(m for m, _ in items if m.iid == 2).project_path, "other/repo99")
        forge.offline = True
        again = ForgeData(forge, store).my_open_mrs(ME.id)  # type: ignore[arg-type]
        self.assertEqual(sorted((m.project_id, m.iid) for m, _ in again), [(10, 1), (10, 3), (99, 2)])

    def test_offline_without_stored_data_raises(self) -> None:
        with self.assertRaises(NetworkError):
            ForgeData(AccessForge(offline=True), Store(MEMORY)).my_open_mrs(ME.id)  # type: ignore[arg-type]

    def test_badges_count_ready_mrs_and_new_roles(self) -> None:
        items = [(open_mr(1), frozenset({ASSIGNEE})), (open_mr(2), frozenset({ASSIGNEE, REVIEWER})),
                 (open_mr(3, draft=True), frozenset({ASSIGNEE}))]
        seen = {(10, 1, ASSIGNEE), (10, 2, ASSIGNEE)}
        assigned = badge_counts(items, seen, ASSIGNEE)
        reviewing = badge_counts(items, seen, REVIEWER)
        self.assertEqual((assigned.total, assigned.new, assigned.drafts), (2, 0, 1))
        self.assertEqual((reviewing.total, reviewing.new, reviewing.drafts), (1, 1, 0))
        # A role added on an MR already seen makes it new; each MR counts once in the title.
        self.assertEqual(new_count(items, seen), 1)

    def test_badge_click_marks_only_its_role(self) -> None:
        items = [(open_mr(1), frozenset({ASSIGNEE, REVIEWER})), (open_mr(2), frozenset({REVIEWER})),
                 (open_mr(3, draft=True), frozenset({ASSIGNEE}))]
        self.assertEqual(seen_on_click(items, set(), ASSIGNEE), {(10, 1, ASSIGNEE)})  # drafts stay new
        self.assertEqual(seen_on_click(items, {(10, 2, REVIEWER)}, REVIEWER), {(10, 1, REVIEWER)})

    def test_badge_tooltip(self) -> None:
        self.assertEqual(badge_tip(BadgeCounts(3, 1, 1), "assignée(s)"),
                         "3 assignée(s), dont 1 nouvelle(s) ; 1 brouillon(s)\nClic : voir ces MR ouvertes")
        self.assertEqual(badge_tip(BadgeCounts(0, 0, 0), "en relecture").splitlines()[0], "0 en relecture")

    def test_author_badge_counts_own_open_mrs_of_any_of_my_accounts(self) -> None:
        store = Store(MEMORY)
        people = PersonDirectory([Person(name="Moi", account_ids=[7, 70])])
        store.put_merge_requests(10, [open_mr(1, author=user_json(70, "me-old")), open_mr(2, draft=True, author=ME_JSON),
                                      open_mr(3, author=user_json(2, "bob")),
                                      MergeRequest.from_json(mr_json(iid=4, author=ME_JSON))])
        mine = authored_open_mrs(store, [10], people, ME)
        self.assertEqual(sorted(m.iid for m in mine), [1, 2])
        self.assertEqual(author_counts(mine), BadgeCounts(1, 0, 1))
        self.assertEqual(authored_open_mrs(store, [10], people, None), [])

    def test_seen_roles_are_stored(self) -> None:
        store = Store(MEMORY)
        store.mark_seen([(10, 1, ASSIGNEE)])
        store.mark_seen([(10, 1, ASSIGNEE), (10, 2, REVIEWER)])
        self.assertEqual(store.seen_roles(), {(10, 1, ASSIGNEE), (10, 2, REVIEWER)})


class NoticeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.people = PersonDirectory([Person(name="Moi", account_ids=[7, 70])])

    def merged(self, iid: int, merger: dict[str, Any]) -> MergeRequest:
        return MergeRequest.from_json(mr_json(iid=iid, state="merged", merger=merger))

    def test_new_merges_exclude_known_and_own_merges(self) -> None:
        synced = [(PROJECT, self.merged(1, user_json(2, "bob"))),
                  (PROJECT, self.merged(2, user_json(2, "bob"))),
                  (PROJECT, self.merged(3, user_json(70, "me-old"))),
                  (PROJECT, open_mr(4))]
        notices = merge_notices({(10, 1)}, synced, ME, self.people)
        self.assertEqual([n.mr.iid for n in notices], [2])
        self.assertEqual((notices[0].title, notices[0].merger, notices[0].repo), ("Nouveau merge", "Bob", "group/repo"))

    def test_my_mr_merged_by_someone_else_from_any_of_my_accounts(self) -> None:
        mine = MergeRequest.from_json(mr_json(iid=5, merger=user_json(2, "bob"), author=user_json(70, "me-old")))
        notices = merge_notices(set(), [(PROJECT, mine)], ME, self.people, others=False)
        self.assertEqual([(n.kind, n.title, n.author, n.merger) for n in notices],
                         [("own", "Votre MR a été mergée", "Moi", "Bob")])
        self.assertEqual(merge_notices(set(), [(PROJECT, mine)], ME, self.people, own=False), [])

    def test_role_notices_name_the_role_and_skip_drafts(self) -> None:
        items = [(open_mr(1), frozenset({ASSIGNEE})), (open_mr(2), frozenset({ASSIGNEE, REVIEWER})),
                 (open_mr(3, draft=True), frozenset({REVIEWER})), (open_mr(4), frozenset({REVIEWER}))]
        notices = role_notices({(10, 1, ASSIGNEE), (10, 2, ASSIGNEE)}, items, self.people)
        self.assertEqual({n.mr.iid: n.title for n in notices}, {2: "Relecture demandée", 4: "Relecture demandée"})

    def test_mr_leaving_draft_is_notified(self) -> None:
        notices = role_notices(set(), [(open_mr(3), frozenset({ASSIGNEE, REVIEWER}))], self.people)
        self.assertEqual([n.title for n in notices], ["MR assignée + relecture"])

    def test_new_mrs_skip_known_drafts_own_and_already_notified(self) -> None:
        bob = user_json(2, "bob")
        synced = [(PROJECT, open_mr(n, author=bob)) for n in (1, 2, 3)]
        synced += [(PROJECT, open_mr(4, draft=True, author=bob)), (PROJECT, open_mr(5, author=user_json(70, "me")))]
        notices = new_mr_notices({(10, 1)}, synced, ME, self.people, skip={(10, 3)})
        self.assertEqual([(n.kind, n.mr.iid, n.author) for n in notices], [("new", 2, "Bob")])

    def test_open_ready_keys_leave_drafts_out(self) -> None:
        store = Store(MEMORY)
        store.put_merge_requests(10, [open_mr(1), open_mr(2, draft=True)])
        self.assertEqual(open_ready_keys(store, [10]), {(10, 1)})

    def test_role_titles(self) -> None:
        self.assertEqual(role_title({ASSIGNEE}), "MR assignée")
        self.assertEqual(role_title({REVIEWER}), "Relecture demandée")


if __name__ == "__main__":
    unittest.main()
