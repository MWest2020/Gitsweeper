"""Cross-forge provider contract suite (the suite deferred by forge-abstraction).

The same invariants run against every concrete provider via a per-forge fake
httpx transport. A future provider (e.g. GitLab) joins simply by adding a
`_Forge` fixture entry: a builder that returns a client wired to a transport
serving that forge's native shapes for the four scenarios below.

Invariants asserted:
  - merged PR            => non-null `merged_at`
  - closed-without-merge => null `merged_at` + non-null `closed_at`
  - `raw` is retained on every normalized record
  - pagination advances across multiple pages to completion
  - timestamps are normalized to UTC with a trailing `Z`
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import pytest

from gitsweeper.lib.forge.base import ForgeProvider
from gitsweeper.lib.forge.forgejo import ForgejoClient
from gitsweeper.lib.forge.github import GitHubClient

# --- GitHub fake transport -------------------------------------------------


def _github_pulls_handler(request: httpx.Request) -> httpx.Response:
    # Two-page pagination via the Link header; merged on p1, closed-unmerged p2.
    page = request.url.params.get("page")
    if page is None:
        return httpx.Response(
            200,
            json=[
                {
                    "number": 1,
                    "state": "closed",
                    "created_at": "2026-01-01T00:00:00Z",
                    "merged_at": "2026-01-02T12:00:00Z",
                    "closed_at": "2026-01-02T12:00:00Z",
                    "user": {"login": "alice"},
                }
            ],
            headers={
                "x-ratelimit-remaining": "100",
                "link": '<https://api.github.com/repos/o/r/pulls?page=2>; rel="next"',
            },
        )
    if page == "2":
        return httpx.Response(
            200,
            json=[
                {
                    "number": 2,
                    "state": "closed",
                    "created_at": "2026-01-01T00:00:00Z",
                    "merged_at": None,
                    "closed_at": "2026-01-03T08:00:00Z",
                    "user": {"login": "bob"},
                }
            ],
            headers={"x-ratelimit-remaining": "100"},
        )
    return httpx.Response(404, text=f"unexpected page {page}")


def _make_github() -> ForgeProvider:
    http = httpx.Client(transport=httpx.MockTransport(_github_pulls_handler))
    return GitHubClient(
        token="t",
        http_client=http,
        sleep_fn=lambda s: None,
        now_fn=lambda: 0.0,
        warn_stream=io.StringIO(),
    )


# --- Forgejo fake transport ------------------------------------------------


def _forgejo_pulls_handler(request: httpx.Request) -> httpx.Response:
    # page/limit pagination; advance until an empty page. Offset timestamps.
    page = request.url.params.get("page")
    if page == "1":
        return httpx.Response(
            200,
            json=[
                {
                    "number": 1,
                    "state": "closed",
                    "created_at": "2026-01-01T01:00:00+01:00",
                    "merged_at": "2026-01-02T13:00:00+01:00",
                    "closed_at": "2026-01-02T13:00:00+01:00",
                    "merged": True,
                    "user": {"login": "alice"},
                }
            ],
        )
    if page == "2":
        return httpx.Response(
            200,
            json=[
                {
                    "number": 2,
                    "state": "closed",
                    "created_at": "2026-01-01T01:00:00+01:00",
                    "merged_at": None,
                    "closed_at": "2026-01-03T09:00:00+01:00",
                    "merged": False,
                    "user": {"login": "bob"},
                }
            ],
        )
    return httpx.Response(200, json=[])


def _make_forgejo() -> ForgeProvider:
    http = httpx.Client(transport=httpx.MockTransport(_forgejo_pulls_handler))
    return ForgejoClient(
        token="t",
        http_client=http,
        sleep_fn=lambda s: None,
        warn_stream=io.StringIO(),
    )


@dataclass(frozen=True)
class _Forge:
    name: str
    make: Callable[[], ForgeProvider]


FORGES = [
    _Forge("github", _make_github),
    _Forge("forgejo", _make_forgejo),
]


@pytest.fixture(params=FORGES, ids=lambda f: f.name)
def provider(request: pytest.FixtureRequest) -> ForgeProvider:
    client = request.param.make()
    yield client
    client.close()


def test_pagination_advances_to_completion(provider: ForgeProvider) -> None:
    prs = list(provider.list_pull_requests("o", "r"))
    # Two PRs, one from each page — pagination ran to completion.
    assert [p.number for p in prs] == [1, 2]


def test_merged_pr_has_non_null_merged_at(provider: ForgeProvider) -> None:
    prs = {p.number: p for p in provider.list_pull_requests("o", "r")}
    assert prs[1].merged_at is not None


def test_closed_without_merge_has_null_merged_at_and_non_null_closed_at(
    provider: ForgeProvider,
) -> None:
    prs = {p.number: p for p in provider.list_pull_requests("o", "r")}
    assert prs[2].merged_at is None
    assert prs[2].closed_at is not None


def test_raw_is_retained(provider: ForgeProvider) -> None:
    for p in provider.list_pull_requests("o", "r"):
        assert isinstance(p.raw, dict)
        assert p.raw.get("number") == p.number


def test_timestamps_are_utc_z(provider: ForgeProvider) -> None:
    for p in provider.list_pull_requests("o", "r"):
        assert p.created_at.endswith("Z")
        for ts in (p.merged_at, p.closed_at):
            if ts is not None:
                assert ts.endswith("Z")
    # Both forges describe the same merge instant; normalization makes them equal.
    merged = {p.number: p.merged_at for p in provider.list_pull_requests("o", "r")}
    assert merged[1] == "2026-01-02T12:00:00Z"
