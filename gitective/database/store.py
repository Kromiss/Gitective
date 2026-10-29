"""Local SQLite store gitective.db: schema, migrations and queries (CT-10, CH-03, CH-11, CH-12)."""

from __future__ import annotations

import dataclasses
import functools
import json
import sqlite3
import threading
import types
import typing
import uuid
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from gitective.shared.i18n import t
from gitective.forge.models import Branch, Commit, CommitStatus, MergeRequest, Project, ProtectedBranch, Tag, User

T = TypeVar("T")

MEMORY = ":memory:"

# Each entry upgrades the schema by one version; never edit a released entry, append a new one.
MIGRATIONS: tuple[tuple[str, ...], ...] = (
    (
        "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        "CREATE TABLE sync (key TEXT PRIMARY KEY, covered_from REAL NOT NULL, synced_at REAL NOT NULL)",
        "CREATE TABLE projects (id INTEGER PRIMARY KEY, data TEXT NOT NULL)",
        """CREATE TABLE merge_requests (
            project_id INTEGER NOT NULL, iid INTEGER NOT NULL, state TEXT NOT NULL,
            created_at REAL NOT NULL, merged_at REAL, updated_at REAL, data TEXT NOT NULL,
            PRIMARY KEY (project_id, iid))""",
        "CREATE INDEX mr_merged ON merge_requests (project_id, merged_at)",
        "CREATE INDEX mr_created ON merge_requests (project_id, created_at)",
        """CREATE TABLE mr_commits (
            project_id INTEGER NOT NULL, iid INTEGER NOT NULL, mr_updated_at REAL, data TEXT NOT NULL,
            PRIMARY KEY (project_id, iid))""",
        """CREATE TABLE mr_statuses (
            project_id INTEGER NOT NULL, iid INTEGER NOT NULL, data TEXT NOT NULL,
            PRIMARY KEY (project_id, iid))""",
        """CREATE TABLE branch_commits (
            project_id INTEGER NOT NULL, branch TEXT NOT NULL, sha TEXT NOT NULL,
            committed_at REAL NOT NULL, data TEXT NOT NULL,
            PRIMARY KEY (project_id, branch, sha))""",
        "CREATE INDEX branch_commits_date ON branch_commits (project_id, branch, committed_at)",
        """CREATE TABLE commit_mr (
            project_id INTEGER NOT NULL, sha TEXT NOT NULL, has_mr INTEGER NOT NULL,
            PRIMARY KEY (project_id, sha))""",
        "CREATE TABLE project_access (project_id INTEGER PRIMARY KEY, members TEXT NOT NULL, protections TEXT NOT NULL)",
        "CREATE TABLE avatars (user_id INTEGER PRIMARY KEY, content BLOB NOT NULL)",
    ),
    (
        # MRs now carry assignees, reviewers and project path: read them all again.
        "DELETE FROM sync WHERE key LIKE 'mr:%'",
        """CREATE TABLE my_mrs (
            project_id INTEGER NOT NULL, iid INTEGER NOT NULL, roles TEXT NOT NULL, data TEXT NOT NULL,
            PRIMARY KEY (project_id, iid))""",
        """CREATE TABLE seen_roles (
            project_id INTEGER NOT NULL, iid INTEGER NOT NULL, role TEXT NOT NULL,
            PRIMARY KEY (project_id, iid, role))""",
        """CREATE TABLE mr_details (
            project_id INTEGER NOT NULL, iid INTEGER NOT NULL, mr_updated_at REAL, data TEXT NOT NULL,
            PRIMARY KEY (project_id, iid))""",
    ),
    (
        # Branches and tags tabs (BR-10, TG-08, TG-09): deleted_at is set when GitLab no longer lists them.
        """CREATE TABLE branches (
            project_id INTEGER NOT NULL, name TEXT NOT NULL, data TEXT NOT NULL, deleted_at REAL,
            PRIMARY KEY (project_id, name))""",
        """CREATE TABLE tags (
            project_id INTEGER NOT NULL, name TEXT NOT NULL, data TEXT NOT NULL, deleted_at REAL,
            PRIMARY KEY (project_id, name))""",
        """CREATE TABLE tag_pipelines (
            project_id INTEGER NOT NULL, name TEXT NOT NULL, commit_sha TEXT NOT NULL, data TEXT NOT NULL,
            PRIMARY KEY (project_id, name))""",
    ),
    (
        # Tag comparison (TC-06, TC-10): MRs of a commit, commits between two commits; never read twice.
        """CREATE TABLE commit_mrs (
            project_id INTEGER NOT NULL, sha TEXT NOT NULL, data TEXT NOT NULL,
            PRIMARY KEY (project_id, sha))""",
        """CREATE TABLE ref_compares (
            project_id INTEGER NOT NULL, base_sha TEXT NOT NULL, head_sha TEXT NOT NULL, data TEXT NOT NULL,
            PRIMARY KEY (project_id, base_sha, head_sha))""",
    ),
)
SCHEMA_VERSION = len(MIGRATIONS)
DATA_TABLES = ("meta", "sync", "projects", "merge_requests", "mr_commits", "mr_statuses",
               "branch_commits", "commit_mr", "project_access", "avatars", "my_mrs", "seen_roles", "mr_details",
               "branches", "tags", "tag_pipelines", "commit_mrs", "ref_compares")
