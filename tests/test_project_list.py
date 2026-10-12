"""Tests of the stored project list (SD-04)."""

from __future__ import annotations

import unittest

from gitective.api.models import Project
from gitective.core.project_list import load_cached, save_cached
from gitective.core.storage import MEMORY, Store


class ProjectListTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        store = Store(MEMORY)
        self.assertIsNone(load_cached(store))
        projects = [Project(id=7, name="x", path_with_namespace="g/x", web_url="https://a/g/x", default_branch="main")]
        read_at = save_cached(store, projects)
        self.assertEqual(load_cached(store), (projects, read_at))
        save_cached(store, [])  # a reload replaces the whole list
        self.assertEqual(load_cached(store)[0], [])


if __name__ == "__main__":
    unittest.main()
