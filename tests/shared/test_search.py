"""Tests of the text search helper."""

import unittest

from gitective.shared.search import matches, sha_hit


class SearchTests(unittest.TestCase):
    def test_matches(self) -> None:
        self.assertTrue(matches("", "anything"))
        self.assertTrue(matches("proj-12", "[PROJ-12] Fix", None))
        self.assertTrue(matches("alice", "title", "Alice Martin"))
        self.assertFalse(matches("bob", "title", None, "Alice"))

    def test_sha_prefix_from_one_character(self) -> None:
        """FI-20: prefix only, from the first character, hexadecimal needles only."""
        shas = [("merge", None), ("squash", "4F1A9C2E77"), ("commit", "4f1b000000")]
        self.assertEqual(sha_hit("4", shas), "squash 4F1A9C2E")
        self.assertEqual(sha_hit(" 4f1b ", shas), "commit 4f1b0000")
        self.assertIsNone(sha_hit("1a9c", shas))  # not a prefix
        self.assertIsNone(sha_hit("PROJ", shas))
        self.assertIsNone(sha_hit("", shas))


if __name__ == "__main__":
    unittest.main()
