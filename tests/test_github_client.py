from __future__ import annotations

import io
from typing import Any

import httpx
import pytest

from gitsweeper.lib.github_client import GitHubClient, _parse_next_link


def _client(transport: httpx.MockTransport, *, token: str | None = None, sleeps: list[float] | None = None, now: float = 0.0):
    sleeps = sleeps if sleeps is not None else []
    http = httpx.Client(
        transport=transport,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "test"},
    )
    return GitHubClient(
        token=token,
        http_client=http,
        sleep_fn=lambda s: sleeps.append(s),
        now_fn=lambda: now,
        warn_stream=io.StringIO(),
    ), sleeps


def test_parse_next_link_picks_only_next() -> None:
    header = (
        '<https://api.github.com/repositories/1/pulls?page=2>; rel="next", '
        '<https://api.github.com/repositories/1/pulls?page=5>; rel="last"'
    )
    assert _parse_next_link(header) == "https://api.github.com/repositories/1/pulls?page=2"
    assert _parse_next_link("") is None


def test_list_pull_requests_follows_link_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page")
        if page is None:
            return httpx.Response(
                200,
                json=[{"number": 1}, {"number": 2}],
                headers={
                    "x-ratelimit-remaining": "100",
                    "link": '<https://api.github.com/repos/o/r/pulls?page=2>; rel="next"',
                },
            )
        if page == "2":
            return httpx.Response(
                200,
                json=[{"number": 3}],
                headers={"x-ratelimit-remaining": "100"},
            )
        return httpx.Response(404, text=f"unexpected page {page}")

    client, sleeps = _client(httpx.MockTransport(handler), token="t")
    nums = [p["number"] for p in client.list_pull_requests("o", "r")]
    assert nums == [1, 2, 3]
    assert sleeps == []  # no rate-limit waits


def test_authorization_header_present_when_token_given() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=[], headers={"x-ratelimit-remaining": "100"})

    client, _ = _client(httpx.MockTransport(handler), token="ghp_secret123")
    list(client.list_pull_requests("o", "r"))
    assert seen["auth"] == "Bearer ghp_secret123"


def test_no_authorization_header_when_token_absent_and_warns_once() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json=[], headers={"x-ratelimit-remaining": "100"})

    warn_stream = io.StringIO()
    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = GitHubClient(token=None, http_client=http, warn_stream=warn_stream, sleep_fn=lambda s: None, now_fn=lambda: 0.0)
    list(client.list_pull_requests("o", "r"))
    list(client.list_pull_requests("o", "r"))
    assert seen == [None, None]
    # Warned once across two calls
    assert warn_stream.getvalue().count("GITHUB_TOKEN is not set") == 1


def test_secondary_rate_limit_sleep_and_retry() -> None:
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(
                429,
                json={"message": "secondary rate limit"},
                headers={"retry-after": "7"},
            )
        return httpx.Response(200, json=[{"number": 99}], headers={"x-ratelimit-remaining": "100"})

    client, sleeps = _client(httpx.MockTransport(handler), token="t")
    nums = [p["number"] for p in client.list_pull_requests("o", "r")]
    assert nums == [99]
    assert state["calls"] == 2
    assert sleeps == [7.0]


def test_primary_rate_limit_sleeps_until_reset_before_next_request() -> None:
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(
                200,
                json=[{"number": 1}],
                headers={
                    "x-ratelimit-remaining": "0",
                    "x-ratelimit-reset": "100",
                    "link": '<https://api.github.com/repos/o/r/pulls?page=2>; rel="next"',
                },
            )
        return httpx.Response(
            200,
            json=[{"number": 2}],
            headers={"x-ratelimit-remaining": "5"},
        )

    client, sleeps = _client(httpx.MockTransport(handler), token="t", now=40.0)
    nums = [p["number"] for p in client.list_pull_requests("o", "r")]
    assert nums == [1, 2]
    # Slept the gap between now=40 and reset=100 = 60s before the next request.
    assert sleeps == [60.0]


def test_4xx_other_than_rate_limit_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    from gitsweeper.lib.github_client import GitHubError

    client, _ = _client(httpx.MockTransport(handler), token="t")
    with pytest.raises(GitHubError):
        list(client.list_pull_requests("o", "r"))