RoleKey = tuple[int, int, str]  # (project_id, iid, "assignee" | "reviewer")
NAMED_TABLES = ("branches", "tags")  # lists read whole at each synchronisation and compared with the base


@dataclasses.dataclass(frozen=True)
class LinkedMr:
    """Few fields of a stored MR, read straight from SQL: MRs of a branch, MR of a tag's commit (BR-03, TG-07)."""

    project_id: int
    iid: int
    state: str
    title: str
    web_url: str
    created_at: float
    source_branch: str


class StoreError(Exception):
    """The database file is unreadable, corrupted, locked or newer than the application (ER-06)."""


# ---------------------------------------------------------------- Encoding


def ts(value: datetime | None) -> float | None:
    """POSIX timestamp of an aware datetime, for ordered SQL comparisons."""
    return value.timestamp() if value is not None else None


def encode(value: Any) -> Any:
    """JSON-ready form of a model object (dataclasses, datetimes, tuples)."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    return value


def _decode_value(hint: Any, value: Any) -> Any:
    if value is None:
        return None
    origin = typing.get_origin(hint)
    if origin in (typing.Union, types.UnionType):
        options = [a for a in typing.get_args(hint) if a is not type(None)]
        return _decode_value(options[0], value)
    if hint is datetime:
        return datetime.fromisoformat(value)
    if origin in (tuple, list):
        args = typing.get_args(hint)
        item = args[0] if args else Any
        items = [_decode_value(item, v) for v in value]
        return tuple(items) if origin is tuple else items
    if isinstance(hint, type) and dataclasses.is_dataclass(hint):
        return decode(hint, value)
    return value


@functools.cache
def _field_hints(cls: type) -> dict[str, Any]:
    """Resolved field types of a model class, computed once: get_type_hints is slow (string annotations)."""
    hints = typing.get_type_hints(cls)
    return {f.name: hints[f.name] for f in dataclasses.fields(cls)}


def decode(cls: type[T], data: dict[str, Any]) -> T:
    """Rebuild a model object from encode()'s output; unknown keys are ignored."""
    hints = _field_hints(cls)
    return cls(**{k: _decode_value(hints[k], v) for k, v in data.items() if k in hints})


def dumps(value: Any) -> str:
    return json.dumps(encode(value), ensure_ascii=False, separators=(",", ":"))


def loads_list(cls: type[T], text: str) -> list[T]:
    return [decode(cls, item) for item in json.loads(text)]


# ---------------------------------------------------------------- Store


