"""Tests of GitLabClient with simulated HTTP responses (no network)."""

from __future__ import annotations

import json
import socket
import ssl
import unittest
import urllib.error
import urllib.parse
from email.message import Message
from io import BytesIO
from typing import Any

from gitective.api.client import GitLabClient
from gitective.api.errors import (
    AuthenticationError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    SSLVerificationError,
)
from gitective.core.cache import SessionCache
from gitective.core.orphan_commits import BranchNotFoundError, find_orphan_commits
from gitective.config.settings import TrackedProject
from gitective.core.dates import day_range, parse_date
from tests.factories import commit_json, mr_json, user_json


class FakeResponse:
    """Minimal stand-in for the object returned by urllib.request.urlopen."""

    def __init__(self, payload: Any, headers: dict[str, str] | None = None) -> None:
        self._body = json.dumps(payload).encode()
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def http_error(code: int, message: str = "") -> urllib.error.HTTPError:
    body = BytesIO(json.dumps({"message": message}).encode())
    return urllib.error.HTTPError("https://gitlab.test", code, message, Message(), body)


class FakeOpener:
    """Returns queued responses (or raises queued errors) and records requests."""

    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[Any] = []

    def __call__(self, request: Any, timeout: float) -> Any:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def query(self, index: int) -> dict[str, list[str]]:
        return urllib.parse.parse_qs(urllib.parse.urlparse(self.requests[index].full_url).query)


def make_client(opener: FakeOpener) -> tuple[GitLabClient, list[float]]:
    sleeps: list[float] = []
    client = GitLabClient("https://gitlab.test/", "secret", opener=opener, sleep=sleeps.append)
    return client, sleeps


class ClientTests(unittest.TestCase):
    def test_token_header_and_typed_result(self) -> None:
        opener = FakeOpener(FakeResponse(user_json(5, "alice")))
        client, _ = make_client(opener)
        user = client.current_user()
        self.assertEqual((user.id, user.username), (5, "alice"))
        self.assertEqual(opener.requests[0].get_header("Private-token"), "secret")
        self.assertEqual(opener.requests[0].full_url, "https://gitlab.test/api/v4/user")

    def test_pagination_follows_next_page(self) -> None:
        opener = FakeOpener(
            FakeResponse([mr_json(iid=1)], {"X-Next-Page": "2"}),
            FakeResponse([mr_json(iid=2)], {"X-Next-Page": ""}),
        )
        client, _ = make_client(opener)
        mrs = client.list_merge_requests(10, state="merged")
        self.assertEqual([m.iid for m in mrs], [1, 2])
        self.assertEqual(opener.query(1)["page"], ["2"])
        self.assertEqual(opener.query(0)["state"], ["merged"])
        self.assertEqual(mrs[0].source_branch, "feature/PROJ-1-thing")

    def test_http_errors_are_mapped(self) -> None:
        for code, error in ((401, AuthenticationError), (403, PermissionDeniedError), (404, NotFoundError)):
            client, _ = make_client(FakeOpener(http_error(code, "nope")))
            with self.assertRaises(error):
                client.current_user()

    def test_rate_limit_retries_then_succeeds(self) -> None:
        opener = FakeOpener(http_error(429), http_error(429), FakeResponse(user_json(1, "a")))
        client, sleeps = make_client(opener)
        self.assertEqual(client.current_user().id, 1)
        self.assertEqual(sleeps, [2.0, 4.0])

    def test_rate_limit_gives_up_after_three_retries(self) -> None:
        client, sleeps = make_client(FakeOpener(*(http_error(429) for _ in range(4))))
        with self.assertRaises(RateLimitError):
            client.current_user()
        self.assertEqual(sleeps, [2.0, 4.0, 8.0])

    def test_timeout_retries_then_network_error(self) -> None:
        client, sleeps = make_client(FakeOpener(*(socket.timeout() for _ in range(4))))
        with self.assertRaises(NetworkError):
            client.current_user()
        self.assertEqual(len(sleeps), 3)

    def test_ssl_and_unreachable(self) -> None:
        client, _ = make_client(FakeOpener(urllib.error.URLError(ssl.SSLError("bad cert"))))
        with self.assertRaises(SSLVerificationError):
            client.current_user()
        client, _ = make_client(FakeOpener(urllib.error.URLError(ConnectionRefusedError())))
        with self.assertRaises(NetworkError):
            client.current_user()

    def test_token_not_sent_to_other_hosts(self) -> None:
        opener = FakeOpener(FakeResponse("x"))
        client, _ = make_client(opener)
        client.download("https://www.gravatar.com/avatar/abc")
        self.assertIsNone(opener.requests[0].get_header("Private-token"))

    def test_disable_ssl_verification(self) -> None:
        client = GitLabClient("https://gitlab.test", "t", verify_ssl=False)
        self.assertEqual(client._ssl_context.verify_mode, ssl.CERT_NONE)


class OrphanCommitTests(unittest.TestCase):
    def test_commits_without_mr_are_reported(self) -> None:
        opener = FakeOpener(
            FakeResponse({"name": "main"}),                                   # branch exists
            FakeResponse([commit_json("aaa", "with mr"), commit_json("bbb", "direct push")]),
            FakeResponse([mr_json()]),                                        # aaa → MR
            FakeResponse([]),                                                 # bbb → none
        )
        client, _ = make_client(opener)
        project = TrackedProject(id=10, path="group/repo", branch="main")
        period = day_range(parse_date("01/10/2026"), parse_date("07/10/2026"))
        progress: list[tuple[int, int]] = []
        orphans = find_orphan_commits(client, SessionCache(), [project], period,
                                      progress=lambda d, t: progress.append((d, t)), workers=1)
        self.assertEqual([o.commit.short_id for o in orphans], ["bbb"])
        self.assertEqual(progress[-1], (2, 2))

    def test_missing_branch_is_reported(self) -> None:
        client, _ = make_client(FakeOpener(http_error(404)))
        project = TrackedProject(id=10, path="group/repo", branch="develop")
        period = day_range(parse_date("01/10/2026"), parse_date("07/10/2026"))
        errors: list[Exception] = []
        self.assertEqual(find_orphan_commits(client, SessionCache(), [project], period, on_error=errors.append), [])
        self.assertIsInstance(errors[0], BranchNotFoundError)


if __name__ == "__main__":
    unittest.main()
