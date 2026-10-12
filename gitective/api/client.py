"""Generic GitLab REST API v4 client built on urllib only."""

from __future__ import annotations

import json
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from gitective.api.errors import (
    AuthenticationError,
    GitLabError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    SSLVerificationError,
)
from gitective.api.models import Commit, MergeRequest, Project, User

Opener = Callable[..., Any]

DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRY_DELAYS: tuple[float, ...] = (2.0, 4.0, 8.0)
PER_PAGE = 100


def _iso(value: datetime | None) -> str | None:
    """Format a datetime for GitLab query parameters (UTC, ISO 8601)."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.astimezone()
    return value.astimezone().isoformat()


class GitLabClient:
    """Thin, typed wrapper around the GitLab REST API v4.

    Handles authentication, pagination, retries on rate limiting and
    timeouts, and maps HTTP / network failures to GitLabError subclasses.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        verify_ssl: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
        retry_delays: Sequence[float] = DEFAULT_RETRY_DELAYS,
        opener: Opener | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/v4"
        self.token = token
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.retry_delays = tuple(retry_delays)
        self._sleep = sleep
        self._ssl_context = ssl.create_default_context()
        if not verify_ssl:
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE
        self._opener = opener or self._default_opener

    # ------------------------------------------------------------------ HTTP

    def _default_opener(self, request: urllib.request.Request, timeout: float) -> Any:
        return urllib.request.urlopen(request, timeout=timeout, context=self._ssl_context)

    def _build_url(self, path: str, params: dict[str, Any] | None) -> str:
        url = f"{self.api_url}/{path.lstrip('/')}"
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
        return url

    def _send(self, url: str, authenticated: bool = True) -> tuple[bytes, dict[str, str]]:
        """Perform a GET with retries; return the body and response headers."""
        headers = {"Accept": "application/json", "User-Agent": "Gitective"}
        if authenticated:
            headers["PRIVATE-TOKEN"] = self.token
        attempts = len(self.retry_delays) + 1
        for attempt in range(attempts):
            last = attempt == attempts - 1
            request = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with self._opener(request, self.timeout) as response:
                    body = response.read()
                    return body, {k.lower(): v for k, v in response.headers.items()}
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and not last:
                    self._sleep(self.retry_delays[attempt])
                    continue
                raise self._http_error(exc) from exc
            except (TimeoutError, socket.timeout) as exc:
                if not last:
                    self._sleep(self.retry_delays[attempt])
                    continue
                raise NetworkError(f"Request timed out after {self.timeout:.0f} s") from exc
            except urllib.error.URLError as exc:
                reason = exc.reason
                if isinstance(reason, ssl.SSLError):
                    raise SSLVerificationError(f"SSL error: {reason}") from exc
                if isinstance(reason, (TimeoutError, socket.timeout)) and not last:
                    self._sleep(self.retry_delays[attempt])
                    continue
                raise NetworkError(f"Cannot reach {self.base_url}: {reason}") from exc
            except ssl.SSLError as exc:
                raise SSLVerificationError(f"SSL error: {exc}") from exc
            except OSError as exc:
                raise NetworkError(f"Network error: {exc}") from exc
        raise NetworkError("Request failed")  # pragma: no cover - loop always returns or raises

    @staticmethod
    def _http_error(exc: urllib.error.HTTPError) -> GitLabError:
        message = f"HTTP {exc.code}"
        try:
            payload = json.loads(exc.read() or b"{}")
            detail = payload.get("message") or payload.get("error")
            if detail:
                message += f": {detail}"
        except (ValueError, AttributeError, OSError):
            pass
        mapping: dict[int, type[GitLabError]] = {
            401: AuthenticationError,
            403: PermissionDeniedError,
            404: NotFoundError,
            429: RateLimitError,
        }
        return mapping.get(exc.code, GitLabError)(message, status=exc.code)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        body, _ = self._send(self._build_url(path, params))
        return json.loads(body or b"null")

    def _paginate(self, path: str, params: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        """Yield every item of a paginated collection, following X-Next-Page."""
        query = dict(params or {})
        query.setdefault("per_page", PER_PAGE)
        page: str | None = "1"
        while page:
            query["page"] = page
            body, headers = self._send(self._build_url(path, query))
            yield from json.loads(body or b"[]")
            page = headers.get("x-next-page") or None

    def _paginate_parallel(self, path: str, params: dict[str, Any], workers: int) -> list[dict[str, Any]]:
        """Fetch page 1, then every other page concurrently, keeping GitLab's order."""
        query = {**params, "per_page": PER_PAGE, "page": 1}
        body, headers = self._send(self._build_url(path, query))
        items: list[dict[str, Any]] = json.loads(body or b"[]")
        pages = int(headers.get("x-total-pages") or 0)
        if not pages and headers.get("x-next-page"):
            # shortcut: GitLab hides the page count above 10,000 items, so read sequentially (page 1 twice).
            return list(self._paginate(path, params))

        def fetch(page: int) -> list[dict[str, Any]]:
            return json.loads(self._send(self._build_url(path, {**query, "page": page}))[0] or b"[]")

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            for page_items in pool.map(fetch, range(2, pages + 1)):
                items.extend(page_items)
        return items

    # --------------------------------------------------------------- Methods

    def current_user(self) -> User:
        """Return the user owning the token (used to test the connection)."""
        return User.from_json(self._get("user"))

    def get_user(self, user_id: int) -> User:
        """Return a user by numeric ID."""
        return User.from_json(self._get(f"users/{user_id}"))

    def search_users(self, query: str) -> list[User]:
        """Search users by name, username or public e-mail."""
        return [User.from_json(u) for u in self._paginate("users", {"search": query})]

    def list_projects(self, membership: bool = True, workers: int = 1) -> list[Project]:
        """List projects visible to the token (member projects by default).

        workers > 1 fetches the pages concurrently.
        """
        params = {"membership": "true" if membership else None, "simple": "true", "order_by": "path", "sort": "asc"}
        return [Project.from_json(p) for p in self._paginate_parallel("projects", params, workers)]

    def get_project(self, project_id: int | str) -> Project:
        """Return one project by ID or URL-encoded path."""
        ref = urllib.parse.quote(str(project_id), safe="")
        return Project.from_json(self._get(f"projects/{ref}"))

    def branch_exists(self, project_id: int, branch: str) -> bool:
        """Tell whether a branch exists in the project."""
        ref = urllib.parse.quote(branch, safe="")
        try:
            self._get(f"projects/{project_id}/repository/branches/{ref}")
            return True
        except NotFoundError:
            return False

    def list_merge_requests(
        self,
        project_id: int,
        state: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        updated_after: datetime | None = None,
        updated_before: datetime | None = None,
    ) -> list[MergeRequest]:
        """List merge requests of a project, optionally filtered by state and dates.

        state: "opened", "closed", "merged", "locked" or None for all.
        """
        params = {
            "state": state,
            "created_after": _iso(created_after),
            "created_before": _iso(created_before),
            "updated_after": _iso(updated_after),
            "updated_before": _iso(updated_before),
            "order_by": "created_at",
            "sort": "desc",
        }
        return [MergeRequest.from_json(m) for m in self._paginate(f"projects/{project_id}/merge_requests", params)]

    def list_merge_request_commits(self, project_id: int, mr_iid: int) -> list[Commit]:
        """List the commits of a merge request."""
        return [Commit.from_json(c) for c in
                self._paginate(f"projects/{project_id}/merge_requests/{mr_iid}/commits")]

    def list_commits(
        self,
        project_id: int,
        ref_name: str,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Commit]:
        """List commits reachable from a branch, optionally within a date range."""
        params = {"ref_name": ref_name, "since": _iso(since), "until": _iso(until)}
        return [Commit.from_json(c) for c in self._paginate(f"projects/{project_id}/repository/commits", params)]

    def list_commit_merge_requests(self, project_id: int, sha: str) -> list[MergeRequest]:
        """List merge requests associated with a commit."""
        data = self._get(f"projects/{project_id}/repository/commits/{sha}/merge_requests")
        return [MergeRequest.from_json(m) for m in data or []]

    def download(self, url: str) -> bytes:
        """Download a raw file (e.g. an avatar).

        The token is only sent to the GitLab instance itself, never to a
        third-party host such as Gravatar.
        """
        same_host = urllib.parse.urlparse(url).netloc == urllib.parse.urlparse(self.base_url).netloc
        body, _ = self._send(url, authenticated=same_host)
        return body
