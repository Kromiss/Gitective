"""Tests of the merge-rights computation (ST-11)."""

from __future__ import annotations

import unittest

from gitective.api.models import ProtectedBranch, User
from gitective.core.mergers import can_merge

DEV, MAINTAINER = User(1, "dev", "Dev"), User(2, "lead", "Lead")
GUEST = User(3, "guest", "Guest")
MEMBERS = [(DEV, 30), (MAINTAINER, 40), (GUEST, 10)]


class CanMergeTests(unittest.TestCase):
    def test_unprotected_branch_allows_developers(self) -> None:
        self.assertEqual(can_merge(MEMBERS, [], "main"), [DEV, MAINTAINER])

    def test_protected_branch_level(self) -> None:
        rule = ProtectedBranch("main", merge_levels=(40,))
        self.assertEqual(can_merge(MEMBERS, [rule], "main"), [MAINTAINER])

    def test_wildcard_and_most_permissive_rule(self) -> None:
        rules = [ProtectedBranch("release/*", merge_levels=(40,)), ProtectedBranch("release/1.*", merge_levels=(30,))]
        self.assertEqual(can_merge(MEMBERS, rules, "release/1.2"), [DEV, MAINTAINER])

    def test_no_one_but_listed_user(self) -> None:
        rule = ProtectedBranch("main", merge_levels=(0,), merge_user_ids=(1,))
        self.assertEqual(can_merge(MEMBERS, [rule], "main"), [DEV])

    def test_parse_protected_branch(self) -> None:
        rule = ProtectedBranch.from_json({"name": "main", "merge_access_levels": [
            {"access_level": 40}, {"access_level": 40, "user_id": 7}, {"access_level": 40, "group_id": 9}]})
        self.assertEqual((rule.merge_levels, rule.merge_user_ids), ((40,), (7,)))


if __name__ == "__main__":
    unittest.main()
