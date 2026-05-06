from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest

from gitsweeper.capabilities import pr_throughput
from gitsweeper.lib import storage


class FakeClient:
    """Stand-in for GitHubClient. Returns canned data, records calls."""

    def __init__(
        self,
        prs: Iterable[dict] = (),
        comments_by_pr: dict[int, list[dict]] | None = None,
    ) -> None:
        self._prs = list(prs)
        self._comments = comments_by_pr or {}
        self.pr_calls = 0
        self.comment_calls: list[int] = []

    def list_pull_requests(self, owner: str, repo: str, state: str = "all") -> Iterator[dict]:
        self.pr_calls += 1
        yield from self._prs

    def list_issue_comments(self, owner: str, repo: str, number: int) -> Iterator[dict]:
        self.comment_calls.append(number)
        yield from self._comments.get(number, [])


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = storage.connect(tmp_path / "gs.sqlite")
    storage.init_schema(c)
    return c


def _pr(number: int, *, created: str, merged: str | None = None, author: str = "alice") -> dict:
    return {
        "number": number,
        "state": "closed" if merged else "open",
        "created_at": created,
        "merged_at": merged,
        "closed_at": merged,
        "user": {"login": author},
        "title": f"PR #{number}",
    }


def _comment(at: str, who: str) -> dict:
    return {"created_at": at, "user": {"login": who}, "body": "..."}


# ---- parse_since ----------------------------------------------------------

def test_parse_since_accepts_none() -> None:
    assert pr_throughput.parse_since(None) is None


def test_parse_since_accepts_iso_date() -> None:
    assert pr_throughput.parse_since("2025-01-15") == "2025-01-15T00:00:00Z"


def test_parse_since_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        pr_throughput.parse_since("yesterday")
    with pytest.raises(ValueError):
        pr_throughput.parse_since("2025-13-01")


# ---- throughput math ------------------------------------------------------

def test_throughput_excludes_open_and_unmerged_closed(conn: sqlite3.Connection) -> None:
    client = FakeClient(prs=[
        _pr(1, created="2025-01-01T00:00:00Z", merged="2025-01-02T00:00:00Z"),  # 1 day
        _pr(2, created="2025-01-01T00:00:00Z", merged="2025-01-08T00:00:00Z"),  # 7 days
        _pr(3, created="2025-01-01T00:00:00Z"),                                  # open
        _pr(4, created="2025-01-01T00:00:00Z"),                                  # closed unmerged below
    ])
    summary = pr_throughput.fetch_and_persist(conn, client, "o", "r")
    # Manually set #4 closed-without-merge
    conn.execute(
        "UPDATE pull_requests SET state='closed', closed_at=? WHERE number=4",
        ("2025-01-05T00:00:00Z",),
    )
    conn.commit()
    result = pr_throughput.compute_throughput(conn, summary.repo_id, "o", "r")
    by_metric = dict(result.rows)
    assert by_metric["count"] == 2
    assert by_metric["median"] == pytest.approx(4.0)
    assert by_metric["max"] == pytest.approx(7.0)


def test_throughput_empty_population_returns_zero_count(conn: sqlite3.Connection) -> None:
    client = FakeClient(prs=[_pr(1, created="2025-01-01T00:00:00Z")])  # not merged
    summary = pr_throughput.fetch_and_persist(conn, client, "o", "r")
    result = pr_throughput.compute_throughput(conn, summary.repo_id, "o", "r")
    by_metric = dict(result.rows)
    assert by_metric["count"] == 0
    assert by_metric["median"] is None
    assert by_metric["p95"] is None
    assert by_metric["max"] is None


def test_throughput_since_filter_excludes_earlier_merges(conn: sqlite3.Connection) -> None:
    client = FakeClient(prs=[
        _pr(1, created="2024-12-31T00:00:00Z", merged="2024-12-31T12:00:00Z"),  # before
        _pr(2, created="2024-12-31T00:00:00Z", merged="2025-01-01T00:00:00Z"),  # boundary, included
        _pr(3, created="2024-12-31T00:00:00Z", merged="2025-02-01T00:00:00Z"),  # after
    ])
    summary = pr_throughput.fetch_and_persist(conn, client, "o", "r")
    since = pr_throughput.parse_since("2025-01-01")
    result = pr_throughput.compute_throughput(conn, summary.repo_id, "o", "r", since=since)
    by_metric = dict(result.rows)
    assert by_metric["count"] == 2  # PRs 2 and 3, not 1


