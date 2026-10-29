"""Tests of the local SQLite store and of the incremental synchronisation (CH-03..CH-12)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from gitective.forge.errors import NetworkError
from gitective.forge.models import Branch, Commit, CommitStatus, MergeRequest, ProtectedBranch, User
from gitective.database.store import MEMORY, SCHEMA_VERSION, Store, StoreError, decode, encode
from gitective.database.sync import ForgeData
from tests.factories import commit_json, mr_json, user_json

NOW = datetime(2026, 10, 12, 19, 0, tzinfo=timezone.utc)


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def mr(iid: int, state: str = "merged", updated: datetime = NOW, sha: str = "abc") -> MergeRequest:
    data = mr_json(iid=iid, state=state, merger=user_json(2, "bob"), created_at=iso(updated - timedelta(days=1)),
                   merged_at=iso(updated))
    data["updated_at"] = iso(updated)
    data["sha"] = sha
    return MergeRequest.from_json(data)


class FakeForge:
    """ForgeClient stand-in: answers from canned lists and records every call."""

    base_url = "https://gitlab.test"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.mrs: list[MergeRequest] = []
        self.offline = False
        self.statuses: list[CommitStatus] = []

    def _record(self, name: str, **kwargs: Any) -> None:
        if self.offline:
            raise NetworkError("unreachable")
        self.calls.append((name, kwargs))

    def list_merge_requests(self, project_id: int, state: str | None = None, **dates: Any) -> list[MergeRequest]:
        self._record("mrs", state=state, **{k: v for k, v in dates.items() if v is not None})
        after, before = dates.get("updated_after"), dates.get("updated_before")
        return [m for m in self.mrs
                if (state is None or m.state == state)
                and (after is None or m.updated_at >= after) and (before is None or m.updated_at < before)]

    def list_merge_request_commits(self, project_id: int, mr_iid: int) -> list[Commit]:
        self._record("commits", iid=mr_iid)
        return [Commit.from_json(commit_json("aaa", "x"))]

    def list_commit_statuses(self, project_id: int, sha: str) -> list[CommitStatus]:
        self._record("statuses", sha=sha)
        return self.statuses

    def list_project_members(self, project_id: int) -> list[tuple[User, int]]:
        self._record("members")
        return [(User.from_json(user_json(1, "alice")), 30)]

    def list_protected_branches(self, project_id: int) -> list[ProtectedBranch]:
        self._record("protections")
        return [ProtectedBranch(name="main", merge_levels=(40,))]

    def get_user(self, user_id: int) -> User:
        return User.from_json(user_json(user_id, "u"))

    def download(self, url: str) -> bytes:
        self._record("download", url=url)
        return b"\x89PNG\r\n\x1a\nfake"


class StoreTests(unittest.TestCase):
    def test_schema_created_at_current_version(self) -> None:
        store = Store(MEMORY)
        self.assertEqual(store.schema_version, SCHEMA_VERSION)
        self.assertTrue(store.is_empty())

    def test_model_round_trip(self) -> None:
        original = mr(1)
        self.assertEqual(decode(MergeRequest, encode(original)), original)
        branch = ProtectedBranch(name="release/*", merge_levels=(30, 40), merge_user_ids=(7,))
        self.assertEqual(decode(ProtectedBranch, encode(branch)), branch)

    def test_merge_requests_filtered_in_the_base(self) -> None:
        store = Store(MEMORY)
        store.put_merge_requests(10, [
            MergeRequest.from_json(mr_json(iid=1, created_at="2026-01-05T08:00:00Z", merged_at="2026-01-06T08:00:00Z")),
            MergeRequest.from_json(mr_json(iid=2, created_at="2026-10-01T08:00:00Z", merged_at="2026-10-02T08:00:00Z")),
            MergeRequest.from_json(mr_json(iid=3, state="opened", created_at="2026-10-03T08:00:00Z")),
        ])
        since = datetime(2026, 9, 1, tzinfo=timezone.utc)

        def iids(**filters: Any) -> list[int]:
            return sorted(m.iid for m in store.merge_requests(10, **filters))

        self.assertEqual(iids(), [1, 2, 3])
        self.assertEqual(iids(state="merged", merged_after=since), [2])
        self.assertEqual(iids(created_after=since), [2, 3])
        self.assertEqual(iids(state="opened"), [3])
        self.assertEqual(iids(updated_after=since), [2, 3])  # the factory sets updated_at = created_at

    def test_reopening_a_file_keeps_data_and_clear_empties_it(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "gitective.db"
            Store(path).put_merge_requests(10, [mr(1), mr(2)])
            store = Store(path)
            self.assertEqual(sorted(m.iid for m in store.merge_requests(10)), [1, 2])
            store.clear()
            self.assertTrue(store.is_empty())

    def test_corrupted_file_raises_store_error(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "gitective.db"
            path.write_bytes(b"this is not a database" * 100)
            with self.assertRaises(StoreError):
                Store(path)
            path.unlink()  # ER-06 recreates the base: the file must not stay locked (Windows)

    def test_newer_schema_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "gitective.db"
            Store(path).conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
            with self.assertRaises(StoreError):
                Store(path)


class SyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.forge = FakeForge()
        self.data = ForgeData(self.forge, Store(MEMORY))  # type: ignore[arg-type]

    def names(self) -> list[str]:
        return [name for name, _ in self.forge.calls]

    def test_first_read_then_store_only_within_a_session(self) -> None:
        self.forge.mrs = [mr(1), mr(2, state="opened")]
        since = NOW - timedelta(days=30)
        self.assertEqual(len(self.data.merge_requests(10, since)), 2)
        self.assertEqual(self.names(), ["mrs", "mrs", "mrs"])  # updated since + opened + closed
        self.data.merge_requests(10, since)
        self.assertEqual(len(self.forge.calls), 3)  # second read: store only

    def test_refresh_is_incremental(self) -> None:
        self.forge.mrs = [mr(1)]
        self.data.merge_requests(10, NOW - timedelta(days=30))
        self.forge.calls.clear()
        self.data.new_session()
        self.forge.mrs.append(mr(3, updated=datetime.now(tz=timezone.utc)))
        self.assertEqual(sorted(m.iid for m in self.data.merge_requests(10, NOW - timedelta(days=30))), [1, 3])
        self.assertEqual(len(self.forge.calls), 1)
        self.assertIn("updated_after", self.forge.calls[0][1])  # only what changed since the last sync

    def test_older_period_reads_the_gap_only(self) -> None:
        self.forge.mrs = [mr(1), mr(2, updated=NOW - timedelta(days=60))]
        self.data.merge_requests(10, NOW - timedelta(days=30))
        self.forge.calls.clear()
        got = self.data.merge_requests(10, NOW - timedelta(days=90))
        self.assertEqual(sorted(m.iid for m in got), [1, 2])
        self.assertEqual(self.forge.calls[0][1]["updated_before"], NOW - timedelta(days=30))

    def test_offline_uses_stored_data(self) -> None:
        self.forge.mrs = [mr(1)]
        self.data.merge_requests(10, NOW - timedelta(days=30))
        self.data.new_session()
        self.forge.offline = True
        self.assertEqual([m.iid for m in self.data.merge_requests(10, NOW - timedelta(days=30))], [1])
        self.assertIsNotNone(self.data.offline_since)

    def test_offline_without_stored_data_raises(self) -> None:
        self.forge.offline = True
        with self.assertRaises(NetworkError):
            self.data.merge_requests(10, NOW)

    def test_merged_mr_commits_and_statuses_read_once(self) -> None:
        merged = mr(1)
        self.forge.statuses = [CommitStatus("jenkins", "success", NOW - timedelta(hours=1), NOW - timedelta(minutes=5))]
        for _ in range(2):
            self.data.new_session()
            self.assertEqual(len(self.data.mr_commits(10, merged)), 1)
            self.assertEqual(self.data.mr_statuses(10, merged)[0].name, "jenkins")
        self.assertEqual(self.names(), ["commits", "statuses"])

    def test_open_mr_commits_read_again_when_the_mr_changed(self) -> None:
        self.data.mr_commits(10, mr(1, state="opened", updated=NOW))
        self.data.mr_commits(10, mr(1, state="opened", updated=NOW))
        self.data.mr_commits(10, mr(1, state="opened", updated=NOW + timedelta(hours=1)))
        self.assertEqual(self.names(), ["commits", "commits"])

    def test_access_and_avatars_once_per_session(self) -> None:
        for _ in range(2):
            self.data.access(10)
            self.data.avatar(5, "https://gitlab.test/a.png")
        self.data.new_session()
        self.data.avatar(5, "https://gitlab.test/a.png")
        self.assertEqual(self.names(), ["members", "protections", "download", "download"])


class NamedListTests(unittest.TestCase):
    def test_replace_named_marks_missing_items_deleted_once(self) -> None:
        """BR-10, TG-08: the first date a branch was seen missing is kept."""
        store = Store(MEMORY)
        a, b = Branch("a", "s1", None), Branch("b", "s2", None)
        store.replace_named("branches", 10, [a, b], 1.0)
        store.replace_named("branches", 10, [a], 2.0)
        store.replace_named("branches", 10, [], 3.0)
        self.assertEqual({x.name: d for _, x, d in store.branches([10])}, {"a": 3.0, "b": 2.0})
        store.replace_named("branches", 11, [b], 4.0)  # other project untouched
        self.assertEqual(len(store.branches([10, 11])), 3)

    def test_commit_shas_of_stored_mr_commits(self) -> None:
        store = Store(MEMORY)
        store.put_mr_commits(10, 1, None, [Commit.from_json(commit_json("abc1234", "fix"))])
        self.assertEqual(store.mr_commit_shas([10, 11]), {(10, 1): ["abc1234" * 5]})
        self.assertEqual(store.mr_commit_shas([]), {})


if __name__ == "__main__":
    unittest.main()
