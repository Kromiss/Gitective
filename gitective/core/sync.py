"""Synchronisation forge → local store, incremental and offline-tolerant (CH-03..CH-09).

Every read goes through ForgeData: it updates the store when needed, then
answers from the store. A data set is brought up to date once per session:
at the first read after launch or after Refresh (CH-05). Immutable data
(commits and CI statuses of a merged MR, MR link of a commit) is never read
twice (CH-09). When the instance is unreachable, stored data is used and
`offline_since` tells the date of the last synchronisation (CH-08).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import TypeVar

from gitective.api.errors import NetworkError
from gitective.api.forge import ForgeClient
from gitective.api.models import Commit, CommitStatus, MergeRequest, ProtectedBranch, User
from gitective.core.storage import Store, ts

T = TypeVar("T")

EPOCH = 0.0  # covered_from value meaning "the whole history"
MR_OVERLAP = timedelta(minutes=5)  # re-read margin for clock differences
# Commits are filtered by commit date, which can be older than the push: re-read a few days.
COMMIT_OVERLAP = timedelta(days=3)


def _dt(value: float) -> datetime:
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class ForgeData:
    """Forge data seen through the local store."""

    def __init__(self, client: ForgeClient | None, store: Store) -> None:
        self.client = client
        self.store = store
        self._fresh: set[str] = set()
        self._branches: dict[tuple[int, str], bool] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self.offline_since: datetime | None = None

    # ------------------------------------------------------------ Session

    def new_session(self) -> None:
        """Next reads bring every data set up to date again (Refresh button)."""
        with self._guard:
            self._fresh.clear()
            self._branches.clear()
            self.offline_since = None

    @contextmanager
    def _lock(self, key: str) -> Iterator[None]:
        """Serialise the synchronisation of one data set across threads."""
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            yield

    def _offline(self, synced_at: float | None) -> None:
        """Remember that stored data is shown because the forge is unreachable."""
        when = _dt(synced_at) if synced_at else _dt(self.store.last_sync() or 0)
        with self._guard:
            if self.offline_since is None or when < self.offline_since:
                self.offline_since = when

    def _require_client(self) -> ForgeClient:
        if self.client is None:
            raise NetworkError("Connexion GitLab non configurée")
        return self.client

    # ------------------------------------------------------------ Merge requests

    def merge_requests(self, project_id: int, since: datetime | None) -> list[MergeRequest]:
        """Every stored MR of a project, after making sure MRs updated since `since` are there.

        since=None asks for the whole history. Open and closed MRs are always complete.
        """
        key = f"mr:{project_id}"
        wanted = ts(since) if since is not None else EPOCH
        with self._lock(key):
            state = self.store.sync_state(key)
            try:
                self._sync_mrs(key, project_id, wanted, state)
            except NetworkError:
                if state is None:
                    raise
                self._offline(state[1])
        return self.store.merge_requests(project_id)

    def _sync_mrs(self, key: str, project_id: int, wanted: float, state: tuple[float, float] | None) -> None:
        client = self._require_client()
        started = _now()
        if state is None:
            if wanted == EPOCH:
                mrs = client.list_merge_requests(project_id)
            else:
                mrs = [*client.list_merge_requests(project_id, updated_after=_dt(wanted)),
                       *client.list_merge_requests(project_id, state="opened"),
                       *client.list_merge_requests(project_id, state="closed")]
            self.store.put_merge_requests(project_id, mrs)
            self.store.set_sync(key, wanted, started.timestamp())
            self._fresh.add(key)
            return
        covered, synced = state
        if wanted < covered:  # older period requested: fill the gap only
            older = client.list_merge_requests(project_id, updated_after=_dt(wanted) if wanted > EPOCH else None,
                                               updated_before=_dt(covered))
            self.store.put_merge_requests(project_id, older)
            covered = wanted
        if key not in self._fresh:  # incremental update (CH-05)
            changed = client.list_merge_requests(project_id, updated_after=_dt(synced) - MR_OVERLAP)
            self.store.put_merge_requests(project_id, changed)
            synced = started.timestamp()
            self._fresh.add(key)
        self.store.set_sync(key, covered, synced)

    def mr_commits(self, project_id: int, mr: MergeRequest) -> list[Commit]:
        """Commits of an MR; read once for a merged MR, again when an open MR changed."""
        stored = self.store.get_mr_commits(project_id, mr.iid)
        if stored is not None and (mr.merged_at is not None or stored[0] == ts(mr.updated_at)):
            return stored[1]
        try:
            commits = self._require_client().list_merge_request_commits(project_id, mr.iid)
        except NetworkError:
            if stored is None:
                raise
            self._offline(None)
            return stored[1]
        self.store.put_mr_commits(project_id, mr.iid, ts(mr.updated_at), commits)
        return commits

    def mr_statuses(self, project_id: int, mr: MergeRequest) -> list[CommitStatus]:
        """CI statuses of the head commit of a merged MR, read once (PI-05)."""
        stored = self.store.get_mr_statuses(project_id, mr.iid)
        if stored is not None:
            return stored
        if not mr.sha:
            return []
        statuses = self._require_client().list_commit_statuses(project_id, mr.sha)
        if mr.merged_at is not None:
            self.store.put_mr_statuses(project_id, mr.iid, statuses)
        return statuses

    # ------------------------------------------------------------ Watched branches

    def branch_exists(self, project_id: int, branch: str) -> bool:
        key = (project_id, branch)
        if key not in self._branches:
            try:
                self._branches[key] = self._require_client().branch_exists(project_id, branch)
            except NetworkError:
                if self.store.sync_state(f"commits:{project_id}:{branch}") is None:
                    raise
                self._offline(None)
                return True
        return self._branches[key]

    def branch_commits(self, project_id: int, branch: str, start: datetime, end: datetime) -> list[Commit]:
        """Commits of a branch whose commit date lies in [start, end]."""
        key = f"commits:{project_id}:{branch}"
        with self._lock(key):
            state = self.store.sync_state(key)
            try:
                client = self._require_client()
                started = _now()
                if state is None:
                    self.store.put_branch_commits(project_id, branch, client.list_commits(project_id, branch, start))
                    self.store.set_sync(key, ts(start) or EPOCH, started.timestamp())
                    self._fresh.add(key)
                else:
                    covered, synced = state
                    if ts(start) < covered:  # type: ignore[operator]
                        self.store.put_branch_commits(project_id, branch,
                                                      client.list_commits(project_id, branch, start, _dt(covered)))
                        covered = ts(start)  # type: ignore[assignment]
                    if key not in self._fresh:
                        recent = client.list_commits(project_id, branch, _dt(synced) - COMMIT_OVERLAP)
                        self.store.put_branch_commits(project_id, branch, recent)
                        synced = started.timestamp()
                        self._fresh.add(key)
                    self.store.set_sync(key, covered, synced)
            except NetworkError:
                if state is None:
                    raise
                self._offline(state[1])
        return self.store.branch_commits(project_id, branch, ts(start), ts(end))  # type: ignore[arg-type]

    def commit_has_mr(self, project_id: int, sha: str) -> bool:
        """Whether a commit belongs to an MR; the answer is stored for good (CO-08)."""
        stored = self.store.commit_has_mr(project_id, sha)
        if stored is not None:
            return stored
        has_mr = bool(self._require_client().list_commit_merge_requests(project_id, sha))
        self.store.put_commit_has_mr(project_id, sha, has_mr)
        return has_mr

    # ------------------------------------------------------------ Merge rights

    def access(self, project_id: int) -> tuple[list[tuple[User, int]], list[ProtectedBranch]]:
        """Project members and branch protections, read again once per session."""
        key = f"access:{project_id}"
        return self._per_session(
            key,
            lambda: self.store.get_access(project_id),
            lambda: self._fetch_access(project_id),
        )

    def _fetch_access(self, project_id: int) -> tuple[list[tuple[User, int]], list[ProtectedBranch]]:
        client = self._require_client()
        members, protections = client.list_project_members(project_id), client.list_protected_branches(project_id)
        self.store.put_access(project_id, members, protections)
        return members, protections

    def _per_session(self, key: str, stored: Callable[[], T | None], fetch: Callable[[], T]) -> T:
        """Fetch once per session; fall back to the stored copy when offline."""
        with self._lock(key):
            if key in self._fresh:
                value = stored()
                if value is not None:
                    return value
            try:
                value = fetch()
            except NetworkError:
                value = stored()
                if value is None:
                    raise
                self._offline(None)
                return value
            self._fresh.add(key)
            return value

    # ------------------------------------------------------------ Avatars

    def avatar(self, user_id: int, url: str | None) -> bytes | None:
        """Raw avatar bytes, downloaded again once per session (AV-07); b"" = unsupported format."""
        def fetch() -> bytes:
            client = self._require_client()
            link = url or client.get_user(user_id).avatar_url
            data = client.download(link) if link else b""
            self.store.put_avatar(user_id, data)
            return data

        return self._per_session(f"avatar:{user_id}", lambda: self.store.get_avatar(user_id), fetch)
