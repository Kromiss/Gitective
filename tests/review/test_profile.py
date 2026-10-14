"""Tests of the Developer / Merger profile, own open MRs, "new" flags and notifications (5.7, 5.8, 6.4, 6.5)."""

from __future__ import annotations

import unittest
from typing import Any

from gitective.database.store import MEMORY, Store
from gitective.database.sync import ForgeData
from gitective.forge.errors import NetworkError
from gitective.forge.models import MergeRequest, ProtectedBranch, User
from gitective.review.profile import (
    ASSIGNEE,
    REVIEWER,
    Profile,
    BadgeCounts,
    badge_counts,
    badge_tip,
    compute_profile,
    load_profile,
    merge_notices,
    new_count,
    role_notices,
    role_title,
    save_profile,
    seen_on_click,
)
from gitective.settings.config_file import Person, TrackedProject
from gitective.shared.people import PersonDirectory
from tests.factories import mr_json, user_json

ME = User.from_json(user_json(7, "me", "Moi Même"))
PROJECT = TrackedProject(id=10, path="group/repo", branch="main")


def open_mr(iid: int, project_id: int = 10, draft: bool = False, **extra: Any) -> MergeRequest:
    data = mr_json(iid=iid, state="opened", draft=draft, project_id=project_id)
    data["references"] = {"full": f"other/repo{project_id}!{iid}"}
    data.update(extra)
    return MergeRequest.from_json(data)


class AccessForge:
    """Forge whose members and protections decide the profile."""

    base_url = "https://gitlab.test"

    def __init__(self, level: int, protections: list[ProtectedBranch], offline: bool = False) -> None:
        self.level, self.protections, self.offline = level, protections, offline
        self.assigned: list[MergeRequest] = []
        self.reviewing: list[MergeRequest] = []

    def list_project_members(self, project_id: int) -> list[tuple[User, int]]:
        if self.offline:
            raise NetworkError("down")
        return [(ME, self.level), (User.from_json(user_json(8, "other")), 40)]

    def list_protected_branches(self, project_id: int) -> list[ProtectedBranch]:
        return self.protections

    def list_my_open_merge_requests(self, user_id: int, role: str) -> list[MergeRequest]:
        if self.offline:
            raise NetworkError("down")
        return self.assigned if role == ASSIGNEE else self.reviewing


class ProfileTests(unittest.TestCase):
    def profile(self, forge: AccessForge, user: User = ME) -> Profile:
        data = ForgeData(forge, Store(MEMORY))  # type: ignore[arg-type]
        return compute_profile(data, user, [PROJECT], workers=1)

    def test_maintainer_on_protected_branch_is_merger(self) -> None:
        profile = self.profile(AccessForge(40, [ProtectedBranch("main", merge_levels=(40,))]))
        self.assertTrue(profile.merger)
        self.assertEqual(profile.merge_projects, ("group/repo",))
        self.assertEqual(profile.label, "Mergeur")

    def test_developer_on_protected_branch_is_developer(self) -> None:
        profile = self.profile(AccessForge(30, [ProtectedBranch("main", merge_levels=(40,))]))
        self.assertFalse(profile.merger)
        self.assertEqual(profile.label, "Développeur")

    def test_developers_allowed_to_merge_or_unprotected_branch(self) -> None:
        self.assertTrue(self.profile(AccessForge(30, [ProtectedBranch("main", merge_levels=(30,))])).merger)
        self.assertTrue(self.profile(AccessForge(30, [])).merger)

    def test_admin_is_always_merger(self) -> None:
        admin = User(id=7, username="me", name="Moi", is_admin=True)
        self.assertTrue(self.profile(AccessForge(10, [ProtectedBranch("main", merge_levels=(40,))]), admin).merger)

    def test_repository_without_watched_branch_is_ignored(self) -> None:
        data = ForgeData(AccessForge(40, []), Store(MEMORY))  # type: ignore[arg-type]
        profile = compute_profile(data, ME, [TrackedProject(id=10, path="group/repo", branch="")], workers=1)
        self.assertFalse(profile.merger)

    def test_profile_is_saved_for_offline_use(self) -> None:
        store = Store(MEMORY)
        self.assertEqual(load_profile(store), Profile())
        saved = Profile(ME, True, ("group/repo",))
        save_profile(store, saved)
        self.assertEqual(load_profile(store), saved)


class MyMrTests(unittest.TestCase):
    def test_both_roles_merged_and_stored_then_offline_fallback(self) -> None:
        forge = AccessForge(40, [])
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
            ForgeData(AccessForge(40, [], offline=True), Store(MEMORY)).my_open_mrs(ME.id)  # type: ignore[arg-type]

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

    def test_role_notices_name_the_role_and_skip_drafts(self) -> None:
        items = [(open_mr(1), frozenset({ASSIGNEE})), (open_mr(2), frozenset({ASSIGNEE, REVIEWER})),
                 (open_mr(3, draft=True), frozenset({REVIEWER})), (open_mr(4), frozenset({REVIEWER}))]
        notices = role_notices({(10, 1, ASSIGNEE), (10, 2, ASSIGNEE)}, items, self.people)
        self.assertEqual({n.mr.iid: n.title for n in notices}, {2: "Relecture demandée", 4: "Relecture demandée"})

    def test_mr_leaving_draft_is_notified(self) -> None:
        notices = role_notices(set(), [(open_mr(3), frozenset({ASSIGNEE, REVIEWER}))], self.people)
        self.assertEqual([n.title for n in notices], ["MR assignée + relecture"])

    def test_role_titles(self) -> None:
        self.assertEqual(role_title({ASSIGNEE}), "MR assignée")
        self.assertEqual(role_title({REVIEWER}), "Relecture demandée")


if __name__ == "__main__":
    unittest.main()
