"""PR throughput analysis capability.

Owns the full flow for the throughput use case: fetch + persist via
the shared libraries, then compute summary statistics with polars and
hand the structured result off to the rendering layer.

Two analyses live here because they share a domain (a pull request's
lifecycle):

- time-to-merge: measured against `created_at` -> `merged_at`,
  considering only merged pull requests.
- time-to-first-response: an opt-in metric that costs one extra
  comment-list call per pull request and isolates maintainer
  responsiveness from submitter follow-up time.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import polars as pl

from gitsweeper.lib import storage
from gitsweeper.lib.github_client import GitHubClient
from gitsweeper.lib.rendering import AnalysisResult


@dataclass(frozen=True)
class FetchSummary:
    repo_id: int
    pulls_written: int


def parse_since(value: str | None) -> str | None:
    """Validate a --since YYYY-MM-DD value and return the ISO 8601 lower
    bound to compare against stored `merged_at` strings."""
    if value is None:
        return None
    try:
        d = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"--since must be YYYY-MM-DD UTC, got {value!r}"
        ) from exc
    return f"{d.isoformat()}T00:00:00Z"


def fetch_and_persist(
    conn: sqlite3.Connection,
    client: GitHubClient,
    owner: str,
    name: str,
) -> FetchSummary:
    repo_id = storage.get_or_create_repository(conn, owner, name)
    written = storage.upsert_pull_requests(
        conn, repo_id, client.list_pull_requests(owner, name)
    )
    return FetchSummary(repo_id=repo_id, pulls_written=written)


def _hours_between(start: str, end: str) -> float:
    s = datetime.fromisoformat(start.replace("Z", "+00:00"))
    e = datetime.fromisoformat(end.replace("Z", "+00:00"))
    return (e - s).total_seconds() / 3600.0


def _percentiles(values: pl.Series) -> dict[str, float | None]:
    if values.is_empty():
        return {"count": 0, "p25": None, "median": None, "p75": None, "p95": None, "max": None}
    return {
        "count": int(values.len()),
        "p25": float(values.quantile(0.25, interpolation="linear")),
        "median": float(values.quantile(0.5, interpolation="linear")),
        "p75": float(values.quantile(0.75, interpolation="linear")),
        "p95": float(values.quantile(0.95, interpolation="linear")),
        "max": float(values.max()),
    }


def compute_throughput(
    conn: sqlite3.Connection,
    repo_id: int,
    owner: str,
    name: str,
    since: str | None = None,
) -> AnalysisResult:
    """Compute time-to-merge percentiles for merged PRs in the cache.

    `since` must already be an ISO 8601 string (use `parse_since` to
    validate user input first)."""
    rows = storage.list_pull_requests(conn, repo_id, merged_since=since)
    merged = [
        _hours_between(r["created_at"], r["merged_at"]) / 24.0
        for r in rows
        if r["merged_at"] is not None
    ]
    series = pl.Series("days", merged, dtype=pl.Float64)
    stats = _percentiles(series)
    return _result_from_stats(
        title=f"time-to-merge for {owner}/{name} (days)",
        stats=stats,
        repo=f"{owner}/{name}",
        since=since,
        considered=len(rows),
    )


def compute_first_response(
    conn: sqlite3.Connection,
    client: GitHubClient,
    repo_id: int,
    owner: str,
    name: str,
    since: str | None = None,
) -> AnalysisResult:
    """Ensure first-response data is cached for every PR in scope, then
    compute percentiles over the populated rows."""
    pr_rows = storage.list_pull_requests(conn, repo_id, merged_since=since)
    cached = {r["pr_id"]: r for r in storage.list_first_responses(conn, repo_id)}

    for pr in pr_rows:
        pr_id = int(pr["id"])
        if pr_id in cached and cached[pr_id]["fr_fetched_at"] is not None:
            continue
        author = pr["author"]
        first_at, responder = _first_non_author_comment(
            client.list_issue_comments(owner, name, int(pr["number"])), author
        )
        storage.upsert_first_response(conn, pr_id, first_at, responder)

    joined = storage.list_first_responses(conn, repo_id, merged_since=since)
    durations: list[float] = []
    no_response = 0
    for r in joined:
        if r["first_response_at"] is None:
            no_response += 1
            continue
        durations.append(_hours_between(r["created_at"], r["first_response_at"]) / 24.0)

    series = pl.Series("days", durations, dtype=pl.Float64)
    stats = _percentiles(series)
    return _result_from_stats(
        title=f"time-to-first-response for {owner}/{name} (days)",
        stats=stats,
        repo=f"{owner}/{name}",
        since=since,
        considered=len(joined),
        extra_metadata={"no_response_yet": no_response},
    )


def _first_non_author_comment(
    comments: Iterable[dict], author: str
) -> tuple[str | None, str | None]:
    for comment in comments:
        user = (comment.get("user") or {}).get("login")
        if user and user != author:
            return comment.get("created_at"), user
    return None, None


def _result_from_stats(
    *,
    title: str,
    stats: dict[str, float | None],
    repo: str,
    since: str | None,
    considered: int,
    extra_metadata: dict | None = None,
) -> AnalysisResult:
    rows: list[list] = [
        ["count", stats["count"]],
        ["p25", stats["p25"]],
        ["median", stats["median"]],
        ["p75", stats["p75"]],
        ["p95", stats["p95"]],
        ["max", stats["max"]],
    ]
    metadata: dict = {
        "repo": repo,
        "since": since,
        "rows_considered": considered,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    return AnalysisResult(
        title=title,
        columns=["metric", "value"],
        rows=rows,
        metadata=metadata,
    )


__all__ = [
    "FetchSummary",
    "compute_first_response",
    "compute_throughput",
    "fetch_and_persist",
    "parse_since",
]