class Store:
    """SQLite database shared by the background tasks.

    One connection per thread (CH-12); every write runs in a transaction.
    Use ":memory:" for tests: a shared in-memory database living as long as the Store.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        self._local = threading.local()
        self._anchor: sqlite3.Connection | None = None
        if self.path == MEMORY:
            self._uri = f"file:gitective-{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._anchor = self._connect()
        else:
            self._uri = None
        try:
            self._check_and_migrate()
        except (sqlite3.DatabaseError, StoreError) as exc:
            # Windows keeps an open file locked: release it so ER-06 can delete and recreate the base.
            self.close()
            if isinstance(exc, StoreError):
                raise
            raise StoreError(str(exc)) from exc

    def close(self) -> None:
        """Close this thread's connection (and the in-memory anchor)."""
        for conn in (getattr(self._local, "conn", None), self._anchor):
            if conn is not None:
                conn.close()
        self._local.conn = None
        self._anchor = None

    def _connect(self) -> sqlite3.Connection:
        if self._uri:
            conn = sqlite3.connect(self._uri, uri=True, timeout=30, check_same_thread=False)
        else:
            conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect()
            self._local.conn = conn
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Commit on success, roll back on error."""
        with self.conn as conn:
            yield conn

    def _check_and_migrate(self) -> None:
        conn = self.conn
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise StoreError(t("base locale corrompue"))
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise StoreError(t("base créée par une version plus récente de Gitective"))
        for number in range(version, SCHEMA_VERSION):
            with self.transaction() as tx:
                for statement in MIGRATIONS[number]:
                    tx.execute(statement)
                tx.execute(f"PRAGMA user_version = {number + 1}")

    @property
    def schema_version(self) -> int:
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    def clear(self) -> None:
        """Delete every stored row, keeping the schema (OC-09)."""
        with self.transaction() as tx:
            for table in DATA_TABLES:
                tx.execute(f"DELETE FROM {table}")

    def is_empty(self) -> bool:
        return all(self.conn.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone() is None
                   for t in DATA_TABLES if t != "meta")

    # ------------------------------------------------------------ Meta and sync

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self.transaction() as tx:
            tx.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))

    def sync_state(self, key: str) -> tuple[float, float] | None:
        """(covered_from, synced_at) timestamps of a synchronised data set."""
        row = self.conn.execute("SELECT covered_from, synced_at FROM sync WHERE key = ?", (key,)).fetchone()
        return (row[0], row[1]) if row else None

    def set_sync(self, key: str, covered_from: float, synced_at: float) -> None:
        with self.transaction() as tx:
            tx.execute("INSERT OR REPLACE INTO sync VALUES (?, ?, ?)", (key, covered_from, synced_at))

    def last_sync(self) -> float | None:
        row = self.conn.execute("SELECT MAX(synced_at) FROM sync").fetchone()
        return row[0] if row else None

    # ------------------------------------------------------------ Projects

    def put_projects(self, projects: Sequence[Project], read_at: str) -> None:
        with self.transaction() as tx:
            tx.execute("DELETE FROM projects")
            tx.executemany("INSERT INTO projects VALUES (?, ?)", [(p.id, dumps(p)) for p in projects])
            tx.execute("INSERT OR REPLACE INTO meta VALUES ('projects_read_at', ?)", (read_at,))

    def projects(self) -> list[Project]:
        return [decode(Project, json.loads(d)) for (d,) in self.conn.execute("SELECT data FROM projects")]

    # ------------------------------------------------------------ Merge requests

    def put_merge_requests(self, project_id: int, mrs: Iterable[MergeRequest]) -> None:
        rows = [(project_id, m.iid, m.state, ts(m.created_at), ts(m.merged_at), ts(m.updated_at), dumps(m))
                for m in mrs]
        with self.transaction() as tx:
            tx.executemany("INSERT OR REPLACE INTO merge_requests VALUES (?, ?, ?, ?, ?, ?, ?)", rows)

    def merge_requests(self, project_id: int, state: str | None = None, merged_after: datetime | None = None,
                       created_after: datetime | None = None,
                       updated_after: datetime | None = None) -> list[MergeRequest]:
        """Stored MRs of a project; the filters run in SQL so only the MRs shown are decoded."""
        where, args = ["project_id = ?"], [project_id]
        for clause, value in (("state = ?", state), ("merged_at >= ?", ts(merged_after)),
                              ("created_at >= ?", ts(created_after)), ("updated_at >= ?", ts(updated_after))):
            if value is not None:
                where.append(clause)
                args.append(value)
        rows = self.conn.execute(f"SELECT data FROM merge_requests WHERE {' AND '.join(where)}", args)
        return [decode(MergeRequest, json.loads(d)) for (d,) in rows]

    def merged_keys(self, project_ids: Iterable[int]) -> set[tuple[int, int]]:
        """(project_id, iid) of every stored merged MR of these projects (NO-04)."""
        ids = list(project_ids)
        if not ids:
            return set()
        marks = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT project_id, iid FROM merge_requests WHERE state = 'merged' AND project_id IN ({marks})", ids)
        return {(pid, iid) for pid, iid in rows}

    def get_mr_commits(self, project_id: int, iid: int) -> tuple[float | None, list[Commit]] | None:
        row = self.conn.execute("SELECT mr_updated_at, data FROM mr_commits WHERE project_id = ? AND iid = ?",
                                (project_id, iid)).fetchone()
        return (row[0], loads_list(Commit, row[1])) if row else None

    def put_mr_commits(self, project_id: int, iid: int, mr_updated_at: float | None, commits: Sequence[Commit]) -> None:
        with self.transaction() as tx:
            tx.execute("INSERT OR REPLACE INTO mr_commits VALUES (?, ?, ?, ?)",
                       (project_id, iid, mr_updated_at, dumps(list(commits))))

    def mr_commit_shas(self, project_ids: Iterable[int]) -> dict[tuple[int, int], list[str]]:
        """SHAs of the stored commits of every MR of these projects, for the SHA search (FI-20)."""
        ids = list(project_ids)
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        rows = self.conn.execute(f"SELECT project_id, iid, data FROM mr_commits WHERE project_id IN ({marks})", ids)
        return {(pid, iid): [c["id"] for c in json.loads(data)] for pid, iid, data in rows}

    def get_mr_statuses(self, project_id: int, iid: int) -> list[CommitStatus] | None:
        row = self.conn.execute("SELECT data FROM mr_statuses WHERE project_id = ? AND iid = ?",
                                (project_id, iid)).fetchone()
        return loads_list(CommitStatus, row[0]) if row else None

    def put_mr_statuses(self, project_id: int, iid: int, statuses: Sequence[CommitStatus]) -> None:
        with self.transaction() as tx:
            tx.execute("INSERT OR REPLACE INTO mr_statuses VALUES (?, ?, ?)",
                       (project_id, iid, dumps(list(statuses))))

    # ------------------------------------------------------------ Watched branches

    def put_branch_commits(self, project_id: int, branch: str, commits: Iterable[Commit]) -> None:
        rows = [(project_id, branch, c.id, ts(c.committed_date), dumps(c)) for c in commits]
        with self.transaction() as tx:
            tx.executemany("INSERT OR REPLACE INTO branch_commits VALUES (?, ?, ?, ?, ?)", rows)

    def branch_commits(self, project_id: int, branch: str, start: float, end: float) -> list[Commit]:
        rows = self.conn.execute(
            "SELECT data FROM branch_commits WHERE project_id = ? AND branch = ? AND committed_at BETWEEN ? AND ?"
            " ORDER BY committed_at DESC", (project_id, branch, start, end))
        return [decode(Commit, json.loads(d)) for (d,) in rows]

    def commit_has_mr(self, project_id: int, sha: str) -> bool | None:
        row = self.conn.execute("SELECT has_mr FROM commit_mr WHERE project_id = ? AND sha = ?",
                                (project_id, sha)).fetchone()
        return bool(row[0]) if row else None

    def put_commit_has_mr(self, project_id: int, sha: str, has_mr: bool) -> None:
        with self.transaction() as tx:
            tx.execute("INSERT OR REPLACE INTO commit_mr VALUES (?, ?, ?)", (project_id, sha, int(has_mr)))

    # ------------------------------------------------------------ Members, protections, avatars

    def get_access(self, project_id: int) -> tuple[list[tuple[User, int]], list[ProtectedBranch]] | None:
        row = self.conn.execute("SELECT members, protections FROM project_access WHERE project_id = ?",
                                (project_id,)).fetchone()
        if not row:
            return None
        members = [(decode(User, u), int(level)) for u, level in json.loads(row[0])]
        return members, loads_list(ProtectedBranch, row[1])

    def put_access(self, project_id: int, members: Sequence[tuple[User, int]],
                   protections: Sequence[ProtectedBranch]) -> None:
        with self.transaction() as tx:
            tx.execute("INSERT OR REPLACE INTO project_access VALUES (?, ?, ?)",
                       (project_id, dumps([[u, level] for u, level in members]), dumps(list(protections))))

    def get_avatar(self, user_id: int) -> bytes | None:
        """Stored image; b"" records an unsupported format (badge fallback)."""
        row = self.conn.execute("SELECT content FROM avatars WHERE user_id = ?", (user_id,)).fetchone()
        return bytes(row[0]) if row else None

    def put_avatar(self, user_id: int, content: bytes) -> None:
        with self.transaction() as tx:
            tx.execute("INSERT OR REPLACE INTO avatars VALUES (?, ?)", (user_id, content))

    # ------------------------------------------------------------ Token owner's open MRs (6.4)

    def put_my_mrs(self, items: Sequence[tuple[MergeRequest, frozenset[str]]]) -> None:
        """Replace the open MRs where the token owner is assignee or reviewer."""
        rows = [(m.project_id, m.iid, ",".join(sorted(roles)), dumps(m)) for m, roles in items]
        with self.transaction() as tx:
            tx.execute("DELETE FROM my_mrs")
            tx.executemany("INSERT INTO my_mrs VALUES (?, ?, ?, ?)", rows)

    def my_mrs(self) -> list[tuple[MergeRequest, frozenset[str]]]:
        rows = self.conn.execute("SELECT roles, data FROM my_mrs")
        return [(decode(MergeRequest, json.loads(d)), frozenset(r.split(","))) for r, d in rows]

    def seen_roles(self) -> set[RoleKey]:
        return {(p, i, r) for p, i, r in self.conn.execute("SELECT project_id, iid, role FROM seen_roles")}

    def mark_seen(self, keys: Iterable[RoleKey]) -> None:
        with self.transaction() as tx:
            tx.executemany("INSERT OR IGNORE INTO seen_roles VALUES (?, ?, ?)", list(keys))

    # ------------------------------------------------------------ MR detail panel (6.6)

    def get_mr_detail(self, project_id: int, iid: int, cls: type[T]) -> tuple[float | None, T] | None:
        row = self.conn.execute("SELECT mr_updated_at, data FROM mr_details WHERE project_id = ? AND iid = ?",
                                (project_id, iid)).fetchone()
        return (row[0], decode(cls, json.loads(row[1]))) if row else None

    def put_mr_detail(self, project_id: int, iid: int, mr_updated_at: float | None, detail: Any) -> None:
        with self.transaction() as tx:
            tx.execute("INSERT OR REPLACE INTO mr_details VALUES (?, ?, ?, ?)",
                       (project_id, iid, mr_updated_at, dumps(detail)))

    # ------------------------------------------------------------ Branches and tags (11, 12)

    def replace_named(self, table: str, project_id: int, items: Sequence[Branch] | Sequence[Tag],
                      seen_at: float) -> None:
        """Store the complete list of branches or tags of a project, read from the forge (BR-10, TG-08).

        New and changed items are written and active again (a branch recreated
        under the same name is no longer deleted); stored items missing from the
        list are kept, marked deleted at `seen_at` unless already marked.
        """
        assert table in NAMED_TABLES
        names = [i.name for i in items]
        with self.transaction() as tx:
            tx.executemany(f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?, NULL)",
                           [(project_id, i.name, dumps(i)) for i in items])
            marks = ",".join("?" * len(names))
            missing = f" AND name NOT IN ({marks})" if names else ""
            tx.execute(f"UPDATE {table} SET deleted_at = ? WHERE project_id = ? AND deleted_at IS NULL{missing}",
                       [seen_at, project_id, *names])

    def branches(self, project_ids: Iterable[int]) -> list[tuple[int, Branch, float | None]]:
        """(project_id, branch, deleted_at) of these projects."""
        return [(pid, decode(Branch, item), deleted) for pid, item, deleted in self._named("branches", project_ids)]

    def tags(self, project_ids: Iterable[int]) -> list[tuple[int, Tag, float | None]]:
        """(project_id, tag, deleted_at) of these projects."""
        return [(pid, decode(Tag, item), deleted) for pid, item, deleted in self._named("tags", project_ids)]

    def _named(self, table: str, project_ids: Iterable[int]) -> list[tuple[int, dict[str, Any], float | None]]:
        ids = list(project_ids)
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        rows = self.conn.execute(f"SELECT project_id, data, deleted_at FROM {table} WHERE project_id IN ({marks})", ids)
        return [(pid, json.loads(data), deleted) for pid, data, deleted in rows]

    def linked_mrs(self, project_ids: Iterable[int]) -> list[LinkedMr]:
        """Stored MRs of these projects, decoded lightly, for the "MR liées" column (BR-03)."""
        ids = list(project_ids)
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        rows = self.conn.execute(
            "SELECT project_id, iid, state, json_extract(data, '$.title'), json_extract(data, '$.web_url'),"
            f" created_at, json_extract(data, '$.source_branch') FROM merge_requests WHERE project_id IN ({marks})",
            ids)
        return [LinkedMr(*row) for row in rows]

    def mr_of_commit(self, project_id: int, sha: str) -> LinkedMr | None:
        """Stored MR whose merge, squash or head commit is `sha` (TG-07)."""
        row = self.conn.execute(
            "SELECT project_id, iid, state, json_extract(data, '$.title'), json_extract(data, '$.web_url'),"
            " created_at, json_extract(data, '$.source_branch') FROM merge_requests WHERE project_id = ? AND ? IN"
            " (json_extract(data, '$.merge_commit_sha'), json_extract(data, '$.squash_commit_sha'),"
            " json_extract(data, '$.sha')) ORDER BY created_at DESC LIMIT 1", (project_id, sha)).fetchone()
        return LinkedMr(*row) if row else None

    def get_tag_pipeline(self, project_id: int, name: str, cls: type[T]) -> tuple[str, T] | None:
        """(commit SHA it was read for, stored pipeline data) of a tag (TG-09)."""
        row = self.conn.execute("SELECT commit_sha, data FROM tag_pipelines WHERE project_id = ? AND name = ?",
                                (project_id, name)).fetchone()
        return (row[0], decode(cls, json.loads(row[1]))) if row else None

    def put_tag_pipeline(self, project_id: int, name: str, commit_sha: str, data: Any) -> None:
        with self.transaction() as tx:
            tx.execute("INSERT OR REPLACE INTO tag_pipelines VALUES (?, ?, ?, ?)",
                       (project_id, name, commit_sha, dumps(data)))

    # ------------------------------------------------------------ Tag comparison (12.1)

    def get_commit_mrs(self, project_id: int, sha: str) -> list[MergeRequest] | None:
        """MRs GitLab links to a commit, as read once (TC-06); None when never read."""
        row = self.conn.execute("SELECT data FROM commit_mrs WHERE project_id = ? AND sha = ?",
                                (project_id, sha)).fetchone()
        return loads_list(MergeRequest, row[0]) if row else None

    def put_commit_mrs(self, project_id: int, sha: str, mrs: Sequence[MergeRequest]) -> None:
        with self.transaction() as tx:
            tx.execute("INSERT OR REPLACE INTO commit_mrs VALUES (?, ?, ?)", (project_id, sha, dumps(list(mrs))))
            tx.execute("INSERT OR REPLACE INTO commit_mr VALUES (?, ?, ?)", (project_id, sha, int(bool(mrs))))

    def get_compare(self, project_id: int, base_sha: str, head_sha: str) -> list[Commit] | None:
        """Commits reachable from head and not from base, as read once (TC-10)."""
        row = self.conn.execute(
            "SELECT data FROM ref_compares WHERE project_id = ? AND base_sha = ? AND head_sha = ?",
            (project_id, base_sha, head_sha)).fetchone()
        return loads_list(Commit, row[0]) if row else None

    def put_compare(self, project_id: int, base_sha: str, head_sha: str, commits: Sequence[Commit]) -> None:
        with self.transaction() as tx:
            tx.execute("INSERT OR REPLACE INTO ref_compares VALUES (?, ?, ?, ?)",
                       (project_id, base_sha, head_sha, dumps(list(commits))))
