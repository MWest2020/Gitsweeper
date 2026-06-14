"""GitLab provider unit tests against a fake httpx transport.

Payloads use the real GitLab v4 shapes captured live from gitlab.com: merge
requests with `iid` (per-project number), `id` (global, ignored), `state` in
{opened,closed,merged}, `author.username`, and `Z`-with-millis timestamps;
notes with `created_at` + `author.username` + `body`; resource state events
with `state` + `user.username`; commits with `id`/`message`/`author_name`/
`authored_date`; group projects with `path` + `namespace.full_path`.
"""

from __future__ import annotations

import io

import httpx
import pytest

from gitsweeper.lib.forge.gitlab import GitLabClient, GitLabError


def _client(transport: httpx.MockTransport, *, token: str | None = None, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    http = httpx.Client(transport=transport, headers={"Accept": "application/json"})
    return GitLabClient(
        token=token,
        http_client=http,
        sleep_fn=lambda s: sleeps.append(s),
        warn_stream=io.StringIO(),
    ), sleeps


def _empty_page() -> httpx.Response:
    return httpx.Response(200, json=[])


def test_pull_requests_normalize_iid_state_and_timestamps() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Namespaced project path is URL-encoded to owner%2Frepo.
        assert (
            request.url.raw_path.decode().split("?")[0]
            == "/api/v4/projects/group%2Fsub%2Frepo/merge_requests"
        )
        if request.url.params.get("page") == "1":
            return httpx.Response(
                200,
                json=[
                    {
                        "iid": 12,
                        "id": 495563942,
                        "state": "merged",
                        "created_at": "2026-06-13T05:24:57.317Z",
                        "merged_at": "2026-06-13T06:07:14.665Z",
                        "closed_at": None,
                        "author": {"username": "alice"},
                    },
                    {
                        "iid": 13,
                        "id": 495563943,
                        "state": "opened",
                        "created_at": "2026-06-13T05:24:57.317Z",
                        "merged_at": None,
                        "closed_at": None,
                        "author": {"username": "bob"},
                    },
                ],
            )
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="t")
    prs = list(client.list_pull_requests("group/sub", "repo"))
    # iid is the number, NOT the global id.
    assert [p.number for p in prs] == [12, 13]
    # merged -> closed, merged_at present and normalized to second-precision Z.
    assert prs[0].state == "closed"
    assert prs[0].merged_at == "2026-06-13T06:07:14Z"
    assert prs[0].created_at == "2026-06-13T05:24:57Z"
    assert prs[0].author == "alice"
    # opened -> open.
    assert prs[1].state == "open"
    assert prs[1].merged_at is None
    # raw retained, including the ignored global id.
    assert prs[0].raw["id"] == 495563942


def test_closed_without_merge_has_null_merged_at() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "1":
            return httpx.Response(
                200,
                json=[
                    {
                        "iid": 20,
                        "id": 1,
                        "state": "closed",
                        "created_at": "2026-06-13T05:24:57.317Z",
                        "merged_at": None,
                        "closed_at": "2026-06-14T09:00:00.000Z",
                        "author": {"username": "carol"},
                    }
                ],
            )
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="t")
    [pr] = list(client.list_pull_requests("o", "r"))
    assert pr.state == "closed"
    assert pr.merged_at is None
    assert pr.closed_at == "2026-06-14T09:00:00Z"


def test_merged_mr_closed_at_falls_back_to_merged_at() -> None:
    # GitLab leaves closed_at null on a merged MR, but base.py's contract says
    # closed_at is non-null for any closed PR — a merged MR is closed at merge.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "1":
            return httpx.Response(
                200,
                json=[
                    {
                        "iid": 30,
                        "id": 2,
                        "state": "merged",
                        "created_at": "2026-06-13T05:24:57.317Z",
                        "merged_at": "2026-06-13T06:07:14.665Z",
                        "closed_at": None,
                        "author": {"username": "alice"},
                    }
                ],
            )
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="t")
    [pr] = list(client.list_pull_requests("o", "r"))
    assert pr.state == "closed"
    assert pr.merged_at == "2026-06-13T06:07:14Z"
    assert pr.closed_at == "2026-06-13T06:07:14Z"


def test_closed_unmerged_keeps_own_closed_at() -> None:
    # A closed-without-merge MR keeps its own closed_at, not a merge fallback.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "1":
            return httpx.Response(
                200,
                json=[
                    {
                        "iid": 31,
                        "id": 3,
                        "state": "closed",
                        "created_at": "2026-06-13T05:24:57.317Z",
                        "merged_at": None,
                        "closed_at": "2026-06-14T09:00:00.000Z",
                        "author": {"username": "bob"},
                    }
                ],
            )
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="t")
    [pr] = list(client.list_pull_requests("o", "r"))
    assert pr.merged_at is None
    assert pr.closed_at == "2026-06-14T09:00:00Z"


def test_project_path_is_url_encoded() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["raw_path"] = request.url.raw_path.decode()
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="t")
    list(client.list_pull_requests("owner", "repo"))
    assert "/api/v4/projects/owner%2Frepo/merge_requests" in seen["raw_path"]