# ---- first response -------------------------------------------------------

def test_first_response_skips_self_authored_comments(conn: sqlite3.Connection) -> None:
    client = FakeClient(
        prs=[_pr(42, created="2025-01-01T00:00:00Z", merged="2025-01-10T00:00:00Z", author="alice")],
        comments_by_pr={
            42: [
                _comment("2025-01-01T01:00:00Z", "alice"),  # self, ignored
                _comment("2025-01-02T00:00:00Z", "bob"),    # winner
                _comment("2025-01-03T00:00:00Z", "carol"),
            ]
        },
    )
    summary = pr_throughput.fetch_and_persist(conn, client, "o", "r")
    result = pr_throughput.compute_first_response(conn, client, summary.repo_id, "o", "r")
    by_metric = dict(result.rows)
    assert by_metric["count"] == 1
    assert by_metric["median"] == pytest.approx(1.0)


def test_first_response_no_non_author_comment_is_excluded_and_counted(conn: sqlite3.Connection) -> None:
    client = FakeClient(
        prs=[
            _pr(1, created="2025-01-01T00:00:00Z", merged="2025-01-10T00:00:00Z", author="alice"),
            _pr(2, created="2025-01-01T00:00:00Z", merged="2025-01-20T00:00:00Z", author="alice"),
        ],
        comments_by_pr={
            1: [_comment("2025-01-02T00:00:00Z", "bob")],     # has response
            2: [_comment("2025-01-02T00:00:00Z", "alice")],   # only author, no response
        },
    )
    summary = pr_throughput.fetch_and_persist(conn, client, "o", "r")
    result = pr_throughput.compute_first_response(conn, client, summary.repo_id, "o", "r")
    by_metric = dict(result.rows)
    assert by_metric["count"] == 1
    assert result.metadata["no_response_yet"] == 1


def test_first_response_caches_after_first_compute(conn: sqlite3.Connection) -> None:
    client = FakeClient(
        prs=[_pr(1, created="2025-01-01T00:00:00Z", merged="2025-01-10T00:00:00Z")],
        comments_by_pr={1: [_comment("2025-01-02T00:00:00Z", "bob")]},
    )
    summary = pr_throughput.fetch_and_persist(conn, client, "o", "r")
    pr_throughput.compute_first_response(conn, client, summary.repo_id, "o", "r")
    pr_throughput.compute_first_response(conn, client, summary.repo_id, "o", "r")
    assert client.comment_calls == [1]  # only fetched once


# ---- structured output for renderer ---------------------------------------

def test_result_has_required_columns_and_metadata(conn: sqlite3.Connection) -> None:
    client = FakeClient(prs=[
        _pr(1, created="2025-01-01T00:00:00Z", merged="2025-01-02T00:00:00Z")
    ])
    summary = pr_throughput.fetch_and_persist(conn, client, "octocat", "hello")
    result = pr_throughput.compute_throughput(conn, summary.repo_id, "octocat", "hello")
    assert result.columns == ["metric", "value"]
    metric_names = [r[0] for r in result.rows]
    assert metric_names == ["count", "p25", "median", "p75", "p95", "max"]
    assert result.metadata["repo"] == "octocat/hello"
    assert "generated_at" in result.metadata


# ---- author filter --------------------------------------------------------

def test_throughput_author_filter_narrows_population(conn: sqlite3.Connection) -> None:
    client = FakeClient(prs=[
        _pr(1, created="2025-01-01T00:00:00Z", merged="2025-01-02T00:00:00Z", author="alice"),
        _pr(2, created="2025-01-01T00:00:00Z", merged="2025-01-04T00:00:00Z", author="bob"),
        _pr(3, created="2025-01-01T00:00:00Z", merged="2025-01-09T00:00:00Z", author="alice"),
    ])
    summary = pr_throughput.fetch_and_persist(conn, client, "o", "r")
    result = pr_throughput.compute_throughput(
        conn, summary.repo_id, "o", "r", author="alice"
    )
    by_metric = dict(result.rows)
    assert by_metric["count"] == 2  # PRs 1 and 3
    assert result.metadata["author"] == "alice"


