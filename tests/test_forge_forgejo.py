"""Forgejo/Gitea provider unit tests against a fake httpx transport.

Payloads use the real Gitea v1 shapes captured live from Codeberg: PR objects
with `merged`/`merged_at` and `+02:00` offset timestamps, issue comments with
`created_at` + `user.login`, the issue *timeline* with `type == "close"` for
the close actor, org repos with `owner.login`, and commits with a top-level
`created` plus `commit.{message,author}`.
"""

from __future__ import annotations

import io

import httpx
import pytest

from gitsweeper.lib.forge.forgejo import ForgejoClient, ForgejoError


def _client(transport: httpx.MockTransport, *, token: str | None = None, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    http = httpx.Client(transport=transport, headers={"Accept": "application/json"})
    return ForgejoClient(
        token=token,
        http_client=http,
        sleep_fn=lambda s: sleeps.append(s),
        warn_stream=io.StringIO(),
    ), sleeps


def _empty_page() -> httpx.Response:
    return httpx.Response(200, json=[])


def test_pull_requests_normalize_merge_and_timestamps() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/repos/o/r/pulls"
        if request.url.params.get("page") == "1":
            return httpx.Response(
                200,
                json=[
                    {
                        "number": 1,
                        "state": "closed",
                        "created_at": "2026-06-13T19:43:08+02:00",
                        "closed_at": "2026-06-14T10:00:00+02:00",
                        "merged_at": "2026-06-14T10:00:00+02:00",
                        "merged": True,
                        "user": {"login": "alice", "username": "alice"},
                    },
                    {
                        "number": 2,
                        "state": "closed",
                        "created_at": "2026-06-13T19:43:08+02:00",
                        "closed_at": "2026-06-15T09:00:00+02:00",
                        "merged_at": None,
                        "merged": False,
                        "user": {"login": "bob", "username": "bob"},
                    },
                ],
            )
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="t")
    prs = list(client.list_pull_requests("o", "r"))
    assert [p.number for p in prs] == [1, 2]
    # Merged PR: merged_at present and normalized to UTC Z (+02:00 -> 08:00Z).
    assert prs[0].merged_at == "2026-06-14T08:00:00Z"
    assert prs[0].created_at == "2026-06-13T17:43:08Z"
    assert prs[0].author == "alice"
    # Closed-without-merge: merged_at null, closed_at present.
    assert prs[1].merged_at is None
    assert prs[1].closed_at == "2026-06-15T07:00:00Z"
    # raw retained
    assert prs[0].raw["merged"] is True


def test_pull_request_merged_at_ignored_when_not_merged() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "1":
            return httpx.Response(
                200,
                json=[
                    {
                        "number": 3,
                        "state": "closed",
                        "created_at": "2026-06-13T19:43:08+02:00",
                        "closed_at": "2026-06-15T09:00:00+02:00",
                        # merged flag false but a stray timestamp present
                        "merged_at": "2026-06-15T09:00:00+02:00",
                        "merged": False,
                        "user": {"login": "bob"},
                    }
                ],
            )
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="t")
    [pr] = list(client.list_pull_requests("o", "r"))
    assert pr.merged_at is None


def test_issue_comments_normalize() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/repos/o/r/issues/5/comments"
        if request.url.params.get("page") == "1":
            return httpx.Response(
                200,
                json=[
                    {
                        "created_at": "2026-06-13T19:43:08+02:00",
                        "user": {"login": "carol"},
                        "body": "looks good",
                    }
                ],
            )
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="t")
    [c] = list(client.list_issue_comments("o", "r", 5))
    assert c.author == "carol"
    assert c.created_at == "2026-06-13T17:43:08Z"
    assert c.body == "looks good"


def test_timeline_close_actor_mapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/repos/o/r/issues/7/timeline"
        if request.url.params.get("page") == "1":
            return httpx.Response(
                200,
                json=[
                    {"type": "comment", "user": {"login": "alice"}},
                    {"type": "close", "user": {"login": "maintainer"}},
                ],
            )
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="t")
    events = list(client.list_issue_events("o", "r", 7))
    closed = [e for e in events if e.event == "closed"]
    assert len(closed) == 1
    assert closed[0].actor == "maintainer"


def test_org_repos_paginate_until_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/orgs/forgejo/repos"
        page = request.url.params.get("page")
        if page == "1":
            return httpx.Response(
                200, json=[{"name": "forgejo", "owner": {"login": "forgejo"}}]
            )
        if page == "2":
            return httpx.Response(
                200, json=[{"name": "runner", "owner": {"login": "forgejo"}}]
            )
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="t")
    repos = list(client.list_org_repos("forgejo"))
    assert [(r.owner, r.name) for r in repos] == [
        ("forgejo", "forgejo"),
        ("forgejo", "runner"),
    ]


def test_commits_normalize() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/repos/o/r/commits"
        if request.url.params.get("page") == "1":
            return httpx.Response(
                200,
                json=[
                    {
                        "sha": "abc123",
                        "author": {"login": "oliverpool"},
                        "created": "2026-06-13T03:46:44+02:00",
                        "commit": {
                            "message": "fix things\n\nTime: 1h",
                            "author": {
                                "name": "oliverpool",
                                "date": "2026-06-13T03:46:44+02:00",
                            },
                        },
                    }
                ],
            )
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="t")
    [c] = list(client.list_commits("o", "r"))
    assert c.sha == "abc123"
    assert c.author == "oliverpool"
    assert c.author_name == "oliverpool"
    assert c.message.startswith("fix things")
    assert c.author_date == "2026-06-13T01:46:44Z"


def test_auth_header_is_gitea_token_style() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="secret123")
    list(client.list_pull_requests("o", "r"))
    assert seen["auth"] == "token secret123"


def test_unauthenticated_warns_once() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _empty_page()

    warn = io.StringIO()
    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = ForgejoClient(
        token=None, http_client=http, warn_stream=warn, sleep_fn=lambda s: None
    )
    list(client.list_pull_requests("o", "r"))
    list(client.list_pull_requests("o", "r"))
    assert warn.getvalue().count("FORGEJO_TOKEN is not set") == 1


def test_rate_limit_429_retry_after() -> None:
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(429, json={}, headers={"retry-after": "3"})
        if request.url.params.get("page") == "1":
            return httpx.Response(200, json=[{"number": 9, "user": {"login": "x"},
                                              "created_at": "2026-01-01T00:00:00+00:00",
                                              "merged": False, "merged_at": None,
                                              "closed_at": None, "state": "open"}])
        return _empty_page()

    client, sleeps = _client(httpx.MockTransport(handler), token="t")
    prs = list(client.list_pull_requests("o", "r"))
    assert [p.number for p in prs] == [9]
    assert sleeps == [3.0]


def test_non_rate_limit_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    client, _ = _client(httpx.MockTransport(handler), token="t")
    with pytest.raises(ForgejoError):
        list(client.list_pull_requests("o", "r"))


def test_base_url_default_is_codeberg() -> None:
    client = ForgejoClient(token="t")
    assert client._api_url == "https://codeberg.org/api/v1"
    client.close()