def test_notes_normalize() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert (
            request.url.raw_path.decode().split("?")[0]
            == "/api/v4/projects/o%2Fr/merge_requests/5/notes"
        )
        if request.url.params.get("page") == "1":
            return httpx.Response(
                200,
                json=[
                    {
                        "created_at": "2026-06-13T05:24:57.317Z",
                        "author": {"username": "dave"},
                        "body": "looks good",
                        "system": False,
                    },
                    {
                        "created_at": "2026-06-13T05:25:00.000Z",
                        "author": {"username": "gitlab-bot"},
                        "body": "approved this merge request",
                        "system": True,
                    },
                ],
            )
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="t")
    comments = list(client.list_issue_comments("o", "r", 5))
    # System notes are kept (the first-response analysis filters by identity).
    assert [c.author for c in comments] == ["dave", "gitlab-bot"]
    assert comments[0].created_at == "2026-06-13T05:24:57Z"
    assert comments[0].body == "looks good"


def test_resource_state_events_close_actor_mapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert (
            request.url.raw_path.decode().split("?")[0]
            == "/api/v4/projects/o%2Fr/merge_requests/7/resource_state_events"
        )
        if request.url.params.get("page") == "1":
            return httpx.Response(
                200,
                json=[
                    {
                        "state": "merged",
                        "user": {"username": "merger"},
                        "created_at": "2026-06-13T05:24:57.317Z",
                    },
                    {
                        "state": "closed",
                        "user": {"username": "maintainer"},
                        "created_at": "2026-06-13T05:25:57.317Z",
                    },
                ],
            )
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="t")
    events = list(client.list_issue_events("o", "r", 7))
    closed = [e for e in events if e.event == "closed"]
    assert len(closed) == 1
    assert closed[0].actor == "maintainer"


def test_resource_state_events_404_degrades_to_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="404 Not Found")

    client, _ = _client(httpx.MockTransport(handler), token="t")
    # Old self-hosted GitLab lacks the endpoint: degrade, don't crash.
    assert list(client.list_issue_events("o", "r", 7)) == []


def test_group_projects_normalize() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v4/groups/gitlab-org/projects"
        page = request.url.params.get("page")
        if page == "1":
            return httpx.Response(
                200,
                json=[
                    {
                        "path": "gitlab",
                        "namespace": {"full_path": "gitlab-org"},
                        "path_with_namespace": "gitlab-org/gitlab",
                    }
                ],
            )
        if page == "2":
            return httpx.Response(
                200,
                json=[
                    {
                        "path": "gitlab-runner",
                        "path_with_namespace": "gitlab-org/gitlab-runner",
                    }
                ],
            )
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="t")
    repos = list(client.list_org_repos("gitlab-org"))
    assert [(r.owner, r.name) for r in repos] == [
        ("gitlab-org", "gitlab"),
        ("gitlab-org", "gitlab-runner"),
    ]


def test_commits_normalize_no_login() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert (
            request.url.raw_path.decode().split("?")[0]
            == "/api/v4/projects/o%2Fr/repository/commits"
        )
        # Branch param is ref_name, since is forwarded.
        assert request.url.params.get("ref_name") == "main"
        assert request.url.params.get("since") == "2026-01-01T00:00:00Z"
        if request.url.params.get("page") == "1":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "abc123",
                        "message": "fix things\n\nTime: 1h",
                        "author_name": "Olivia Pool",
                        "authored_date": "2026-06-13T03:46:44.000Z",
                    }
                ],
            )
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="t")
    commits = list(
        client.list_commits("o", "r", since="2026-01-01T00:00:00Z", sha="main")
    )
    [c] = commits
    assert c.sha == "abc123"
    assert c.author is None
    assert c.author_name == "Olivia Pool"
    assert c.message.startswith("fix things")
    assert c.author_date == "2026-06-13T03:46:44Z"


def test_auth_header_is_private_token() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["token"] = request.headers.get("private-token")
        return _empty_page()

    client, _ = _client(httpx.MockTransport(handler), token="secret123")
    list(client.list_pull_requests("o", "r"))
    assert seen["token"] == "secret123"


def test_unauthenticated_warns_once() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _empty_page()

    warn = io.StringIO()
    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = GitLabClient(
        token=None, http_client=http, warn_stream=warn, sleep_fn=lambda s: None
    )
    list(client.list_pull_requests("o", "r"))
    list(client.list_pull_requests("o", "r"))
    assert warn.getvalue().count("GITLAB_TOKEN is not set") == 1


def test_rate_limit_429_retry_after() -> None:
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(429, json={}, headers={"retry-after": "3"})
        if request.url.params.get("page") == "1":
            return httpx.Response(
                200,
                json=[
                    {
                        "iid": 9,
                        "id": 1,
                        "state": "opened",
                        "created_at": "2026-01-01T00:00:00.000Z",
                        "merged_at": None,
                        "closed_at": None,
                        "author": {"username": "x"},
                    }
                ],
            )
        return _empty_page()

    client, sleeps = _client(httpx.MockTransport(handler), token="t")
    prs = list(client.list_pull_requests("o", "r"))
    assert [p.number for p in prs] == [9]
    assert sleeps == [3.0]


def test_non_rate_limit_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    client, _ = _client(httpx.MockTransport(handler), token="t")
    with pytest.raises(GitLabError):
        list(client.list_pull_requests("o", "r"))


def test_base_url_default_is_gitlab_com() -> None:
    client = GitLabClient(token="t")
    assert client._api_url == "https://gitlab.com/api/v4"
    client.close()
