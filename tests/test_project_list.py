"""Tests of the project list disk cache."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gitective.api.models import Project
from gitective.core.project_list import load_cached, save_cached


class ProjectListCacheTests(unittest.TestCase):
    def test_round_trip_and_instance_check(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "projects_cache.json"
            self.assertIsNone(load_cached("https://a", path))
            projects = [Project(id=7, name="x", path_with_namespace="g/x", web_url="https://a/g/x", default_branch="main")]
            saved_at = save_cached("https://a", projects, path)
            self.assertEqual(load_cached("https://a", path), (projects, saved_at))
            self.assertIsNone(load_cached("https://b", path))


if __name__ == "__main__":
    unittest.main()
