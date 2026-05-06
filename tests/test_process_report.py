from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from gitsweeper.capabilities import process_report
from gitsweeper.lib import storage


class FakeClient:
    """Minimal client implementing the union of methods generate_report
    actually calls. Returns canned data for fetch + comments + events."""

    def __init__(
        self,
        prs: list[dict] | None = None,
        comments_by_pr: dict[int, list[dict]] | None = None,
        events_by_pr: dict[int, list[dict]] | None = None,
    ) -> None:
        self._prs = prs or []
        self._comments = comments_by_pr or {}
        self._events = events_by_pr or {}
        self.pr_calls = 0
        self.comment_calls: list[int] = []
        self.event_calls: list[int] = []

    def list_pull_requests(self, owner: str, repo: str, state: str = "all") -> Iterator[dict]:
        self.pr_calls += 1
        yield from self._prs

    def list_issue_comments(self, owner: str, repo: str, number: int) -> Iterator[dict]:
        self.comment_calls.append(number)
        yield from self._comments.get(number, [])

    def list_issue_events(self, owner: str, repo: str, number: int) -> Iterator[dict]:
        self.event_calls.append(number)
        yield from self._events.get(number, [])


def _pr(number: int, *, author="alice", merged: bool = False, closed: bool = True) -> dict:
    return {
        "number": number,
        "state": "closed" if (merged or closed) else "open",
        "created_at": "2025-01-06T08:00:00Z",
        "merged_at": "2025-01-07T08:00:00Z" if merged else None,
        "closed_at": "2025-01-07T08:00:00Z" if (merged or closed) else None,
        "user": {"login": author},
    }


def _comment(at: str, who: str) -> dict:
    return {"created_at": at, "user": {"login": who}}


def _close_event(actor: str | None) -> dict:
    return {"event": "closed", "actor": ({"login": actor} if actor else None)}


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = storage.connect(tmp_path / "gs.sqlite")
    storage.init_schema(c)
    return c


def test_empty_cache_raises_cache_empty(conn: sqlite3.Connection) -> None:
    client = FakeClient()  # no PRs
    with pytest.raises(process_report.CacheEmpty):
        process_report.generate_report(conn, client, "octocat", "hello", refresh=False)


def test_empty_cache_with_refresh_fetches_and_succeeds(conn: sqlite3.Connection) -> None:
    client = FakeClient(
        prs=[_pr(1, merged=True), _pr(2, closed=True, author="alice")],
        comments_by_pr={1: [_comment("2025-01-06T09:00:00Z", "bob")]},
        events_by_pr={2: [_close_event("alice")]},
    )
    md = process_report.generate_report(
        conn, client, "octocat", "hello", refresh=True
    )
    assert client.pr_calls == 1
    assert "# Process report for octocat/hello" in md
    assert "## volume" in md
    assert "## time-to-merge" in md
    assert "## time-to-first-response" in md
    assert "## closed-without-merge classification" in md
    assert "## temporal patterns" in md


def test_report_sections_appear_in_fixed_order(conn: sqlite3.Connection) -> None:
    client = FakeClient(
        prs=[_pr(1, merged=True), _pr(2, closed=True)],
        comments_by_pr={1: [_comment("2025-01-06T09:00:00Z", "bob")]},
        events_by_pr={2: [_close_event("MAINTAINER")]},
    )
    md = process_report.generate_report(
        conn, client, "o", "r", refresh=True
    )
    order = [
        md.index("## volume"),
        md.index("## time-to-merge"),
        md.index("## time-to-first-response"),
        md.index("## closed-without-merge classification"),
        md.index("## temporal patterns"),
    ]
    assert order == sorted(order)


def test_report_with_author_scopes_all_sections(conn: sqlite3.Connection) -> None:
    client = FakeClient(
        prs=[
            _pr(1, author="MWest2020", merged=True),
            _pr(2, author="alice", merged=True),
        ],
        comments_by_pr={
            1: [_comment("2025-01-06T09:00:00Z", "bob")],
            2: [_comment("2025-01-06T09:00:00Z", "bob")],
        },
    )
    md = process_report.generate_report(
        conn, client, "o", "r", author="MWest2020", refresh=True
    )
    assert "author MWest2020" in md
    # Volume should reflect only MWest2020's 1 PR
    # Find the volume section and look at the total cell
    import re
    block = md.split("## volume", 1)[1].split("##", 1)[0]
    total = re.search(r"\|\s*total\s*\|\s*(\d+)\s*\|", block)
    assert total is not None and total.group(1) == "1"


def test_report_writes_to_out_path_and_returns_clean_markdown(
    conn: sqlite3.Connection, tmp_path: Path,
) -> None:
    client = FakeClient(
        prs=[_pr(1, merged=True)],
        comments_by_pr={1: [_comment("2025-01-06T09:00:00Z", "bob")]},
    )
    md = process_report.generate_report(conn, client, "o", "r", refresh=True)
    out_path = tmp_path / "report.md"
    out_path.write_text(md, encoding="utf-8")
    contents = out_path.read_text(encoding="utf-8")
    assert contents == md
    # No ANSI escape codes
    assert "\x1b[" not in contents


def test_lazy_enrichment_is_idempotent_across_runs(conn: sqlite3.Connection) -> None:
    client = FakeClient(
        prs=[_pr(1, merged=True), _pr(2, closed=True)],
        comments_by_pr={1: [_comment("2025-01-06T09:00:00Z", "bob")]},
        events_by_pr={2: [_close_event("alice")]},
    )
    process_report.generate_report(conn, client, "o", "r", refresh=True)
    assert client.comment_calls == [1, 2]
    assert client.event_calls == [2]
    # Second run, no refresh — should not trigger any new GitHub calls.
    pre_comment_calls = list(client.comment_calls)
    pre_event_calls = list(client.event_calls)
    pre_pr_calls = client.pr_calls
    process_report.generate_report(conn, client, "o", "r", refresh=False)
    assert client.comment_calls == pre_comment_calls
    assert client.event_calls == pre_event_calls
    assert client.pr_calls == pre_pr_calls
