"""Tests for the reconcile capability.

Pure unit tests on the classifier and aggregation helpers, plus
end-to-end tests that drive the reconcile function through
pytest-httpx mocks for both Billbird and GitHub. No threads, no
network — every httpx call is intercepted and matched.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from billbird_client import BillbirdClient

from gitsweeper.capabilities.commit_time_reconcile import (
    _aggregate_commits,
    _aggregate_logs,
    classify,
    reconcile,
)
from gitsweeper.lib.github_client import GitHubClient

# --- Classifier ----------------------------------------------------


@pytest.mark.parametrize(
    "commits,logs,want",
    [
        (0, 0, "aligned"),         # empty bucket — theoretical
        (60, 0, "commits_only"),
        (0, 60, "logs_only"),
        (60, 60, "aligned"),
        (60, 65, "aligned"),       # 5min drift, within 15min floor
        (60, 75, "aligned"),       # 15min drift, exactly at the floor
        (60, 90, "over_logged"),   # >15min drift
        (60, 30, "over_committed"),
        (600, 660, "aligned"),     # 10% of 600 = 60, drift 60, on the line
        (600, 670, "over_logged"), # 10% of 600 = 60, drift 70 > tolerance
        (10, 22, "aligned"),       # 12min drift on tiny commit, within floor
        (10, 25, "aligned"),       # 15min drift = floor → still aligned
        (10, 26, "over_logged"),   # 16min drift > floor
    ],
)
def test_classify(commits: int, logs: int, want: str) -> None:
    assert classify(commits, logs) == want


# --- Aggregation helpers -------------------------------------------


def _commit(
    sha: str,
    message: str,
    login: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Shape mirroring what GitHub's /commits endpoint returns."""
    return {
        "sha": sha,
        "author": {"login": login} if login else None,
        "commit": {
            "author": {"name": name or login or "unknown"},
            "message": message,
        },
    }


def test_aggregate_commits_groups_per_issue_and_author() -> None:
    commits = [
        _commit("a1", "fix\n\nCloses #5\nTime: 1h", login="alice"),
        _commit("a2", "more work on #5\n\nTime: 30m", login="alice"),
        _commit("a3", "refactor\n\nFixes #7\nTime: 45m", login="alice"),
        _commit("b1", "tidy\n\nCloses #5\nTime: 15m", login="bob"),
        _commit("c1", "no footer\n\nCloses #5"),
    ]
    buckets = _aggregate_commits(commits, "org/repo")
    keys = {(k.author, k.issue): v for k, v in buckets.items()}
    assert keys[("alice", 5)] == 90  # 60 + 30
    assert keys[("alice", 7)] == 45
    assert keys[("bob", 5)] == 15
    assert all(v > 0 for v in keys.values())


def test_aggregate_commits_unreferenced_goes_to_null_issue() -> None:
    commits = [_commit("x1", "no issue ref\n\nTime: 20m", login="alice")]
    buckets = _aggregate_commits(commits, "org/repo")
    [(k, v)] = buckets.items()
    assert k.issue is None
    assert k.author == "alice"
    assert v == 20


def test_aggregate_logs_skips_non_active() -> None:
    entries = [
        {"GitHubUsername": "alice", "IssueNumber": 5, "DurationMinutes": 60, "Status": "active"},
        {"GitHubUsername": "alice", "IssueNumber": 5, "DurationMinutes": 30, "Status": "superseded"},
        {"GitHubUsername": "alice", "IssueNumber": 5, "DurationMinutes": 20, "Status": "deleted"},
    ]
    buckets = _aggregate_logs(entries, "org/repo")
    [(_, total)] = buckets.items()
    assert total == 60


# --- End-to-end with pytest-httpx ----------------------------------


@pytest.fixture
def billbird_base() -> str:
    return "http://billbird.test"


