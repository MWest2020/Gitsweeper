"""Pull-request classification.

Closed-without-merge pull requests come in two very different shapes:

- self-pulled: the submitter closed the PR themselves, usually because
  it was a duplicate or a quickly-superseded draft. These should not
  count against maintainer responsiveness.
- maintainer-closed: a maintainer closed the PR without merging,
  typically because it was out of scope or rejected. These represent
  a maintainer decision.

The GitHub `pulls` list endpoint omits `closed_by` for many pull
requests, so we look up the actor of the most recent `closed` event
via the issue-events endpoint and persist the answer.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from gitsweeper.lib import storage
from gitsweeper.lib.rendering import AnalysisResult


class _IssueEventClient(Protocol):
    def list_issue_events(
        self, owner: str, repo: str, issue_number: int
    ) -> Iterable[dict]: ...


@dataclass(frozen=True)
class EnrichmentSummary:
    fetched: int
    skipped_cached: int


def _last_close_actor(events: Iterable[dict]) -> str | None:
    last_actor: str | None = None
    for event in events:
        if event.get("event") == "closed":
            actor = event.get("actor") or {}
            login = actor.get("login")
            last_actor = login if login else last_actor
    return last_actor


def enrich_close_actors(
    conn: sqlite3.Connection,
    client: _IssueEventClient,
    repo_id: int,
    owner: str,
    name: str,
) -> EnrichmentSummary:
    """Fetch and persist the close-event actor for every closed-without-
    merge PR that has not been enriched yet. Returns counts for caller-
    side reporting."""
    rows = storage.list_close_actors(conn, repo_id)
    fetched = 0
    skipped = 0
    for row in rows:
        if row["ca_fetched_at"] is not None:
            skipped += 1
            continue
        actor = _last_close_actor(
            client.list_issue_events(owner, name, int(row["number"]))
        )
        storage.upsert_close_actor(conn, int(row["pr_id"]), actor)
        fetched += 1
    return EnrichmentSummary(fetched=fetched, skipped_cached=skipped)


def compute_classification(
    conn: sqlite3.Connection,
    repo_id: int,
    owner: str,
    name: str,
    *,
    author: str | None = None,
) -> AnalysisResult:
    """Categorise enriched closed-without-merge PRs and surface counts as
    a structured result. Pull requests with no enrichment row yet are
    reported as a separate `pending_enrichment` count rather than mixed
    in with the main categories."""
    rows = storage.list_close_actors(conn, repo_id, author=author)

    self_pulled = 0
    maintainer_closed = 0
    unknown = 0
    pending = 0
    for row in rows:
        if row["ca_fetched_at"] is None:
            pending += 1
            continue
        actor = row["close_actor"]
        if actor is None:
            unknown += 1
        elif actor.lower() == row["author"].lower():
            self_pulled += 1
        else:
            maintainer_closed += 1

    closed_unmerged_total = len(rows)

    title_scope = f" by {author}" if author else ""
    metadata: dict = {
        "repo": f"{owner}/{name}",
        "closed_unmerged_total": closed_unmerged_total,
        "pending_enrichment": pending,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if author:
        metadata["author"] = author

    return AnalysisResult(
        title=f"closed-without-merge classification for {owner}/{name}{title_scope}",
        columns=["category", "count"],
        rows=[
            ["self_pulled", self_pulled],
            ["maintainer_closed", maintainer_closed],
            ["unknown_actor", unknown],
            ["pending_enrichment", pending],
        ],
        metadata=metadata,
    )


__all__ = [
    "EnrichmentSummary",
    "compute_classification",
    "enrich_close_actors",
]
