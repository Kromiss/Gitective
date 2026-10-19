"""Upgrade of an existing gitective.db from schema 1 to schema 2 (CH-11)."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from gitective.database.store import MIGRATIONS, SCHEMA_VERSION, Store
from gitective.database.sync import MrDetailData
from gitective.forge.models import Branch, MergeRequest
from gitective.review.profile import ASSIGNEE
from tests.factories import mr_json


def schema_1_database(path: Path) -> None:
    """A base as written by the previous version: schema 1 with a synced project, an MR and an avatar."""
    conn = sqlite3.connect(path)
    for statement in MIGRATIONS[0]:
        conn.execute(statement)
    old_mr = mr_json(iid=4)  # stored before assignees, reviewers and project path existed
    stored = {k: v for k, v in MergeRequest.from_json(old_mr).__dict__.items()
              if k not in ("assignees", "reviewers", "project_path")}
    stored["author"] = stored["author"].__dict__
    stored["merged_by"] = stored["merged_by"].__dict__ if stored["merged_by"] else None
    for key in ("created_at", "merged_at", "closed_at", "updated_at"):
        stored[key] = stored[key].isoformat() if stored[key] else None
    conn.execute("INSERT INTO merge_requests VALUES (10, 4, 'merged', 1.0, 2.0, 2.0, ?)", (json.dumps(stored),))
    conn.execute("INSERT INTO sync VALUES ('mr:10', 0.0, 2.0)")
    conn.execute("INSERT INTO sync VALUES ('commits:10:main', 0.0, 2.0)")
    conn.execute("INSERT INTO avatars VALUES (1, ?)", (b"png",))
    conn.execute("INSERT INTO meta VALUES ('instance_url', 'https://gitlab.test')")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()


class MigrationTests(unittest.TestCase):
    def test_schema_1_base_is_upgraded_without_losing_data(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "gitective.db"
            schema_1_database(path)
            store = Store(path)
            self.assertEqual(store.schema_version, SCHEMA_VERSION)
            self.assertEqual(SCHEMA_VERSION, 4)
            # Kept: stored MRs, commits sync state, avatars, instance URL.
            old = store.merge_requests(10)
            self.assertEqual([m.iid for m in old], [4])
            self.assertEqual((old[0].assignees, old[0].reviewers, old[0].project_path), ((), (), ""))
            self.assertIsNotNone(store.sync_state("commits:10:main"))
            self.assertEqual(store.get_avatar(1), b"png")
            self.assertEqual(store.get_meta("instance_url"), "https://gitlab.test")
            # MRs are read again once, to get their assignees and reviewers.
            self.assertIsNone(store.sync_state("mr:10"))

    def test_new_tables_work_after_upgrade_and_reopening(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "gitective.db"
            schema_1_database(path)
            store = Store(path)
            mr = MergeRequest.from_json(mr_json(iid=5, state="opened"))
            store.put_my_mrs([(mr, frozenset({ASSIGNEE}))])
            store.mark_seen([(10, 5, ASSIGNEE)])
            store.put_mr_detail(10, 5, 1.0, MrDetailData(fetched_at=mr.created_at))
            store.replace_named("branches", 10, [Branch(name="feature/x", commit_sha="a1", committed_date=None)], 1.0)
            again = Store(path)
            self.assertEqual([b.name for _, b, _ in again.branches([10])], ["feature/x"])
            self.assertEqual([(m.iid, r) for m, r in again.my_mrs()], [(5, frozenset({ASSIGNEE}))])
            self.assertEqual(again.seen_roles(), {(10, 5, ASSIGNEE)})
            self.assertIsNotNone(again.get_mr_detail(10, 5, MrDetailData))
            again.clear()  # OC-09 also empties the new tables
            self.assertEqual((again.my_mrs(), again.seen_roles()), ([], set()))


if __name__ == "__main__":
    unittest.main()