def test_reconcile_end_to_end(httpx_mock, billbird_base: str) -> None:
    # GitHub commits page
    httpx_mock.add_response(
        url="https://api.github.com/repos/org/repo/commits?per_page=100",
        json=[
            _commit("c1", "fix #5\n\nTime: 1h", login="alice"),
            _commit("c2", "drive-by typo\n\nTime: 5m"),
        ],
    )
    # Billbird time-entries response
    httpx_mock.add_response(
        url=re.compile(rf"^{re.escape(billbird_base)}/api/v1/time-entries.*"),
        json=[
            {
                "GitHubUsername": "alice",
                "IssueNumber": 5,
                "DurationMinutes": 60,
                "Status": "active",
                "Repository": "org/repo",
            },
            {
                "GitHubUsername": "bob",
                "IssueNumber": 9,
                "DurationMinutes": 30,
                "Status": "active",
                "Repository": "org/repo",
            },
        ],
    )

    gh = GitHubClient(token="ghp_x")
    bb = BillbirdClient(billbird_base, "bb_test")
    try:
        result = reconcile(github=gh, billbird=bb, owner="org", name="repo")
    finally:
        bb.close()
        gh.close()

    by_key = {(r[1], r[2]): r for r in result.rows}

    alice_row = by_key[("alice", 5)]
    assert alice_row[3] == 60
    assert alice_row[4] == 60
    assert alice_row[5] == 0
    assert alice_row[6] == "aligned"

    bob_row = by_key[("bob", 9)]
    assert bob_row[3] == 0
    assert bob_row[4] == 30
    assert bob_row[6] == "logs_only"

    unknown_row = by_key[("unknown", None)]
    assert unknown_row[3] == 5
    assert unknown_row[4] == 0
    assert unknown_row[6] == "commits_only"


def test_reconcile_sorts_by_absolute_drift(httpx_mock, billbird_base: str) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/org/repo/commits?per_page=100",
        json=[
            _commit("a", "issue 1\n\nCloses #1\nTime: 60m", login="alice"),
            _commit("b", "issue 3\n\nCloses #3\nTime: 30m", login="alice"),
            _commit("c", "issue 2 untouched"),
        ],
    )
    httpx_mock.add_response(
        url=re.compile(rf"^{re.escape(billbird_base)}/api/v1/time-entries.*"),
        json=[
            {"GitHubUsername": "alice", "IssueNumber": 1, "DurationMinutes": 60, "Status": "active", "Repository": "org/repo"},
            {"GitHubUsername": "alice", "IssueNumber": 3, "DurationMinutes": 120, "Status": "active", "Repository": "org/repo"},
        ],
    )

    gh = GitHubClient(token="ghp_x")
    bb = BillbirdClient(billbird_base, "bb_test")
    try:
        result = reconcile(github=gh, billbird=bb, owner="org", name="repo")
    finally:
        bb.close()
        gh.close()

    issue_order = [r[2] for r in result.rows]
    # Drift descending by absolute value: issue 3 (drift +90) leads.
    assert issue_order[0] == 3
    assert 1 in issue_order


def test_reconcile_with_author_filter(httpx_mock, billbird_base: str) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/org/repo/commits?per_page=100",
        json=[
            _commit("a", "Closes #1\nTime: 60m", login="alice"),
            _commit("b", "Closes #2\nTime: 30m", login="bob"),
        ],
    )
    # Billbird query carries username=alice so the response is already filtered.
    httpx_mock.add_response(
        url=re.compile(rf"^{re.escape(billbird_base)}/api/v1/time-entries.*"),
        json=[
            {"GitHubUsername": "alice", "IssueNumber": 1, "DurationMinutes": 60, "Status": "active", "Repository": "org/repo"},
        ],
    )

    gh = GitHubClient(token="ghp_x")
    bb = BillbirdClient(billbird_base, "bb_test")
    try:
        result = reconcile(github=gh, billbird=bb, owner="org", name="repo", author="alice")
    finally:
        bb.close()
        gh.close()

    authors_in_result = {r[1] for r in result.rows}
    assert "alice" in authors_in_result
    assert "bob" not in authors_in_result
