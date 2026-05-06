from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from gitsweeper.capabilities import pr_classification, pr_throughput
from gitsweeper.lib import storage


class FakeEventsClient:
    def __init__(self, events_by_pr: dict[int, list[dict]]) -> None:
        self._events = events_by_pr
        self.calls: list[int] = []

    # Required for fetch_and_persist
    def list_pull_requests(self, owner: str, repo: str, state: str = "all") -> Iterator[dict]:
        return iter([])

    def list_issue_events(self, owner: str, repo: str, number: int) -> Iterator[dict]:
        self.calls.append(number)
        yield from self._events.get(number, [])


def _close(actor: str | None = None) -> dict:
    return {"event": "closed", "actor": ({"login": actor} if actor else None)}


def _other(name: str = "labeled") -> dict:
    return {"event": name, "actor": {"login": "anyone"}}


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = storage.connect(tmp_path / "gs.sqlite")
    storage.init_schema(c)
    return c


def _seed_prs(conn: sqlite3.Connection, prs: list[dict]) -> int:
    repo_id = storage.get_or_create_repository(conn, "o", "r")
    storage.upsert_pull_requests(conn, repo_id, prs)
    return repo_id


def _pr(
    number: int,
    *,
    author: str = "alice",
    merged: bool = False,
    closed: bool = True,
) -> dict:
    return {
        "number": number,
        "state": "closed" if (merged or closed) else "open",
        "created_at": "2025-01-01T00:00:00Z",
        "merged_at": "2025-01-02T00:00:00Z" if merged else None,
        "closed_at": "2025-01-02T00:00:00Z" if (merged or closed) else None,
        "user": {"login": author},
    }


def test_enrichment_only_runs_for_closed_without_merge(conn: sqlite3.Connection) -> None:
    repo_id = _seed_prs(conn, [
        _pr(1, closed=True),
        _pr(2, merged=True),                      # merged: must be skipped
        _pr(3, closed=False),                     # open: must be skipped
    ])
    client = FakeEventsClient({1: [_close("alice")]})
    summary = pr_classification.enrich_close_actors(conn, client, repo_id, "o", "r")
    assert summary.fetched == 1
    assert summary.skipped_cached == 0
    assert client.calls == [1]


def test_enrichment_is_incremental(conn: sqlite3.Connection) -> None:
    repo_id = _seed_prs(conn, [_pr(1), _pr(2)])
    client = FakeEventsClient({1: [_close("alice")], 2: [_close("bob")]})
    pr_classification.enrich_close_actors(conn, client, repo_id, "o", "r")
    second = pr_classification.enrich_close_actors(conn, client, repo_id, "o", "r")
    assert second.fetched == 0
    assert second.skipped_cached == 2
    assert client.calls == [1, 2]  # not called again


def test_classification_uses_last_closed_event(conn: sqlite3.Connection) -> None:
    repo_id = _seed_prs(conn, [_pr(1, author="alice")])
    client = FakeEventsClient({
        # An earlier close, then a reopen-equivalent event, then the
        # actual final close — our classifier picks the last close.
        1: [_close("alice"), _other("reopened"), _close("bob")]
    })
    pr_classification.enrich_close_actors(conn, client, repo_id, "o", "r")
    result = pr_classification.compute_classification(conn, repo_id, "o", "r")
    by_cat = dict(result.rows)
    assert by_cat["maintainer_closed"] == 1
    assert by_cat["self_pulled"] == 0


def test_self_pulled_vs_maintainer_closed(conn: sqlite3.Connection) -> None:
    repo_id = _seed_prs(conn, [
        _pr(1, author="alice"),
        _pr(2, author="alice"),
        _pr(3, author="alice"),
    ])
    client = FakeEventsClient({
        1: [_close("alice")],          # self-pulled
        2: [_close("MAINTAINER_BOT")], # maintainer-closed
        3: [_other("labeled")],        # no close event → unknown
    })
    pr_classification.enrich_close_actors(conn, client, repo_id, "o", "r")
    result = pr_classification.compute_classification(conn, repo_id, "o", "r")
    by_cat = dict(result.rows)
    assert by_cat["self_pulled"] == 1
    assert by_cat["maintainer_closed"] == 1
    assert by_cat["unknown_actor"] == 1
    assert by_cat["pending_enrichment"] == 0


def test_pending_enrichment_is_reported_separately(conn: sqlite3.Connection) -> None:
    repo_id = _seed_prs(conn, [_pr(1, author="alice"), _pr(2, author="alice")])
    client = FakeEventsClient({1: [_close("alice")]})
    pr_classification.enrich_close_actors(conn, client, repo_id, "o", "r")
    # Wipe PR 2's enrichment row so it shows as pending.
    pr_rows = storage.list_pull_requests(conn, repo_id)
    pr2_id = next(r["id"] for r in pr_rows if r["number"] == 2)
    conn.execute("DELETE FROM pr_close_actors WHERE pr_id = ?", (pr2_id,))
    conn.commit()

    result = pr_classification.compute_classification(conn, repo_id, "o", "r")
    by_cat = dict(result.rows)
    assert by_cat["pending_enrichment"] == 1
    assert by_cat["self_pulled"] == 1


def test_classification_author_filter(conn: sqlite3.Connection) -> None:
    repo_id = _seed_prs(conn, [
        _pr(1, author="alice"),
        _pr(2, author="bob"),
    ])
    client = FakeEventsClient({1: [_close("alice")], 2: [_close("alice")]})
    pr_classification.enrich_close_actors(conn, client, repo_id, "o", "r")
    result = pr_classification.compute_classification(conn, repo_id, "o", "r", author="alice")
    by_cat = dict(result.rows)
    assert by_cat["self_pulled"] == 1     # only PR 1 (alice/alice)
    assert by_cat["maintainer_closed"] == 0
    assert result.metadata["author"] == "alice"


def test_pr_throughput_fetch_and_persist_compatible_with_classify_flow(
    conn: sqlite3.Connection,
) -> None:
    """Smoke test that storage rows produced by the existing fetch path
    are usable by classification (regression guard)."""
    from tests.test_pr_throughput import FakeClient as ThroughputFake

    pr1 = {
        "number": 1, "state": "closed",
        "created_at": "2025-01-01T00:00:00Z",
        "merged_at": None, "closed_at": "2025-01-02T00:00:00Z",
        "user": {"login": "alice"},
    }
    summary = pr_throughput.fetch_and_persist(
        conn, ThroughputFake(prs=[pr1]), "o", "r"
    )
    events_client = FakeEventsClient({1: [_close("alice")]})
    pr_classification.enrich_close_actors(
        conn, events_client, summary.repo_id, "o", "r"
    )
    result = pr_classification.compute_classification(
        conn, summary.repo_id, "o", "r"
    )
    by_cat = dict(result.rows)
    assert by_cat["self_pulled"] == 1
