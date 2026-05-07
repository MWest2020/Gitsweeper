from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from gitsweeper.capabilities import effort_allocation, pr_throughput
from gitsweeper.lib import storage


class FakeFetchClient:
    def __init__(self, prs: list[dict]) -> None:
        self._prs = prs

    def list_pull_requests(self, owner: str, repo: str, state: str = "all") -> Iterator[dict]:
        yield from self._prs


def _pr(
    number: int,
    *,
    author: str,
    created: str = "2026-01-05T08:00:00Z",
    merged: str | None = None,
    closed: str | None = None,
) -> dict:
    return {
        "number": number,
        "state": "closed" if (merged or closed) else "open",
        "created_at": created,
        "merged_at": merged,
        "closed_at": merged or closed,
        "user": {"login": author},
    }


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = storage.connect(tmp_path / "gs.sqlite")
    storage.init_schema(c)
    return c


def _seed(conn: sqlite3.Connection, owner: str, name: str, prs: list[dict]) -> int:
    return pr_throughput.fetch_and_persist(
        conn, FakeFetchClient(prs=prs), owner, name
    ).repo_id


def _row_by_author(rows: list[list], author: str) -> list:
    """Find the row whose author column equals `author` (default layout
    has repo at index 0, author at 1)."""
    matches = [r for r in rows if r[1] == author]
    assert len(matches) == 1, f"expected one row for {author!r}, got {len(matches)}"
    return matches[0]


def test_one_row_per_repo_author(conn: sqlite3.Connection) -> None:
    _seed(conn, "o", "r", [
        _pr(1, author="alice", merged="2026-01-06T08:00:00Z"),
        _pr(2, author="alice", merged="2026-01-07T08:00:00Z"),
        _pr(3, author="bob", merged="2026-01-06T08:00:00Z"),
    ])
    result = effort_allocation.compute_effort_allocation(conn)
    assert result.metadata["row_count"] == 2
    assert sorted(r[1] for r in result.rows) == ["alice", "bob"]
    alice = _row_by_author(result.rows, "alice")
    assert alice[2] == 2  # submissions
    assert alice[3] == 2  # merged
    assert alice[4] == 1.0  # merged_rate (2 merged / 2 effective)


def test_self_pulled_uses_close_actor(conn: sqlite3.Connection) -> None:
    repo_id = _seed(conn, "o", "r", [
        _pr(1, author="alice", closed="2026-01-06T08:00:00Z"),  # closed-unmerged
        _pr(2, author="alice", merged="2026-01-06T08:00:00Z"),
    ])
    pr_rows = storage.list_pull_requests(conn, repo_id)
    closed_pr = next(r for r in pr_rows if r["number"] == 1)
    storage.upsert_close_actor(conn, int(closed_pr["id"]), "alice")  # self-pulled

    result = effort_allocation.compute_effort_allocation(conn)
    alice = _row_by_author(result.rows, "alice")
    # columns: repo, author, submissions, merged, merged_rate,
    #          self_pulled, closed_by_maintainer, closed_unenriched, still_open
    assert alice[5] == 1   # self_pulled
    assert alice[6] == 0   # closed_by_maintainer
    assert alice[7] == 0   # closed_unenriched
    assert alice[4] == 1.0  # 1 merged / (1 merged + 0 maintainer-closed)


def test_maintainer_closed_uses_close_actor(conn: sqlite3.Connection) -> None:
    repo_id = _seed(conn, "o", "r", [
        _pr(1, author="alice", closed="2026-01-06T08:00:00Z"),
    ])
    pr_id = storage.list_pull_requests(conn, repo_id)[0]["id"]
    storage.upsert_close_actor(conn, int(pr_id), "BOT_MAINTAINER")

    result = effort_allocation.compute_effort_allocation(conn)
    alice = _row_by_author(result.rows, "alice")
    assert alice[6] == 1   # closed_by_maintainer
    assert alice[5] == 0   # self_pulled
    assert alice[4] == 0.0  # 0 merged / (0 + 1 maintainer-closed) = 0/1


