"""Short repository names (dépôts homonymes)."""

import unittest

from gitective.shared.repo_names import short_name, short_names


class RepoNamesTests(unittest.TestCase):
    def test_last_segment_unless_shared(self) -> None:
        paths = ["acme/identity/auth-service", "legacy/auth-service", "acme/portal-web", "acme/portal-web", ""]
        self.assertEqual(short_names(paths), {"acme/identity/auth-service": "identity/auth-service",
                                              "legacy/auth-service": "legacy/auth-service",
                                              "acme/portal-web": "portal-web"})
        # Same two last segments: one more segment, only for those two.
        self.assertEqual(short_names(["a/x/api", "b/x/api", "c/y/api"]),
                         {"a/x/api": "a/x/api", "b/x/api": "b/x/api", "c/y/api": "y/api"})
        self.assertEqual(short_name("other/portal-web", ["acme/portal-web"]), "other/portal-web")
        self.assertEqual(short_name("solo", []), "solo")


if __name__ == "__main__":
    unittest.main()
