"""Local SQLite store gitective.db: schema, migrations and queries (CT-10, CH-03, CH-11, CH-12)."""

from __future__ import annotations

import dataclasses
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

from gitective.api.models import Commit, CommitStatus, MergeRequest, Project, ProtectedBranch, User

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
)
SCHEMA_VERSION = len(MIGRATIONS)
DATA_TABLES = ("meta", "sync", "projects", "merge_requests", "mr_commits", "mr_statuses",
               "branch_commits", "commit_mr", "project_access", "avatars")


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


def decode(cls: type[T], data: dict[str, Any]) -> T:
    """Rebuild a model object from encode()'s output; unknown keys are ignored."""
    hints = typing.get_type_hints(cls)
    known = {f.name for f in dataclasses.fields(cls)}  # type: ignore[arg-type]
    return cls(**{k: _decode_value(hints[k], v) for k, v in data.items() if k in known})


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
        except sqlite3.DatabaseError as exc:
            raise StoreError(str(exc)) from exc

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
            raise StoreError("base locale corrompue")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise StoreError("base créée par une version plus récente de Gitective")
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

    def merge_requests(self, project_id: int) -> list[MergeRequest]:
        rows = self.conn.execute("SELECT data FROM merge_requests WHERE project_id = ?", (project_id,))
        return [decode(MergeRequest, json.loads(d)) for (d,) in rows]

    def get_mr_commits(self, project_id: int, iid: int) -> tuple[float | None, list[Commit]] | None:
        row = self.conn.execute("SELECT mr_updated_at, data FROM mr_commits WHERE project_id = ? AND iid = ?",
                                (project_id, iid)).fetchone()
        return (row[0], loads_list(Commit, row[1])) if row else None

    def put_mr_commits(self, project_id: int, iid: int, mr_updated_at: float | None, commits: Sequence[Commit]) -> None:
        with self.transaction() as tx:
            tx.execute("INSERT OR REPLACE INTO mr_commits VALUES (?, ?, ?, ?)",
                       (project_id, iid, mr_updated_at, dumps(list(commits))))

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
