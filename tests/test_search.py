"""Tests of the text search helper."""

import unittest

from gitective.ui.widgets import matches


class SearchTests(unittest.TestCase):
    def test_matches(self) -> None:
        self.assertTrue(matches("", "anything"))
        self.assertTrue(matches("proj-12", "[PROJ-12] Fix", None))
        self.assertTrue(matches("alice", "title", "Alice Martin"))
        self.assertFalse(matches("bob", "title", None, "Alice"))


if __name__ == "__main__":
    unittest.main()
