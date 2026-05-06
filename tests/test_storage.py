from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from gitsweeper.lib import storage


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = storage.connect(tmp_path / "gs.sqlite")
    storage.init_schema(c)
    return c


def _pr(
    number: int,
    *,
    merged_at: str | None = None,
    closed_at: str | None = None,
    author: str = "alice",
) -> dict:
    return {
        "number": number,
        "state": "closed" if closed_at or merged_at else "open",
        "created_at": "2025-01-01T00:00:00Z",
        "merged_at": merged_at,
        "closed_at": closed_at,
        "user": {"login": author},
        "title": f"PR #{number}",
    }


def test_init_schema_is_idempotent(conn: sqlite3.Connection) -> None:
    storage.init_schema(conn)
    storage.init_schema(conn)
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "repositories",
        "pull_requests",
        "pr_first_responses",
        "pr_close_actors",
    } <= tables


def test_get_or_create_repository_returns_same_id(conn: sqlite3.Connection) -> None:
    a = storage.get_or_create_repository(conn, "nextcloud", "app-certificate-requests")
    b = storage.get_or_create_repository(conn, "nextcloud", "app-certificate-requests")
    assert a == b


def test_get_or_create_repository_distinguishes_namespaces(conn: sqlite3.Connection) -> None:
    a = storage.get_or_create_repository(conn, "octocat", "hello", owner_namespace=None)
    b = storage.get_or_create_repository(conn, "octocat", "hello", owner_namespace="tenant-1")
    assert a != b


def test_upsert_pull_requests_idempotent_and_roundtrip(conn: sqlite3.Connection) -> None:
    repo_id = storage.get_or_create_repository(conn, "o", "r")
    prs = [
        _pr(1, merged_at="2025-02-01T10:00:00Z", closed_at="2025-02-01T10:00:00Z"),
        _pr(2),
    ]
    assert storage.upsert_pull_requests(conn, repo_id, prs) == 2
    assert storage.upsert_pull_requests(conn, repo_id, prs) == 2  # second time: update path
    rows = storage.list_pull_requests(conn, repo_id)
    assert [r["number"] for r in rows] == [1, 2]
    assert rows[0]["state"] == "merged"
    assert rows[1]["state"] == "open"
    assert json.loads(rows[0]["raw_payload"])["title"] == "PR #1"


def test_list_pull_requests_filters_by_merged_since(conn: sqlite3.Connection) -> None:
    repo_id = storage.get_or_create_repository(conn, "o", "r")
    storage.upsert_pull_requests(
        conn,
        repo_id,
        [
            _pr(1, merged_at="2024-06-01T00:00:00Z"),  # before
            _pr(2, merged_at="2025-01-01T00:00:00Z"),  # boundary, included
            _pr(3, merged_at="2025-06-01T00:00:00Z"),  # after
            _pr(4),                                    # open, excluded
        ],
    )
    rows = storage.list_pull_requests(conn, repo_id, merged_since="2025-01-01T00:00:00Z")
    assert [r["number"] for r in rows] == [2, 3]


def test_first_response_upsert_and_join(conn: sqlite3.Connection) -> None:
    repo_id = storage.get_or_create_repository(conn, "o", "r")
    storage.upsert_pull_requests(
        conn,
        repo_id,
        [_pr(1, merged_at="2025-02-01T10:00:00Z"), _pr(2)],
    )
    pr_rows = storage.list_pull_requests(conn, repo_id)
    pr1_id = next(r["id"] for r in pr_rows if r["number"] == 1)

    storage.upsert_first_response(conn, pr1_id, "2025-02-01T05:00:00Z", "bob")
    storage.upsert_first_response(conn, pr1_id, "2025-02-01T04:00:00Z", "carol")  # update path

    joined = storage.list_first_responses(conn, repo_id)
    by_pr = {r["pr_id"]: r for r in joined}
    assert by_pr[pr1_id]["responder"] == "carol"
    assert by_pr[pr1_id]["first_response_at"] == "2025-02-01T04:00:00Z"
    pr2_id = next(r["id"] for r in pr_rows if r["number"] == 2)
    assert by_pr[pr2_id]["responder"] is None  # no first-response row yet


def test_list_pull_requests_author_filter_is_case_insensitive(conn: sqlite3.Connection) -> None:
    repo_id = storage.get_or_create_repository(conn, "o", "r")
    storage.upsert_pull_requests(
        conn,
        repo_id,
        [
            _pr(1, author="MWest2020"),
            _pr(2, author="alice"),
            _pr(3, author="mwest2020"),
        ],
    )
    rows = storage.list_pull_requests(conn, repo_id, author="mwest2020")
    assert sorted(r["number"] for r in rows) == [1, 3]


def test_list_pull_requests_author_combined_with_merged_since(conn: sqlite3.Connection) -> None:
    repo_id = storage.get_or_create_repository(conn, "o", "r")
    storage.upsert_pull_requests(
        conn,
        repo_id,
        [
            _pr(1, author="MWest2020", merged_at="2024-06-01T00:00:00Z"),
            _pr(2, author="MWest2020", merged_at="2025-06-01T00:00:00Z"),
            _pr(3, author="alice", merged_at="2025-06-01T00:00:00Z"),
        ],
    )
    rows = storage.list_pull_requests(
        conn, repo_id, merged_since="2025-01-01T00:00:00Z", author="MWest2020"
    )
    assert [r["number"] for r in rows] == [2]


def test_list_pull_requests_unknown_author_returns_empty(conn: sqlite3.Connection) -> None:
    repo_id = storage.get_or_create_repository(conn, "o", "r")
    storage.upsert_pull_requests(conn, repo_id, [_pr(1, author="MWest2020")])
    assert storage.list_pull_requests(conn, repo_id, author="ghost") == []


def test_close_actor_upsert_idempotent_and_filters_by_author(conn: sqlite3.Connection) -> None:
    repo_id = storage.get_or_create_repository(conn, "o", "r")
    storage.upsert_pull_requests(
        conn,
        repo_id,
        [
            _pr(1, author="MWest2020", closed_at="2025-02-01T00:00:00Z"),  # closed-unmerged
            _pr(2, author="MWest2020", merged_at="2025-02-01T00:00:00Z"),  # merged: excluded
            _pr(3, author="alice", closed_at="2025-02-01T00:00:00Z"),       # closed-unmerged, other author
        ],
    )
    pr_rows = storage.list_pull_requests(conn, repo_id)
    by_num = {r["number"]: r for r in pr_rows}
    storage.upsert_close_actor(conn, by_num[1]["id"], "MWest2020")
    storage.upsert_close_actor(conn, by_num[1]["id"], "tobiasKaminsky")  # update path

    rows = storage.list_close_actors(conn, repo_id)
    assert sorted(r["number"] for r in rows) == [1, 3]
    assert next(r for r in rows if r["number"] == 1)["close_actor"] == "tobiasKaminsky"
    # PR 3 has no actor row yet
    assert next(r for r in rows if r["number"] == 3)["close_actor"] is None

    only_mark = storage.list_close_actors(conn, repo_id, author="MWest2020")
    assert [r["number"] for r in only_mark] == [1]
