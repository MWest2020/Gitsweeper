"""Reusable process report.

Composes the throughput, first-response, classification, and temporal-
pattern analyses into a single markdown document. Each section is
produced by handing a structured `AnalysisResult` to the markdown
renderer; the orchestration here decides only *which* analyses run
and in *what order*.
"""

from __future__ import annotations

import io
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Protocol

from gitsweeper.capabilities import pr_classification, pr_throughput
from gitsweeper.lib import storage
from gitsweeper.lib.rendering import AnalysisResult, get_renderer


class ReportClient(Protocol):
    def list_pull_requests(
        self, owner: str, repo: str, state: str = "all"
    ) -> Iterable[dict]: ...

    def list_issue_comments(
        self, owner: str, repo: str, issue_number: int
    ) -> Iterable[dict]: ...

    def list_issue_events(
        self, owner: str, repo: str, issue_number: int
    ) -> Iterable[dict]: ...


class CacheEmpty(RuntimeError):
    """Raised when the report is requested but the cache contains no PRs
    for the target repository and the user did not pass `--refresh`."""


def _volume_result(
    conn: sqlite3.Connection,
    repo_id: int,
    owner: str,
    name: str,
    *,
    author: str | None,
) -> AnalysisResult:
    rows = storage.list_pull_requests(conn, repo_id, author=author)
    merged = sum(1 for r in rows if r["merged_at"])
    closed_unmerged = sum(1 for r in rows if not r["merged_at"] and r["closed_at"])
    open_ = sum(1 for r in rows if not r["merged_at"] and not r["closed_at"])
    title_scope = f" by {author}" if author else ""
    metadata: dict = {"repo": f"{owner}/{name}"}
    if author:
        metadata["author"] = author
    return AnalysisResult(
        title=f"volume for {owner}/{name}{title_scope}",
        columns=["category", "count"],
        rows=[
            ["total", len(rows)],
            ["merged", merged],
            ["closed_without_merge", closed_unmerged],
            ["open", open_],
        ],
        metadata=metadata,
    )


def generate_report(
    conn: sqlite3.Connection,
    client: ReportClient,
    owner: str,
    name: str,
    *,
    author: str | None = None,
    since: str | None = None,
    refresh: bool = False,
) -> str:
    """Produce a markdown process report for `owner/repo`.

    Behaviour:
    - `refresh=True`: fetch all pull requests, fill in any missing
      first-response and close-actor enrichment, then compose. Many
      API calls.
    - `refresh=False`: refuse if no pull requests are cached for the
      repository (raise `CacheEmpty`); otherwise compose what is in
      the cache. `compute_first_response` and `enrich_close_actors`
      still fill in missing rows lazily — the same behaviour as the
      `first-response` and `classify` commands.
    """
    repo_id = storage.get_or_create_repository(conn, owner, name)

    cached_count = len(storage.list_pull_requests(conn, repo_id))
    if cached_count == 0 and not refresh:
        raise CacheEmpty(
            f"No pull requests cached for {owner}/{name}. "
            f"Run `gitsweeper fetch {owner}/{name}` first, or pass --refresh."
        )

    if refresh:
        pr_throughput.fetch_and_persist(conn, client, owner, name)

    # First-response enrichment (lazy: skips already-cached PRs).
    pr_throughput.compute_first_response(conn, client, repo_id, owner, name)
    # Classification enrichment (lazy: skips already-cached PRs).
    pr_classification.enrich_close_actors(conn, client, repo_id, owner, name)

    sections: list[AnalysisResult] = [
        _volume_result(conn, repo_id, owner, name, author=author),
        pr_throughput.compute_throughput(
            conn, repo_id, owner, name, since=since, author=author
        ),
        pr_throughput.compute_first_response(
            conn, client, repo_id, owner, name, since=since, author=author,
        ),
        pr_classification.compute_classification(
            conn, repo_id, owner, name, author=author
        ),
        pr_throughput.compute_temporal_patterns(
            conn, repo_id, owner, name, since=since, author=author
        ),
    ]

    md = get_renderer("markdown")
    buffer = io.StringIO()
    title_scope = f" — author {author}" if author else ""
    buffer.write(f"# Process report for {owner}/{name}{title_scope}\n\n")
    buffer.write(
        f"_Generated {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} "
        f"from gitsweeper local cache._\n\n"
    )
    if since:
        buffer.write(f"Scoped to PRs (and responses) on or after **{since}**.\n\n")
    for section in sections:
        md.render(section, stream=buffer)
    return buffer.getvalue()


__all__ = [
    "CacheEmpty",
    "ReportClient",
    "generate_report",
]