def test_merged_rate_zero_when_only_maintainer_close(conn: sqlite3.Connection) -> None:
    repo_id = _seed(conn, "o", "r", [
        _pr(1, author="alice", closed="2026-01-06T08:00:00Z"),
    ])
    pr_id = storage.list_pull_requests(conn, repo_id)[0]["id"]
    storage.upsert_close_actor(conn, int(pr_id), "BOT_MAINTAINER")
    result = effort_allocation.compute_effort_allocation(conn)
    alice = _row_by_author(result.rows, "alice")
    assert alice[4] == 0.0


def test_closed_unenriched_is_separate_bucket(conn: sqlite3.Connection) -> None:
    _seed(conn, "o", "r", [
        _pr(1, author="alice", closed="2026-01-06T08:00:00Z"),  # never enriched
    ])
    result = effort_allocation.compute_effort_allocation(conn)
    alice = _row_by_author(result.rows, "alice")
    assert alice[7] == 1   # closed_unenriched
    assert alice[5] == 0
    assert alice[6] == 0
    assert alice[4] is None  # denom = merged 0 + maintainer 0 = 0 → None
    assert result.metadata["closed_unenriched_total"] == 1


def test_merged_rate_excludes_self_pulled_from_denominator(conn: sqlite3.Connection) -> None:
    repo_id = _seed(conn, "o", "r", [
        _pr(1, author="alice", merged="2026-01-06T08:00:00Z"),
        _pr(2, author="alice", merged="2026-01-06T08:00:00Z"),
        _pr(3, author="alice", merged="2026-01-06T08:00:00Z"),
        _pr(4, author="alice", merged="2026-01-06T08:00:00Z"),
        _pr(5, author="alice", merged="2026-01-06T08:00:00Z"),
        _pr(6, author="alice", closed="2026-01-06T08:00:00Z"),
        _pr(7, author="alice", closed="2026-01-06T08:00:00Z"),
        _pr(8, author="alice", closed="2026-01-06T08:00:00Z"),
    ])
    # Self-pull all closed PRs
    for r in storage.list_pull_requests(conn, repo_id):
        if r["merged_at"] is None and r["closed_at"]:
            storage.upsert_close_actor(conn, int(r["id"]), "alice")

    result = effort_allocation.compute_effort_allocation(conn)
    alice = _row_by_author(result.rows, "alice")
    assert alice[2] == 8   # submissions
    assert alice[3] == 5   # merged
    assert alice[5] == 3   # self_pulled
    assert alice[4] == 1.0  # 5/(5+0) — self-pull not in denom


def test_by_period_adds_period_column(conn: sqlite3.Connection) -> None:
    _seed(conn, "o", "r", [
        _pr(1, author="alice", created="2026-01-05T08:00:00Z",
            merged="2026-01-06T08:00:00Z"),  # 2026-W02
        _pr(2, author="alice", created="2026-01-12T08:00:00Z",
            merged="2026-01-13T08:00:00Z"),  # 2026-W03
    ])
    result = effort_allocation.compute_effort_allocation(conn, by_period=True)
    assert result.columns[0] == "period"
    periods = sorted({r[0] for r in result.rows})
    assert periods == ["2026-W02", "2026-W03"]


def test_repos_filter(conn: sqlite3.Connection) -> None:
    _seed(conn, "ConductionNL", "openregister", [_pr(1, author="alice", merged="2026-01-06T08:00:00Z")])
    _seed(conn, "ConductionNL", "opencatalogi", [_pr(1, author="alice", merged="2026-01-06T08:00:00Z")])
    result = effort_allocation.compute_effort_allocation(
        conn, repos=[("ConductionNL", "openregister")]
    )
    assert {r[0] for r in result.rows} == {"ConductionNL/openregister"}


def test_since_filter(conn: sqlite3.Connection) -> None:
    _seed(conn, "o", "r", [
        _pr(1, author="alice", created="2025-12-31T08:00:00Z",
            merged="2026-01-01T08:00:00Z"),
        _pr(2, author="alice", created="2026-02-01T08:00:00Z",
            merged="2026-02-02T08:00:00Z"),
    ])
    result = effort_allocation.compute_effort_allocation(
        conn, since="2026-01-15T00:00:00Z"
    )
    alice = _row_by_author(result.rows, "alice")
    assert alice[2] == 1  # only PR #2 in the window