def test_throughput_author_filter_is_case_insensitive(conn: sqlite3.Connection) -> None:
    client = FakeClient(prs=[
        _pr(1, created="2025-01-01T00:00:00Z", merged="2025-01-02T00:00:00Z", author="MWest2020"),
    ])
    summary = pr_throughput.fetch_and_persist(conn, client, "o", "r")
    result = pr_throughput.compute_throughput(
        conn, summary.repo_id, "o", "r", author="mwest2020"
    )
    by_metric = dict(result.rows)
    assert by_metric["count"] == 1


def test_throughput_author_with_no_match_is_empty_not_error(conn: sqlite3.Connection) -> None:
    client = FakeClient(prs=[
        _pr(1, created="2025-01-01T00:00:00Z", merged="2025-01-02T00:00:00Z", author="alice"),
    ])
    summary = pr_throughput.fetch_and_persist(conn, client, "o", "r")
    result = pr_throughput.compute_throughput(
        conn, summary.repo_id, "o", "r", author="ghost"
    )
    by_metric = dict(result.rows)
    assert by_metric["count"] == 0
    assert result.metadata["author"] == "ghost"


def test_temporal_patterns_dow_and_hour_buckets(conn: sqlite3.Connection) -> None:
    # Two PRs created Mon 2025-01-06 morning, one Fri 2025-01-10 evening.
    client = FakeClient(
        prs=[
            _pr(1, created="2025-01-06T08:00:00Z", merged="2025-01-07T10:00:00Z"),  # Mon 08
            _pr(2, created="2025-01-06T13:00:00Z", merged="2025-01-08T13:00:00Z"),  # Mon 13
            _pr(3, created="2025-01-10T20:00:00Z", merged="2025-01-13T09:00:00Z"),  # Fri 20
        ],
        comments_by_pr={
            1: [_comment("2025-01-06T09:00:00Z", "bob")],
            2: [_comment("2025-01-07T10:00:00Z", "bob")],
            3: [_comment("2025-01-13T09:00:00Z", "bob")],   # Mon 09 (response)
        },
    )
    summary = pr_throughput.fetch_and_persist(conn, client, "o", "r")
    pr_throughput.compute_first_response(conn, client, summary.repo_id, "o", "r")
    result = pr_throughput.compute_temporal_patterns(
        conn, summary.repo_id, "o", "r"
    )
    by_metric = dict(result.rows)
    assert by_metric["submissions_dow_Mon"] == 2
    assert by_metric["submissions_dow_Fri"] == 1
    assert by_metric["submissions_hour_08"] == 1
    assert by_metric["submissions_hour_13"] == 1
    assert by_metric["submissions_hour_20"] == 1
    assert by_metric["responses_dow_Mon"] == 2
    assert by_metric["responses_hour_09"] == 2
    # Median first-response when submitted on Friday: only PR3 = 2.54d
    assert by_metric["median_frt_days_when_submitted_Fri"] == pytest.approx(
        2.5416666666666665, rel=1e-3
    )
    # Days with no submissions report None as median
    assert by_metric["median_frt_days_when_submitted_Tue"] is None


def test_temporal_patterns_author_filter(conn: sqlite3.Connection) -> None:
    client = FakeClient(prs=[
        _pr(1, created="2025-01-06T08:00:00Z", author="alice"),
        _pr(2, created="2025-01-06T08:00:00Z", author="bob"),
    ])
    summary = pr_throughput.fetch_and_persist(conn, client, "o", "r")
    result = pr_throughput.compute_temporal_patterns(
        conn, summary.repo_id, "o", "r", author="alice"
    )
    by_metric = dict(result.rows)
    assert by_metric["submissions_dow_Mon"] == 1   # only alice's
    assert result.metadata["author"] == "alice"
    assert result.metadata["submissions_total"] == 1


def test_first_response_author_filter(conn: sqlite3.Connection) -> None:
    client = FakeClient(
        prs=[
            _pr(1, created="2025-01-01T00:00:00Z", merged="2025-01-05T00:00:00Z", author="alice"),
            _pr(2, created="2025-01-01T00:00:00Z", merged="2025-01-09T00:00:00Z", author="bob"),
        ],
        comments_by_pr={
            1: [_comment("2025-01-02T00:00:00Z", "carol")],
            2: [_comment("2025-01-03T00:00:00Z", "carol")],
        },
    )
    summary = pr_throughput.fetch_and_persist(conn, client, "o", "r")
    result = pr_throughput.compute_first_response(
        conn, client, summary.repo_id, "o", "r", author="alice"
    )
    by_metric = dict(result.rows)
    assert by_metric["count"] == 1
    assert result.metadata["author"] == "alice"
