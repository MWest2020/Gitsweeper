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
    author: str | None = None,
) -> AnalysisResult:
    """Compute time-to-merge percentiles for merged PRs in the cache.

    `since` must already be an ISO 8601 string (use `parse_since` to
    validate user input first). `author` filters by GitHub login,
    case-insensitively."""
    rows = storage.list_pull_requests(
        conn, repo_id, merged_since=since, author=author
    )
    merged = [
        _hours_between(r["created_at"], r["merged_at"]) / 24.0
        for r in rows
        if r["merged_at"] is not None
    ]
    series = pl.Series("days", merged, dtype=pl.Float64)
    stats = _percentiles(series)
    title_scope = f" by {author}" if author else ""
    return _result_from_stats(
        title=f"time-to-merge for {owner}/{name}{title_scope} (days)",
        stats=stats,
        repo=f"{owner}/{name}",
        since=since,
        considered=len(rows),
        extra_metadata={"author": author} if author else None,
    )


def compute_first_response(
    conn: sqlite3.Connection,
    client: GitHubClient,
    repo_id: int,
    owner: str,
    name: str,
    since: str | None = None,
    author: str | None = None,
) -> AnalysisResult:
    """Ensure first-response data is cached for every PR in scope, then
    compute percentiles over the populated rows."""
    # Always enrich for *all* PRs in repo (not just author-filtered) so
    # cache stays useful for other slices. The reporting cut applies
    # author/since at the analysis step.
    pr_rows = storage.list_pull_requests(conn, repo_id, merged_since=since)
    cached = {r["pr_id"]: r for r in storage.list_first_responses(conn, repo_id)}

    for pr in pr_rows:
        pr_id = int(pr["id"])
        if pr_id in cached and cached[pr_id]["fr_fetched_at"] is not None:
            continue
        pr_author = pr["author"]
        first_at, responder = _first_non_author_comment(
            client.list_issue_comments(owner, name, int(pr["number"])), pr_author
        )
        storage.upsert_first_response(conn, pr_id, first_at, responder)

    joined = storage.list_first_responses(
        conn, repo_id, merged_since=since, author=author
    )
    durations: list[float] = []
    no_response = 0
    for r in joined:
        if r["first_response_at"] is None:
            no_response += 1
            continue
        durations.append(_hours_between(r["created_at"], r["first_response_at"]) / 24.0)

    series = pl.Series("days", durations, dtype=pl.Float64)
    stats = _percentiles(series)
    title_scope = f" by {author}" if author else ""
    extra: dict = {"no_response_yet": no_response}
    if author:
        extra["author"] = author
    return _result_from_stats(
        title=f"time-to-first-response for {owner}/{name}{title_scope} (days)",
        stats=stats,
        repo=f"{owner}/{name}",
        since=since,
        considered=len(joined),
        extra_metadata=extra,
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


DAYS_OF_WEEK = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def compute_temporal_patterns(
    conn: sqlite3.Connection,
    repo_id: int,
    owner: str,
    name: str,
    *,
    author: str | None = None,
    since: str | None = None,
) -> AnalysisResult:
    """Day-of-week and hour-of-day distributions for submissions and
    first-responses, plus median first-response by submission DOW.

    The result has one row per metric so the markdown / JSON renderers
    can format it the same way they format throughput statistics.
    """
    pr_rows = storage.list_pull_requests(conn, repo_id, author=author)
    fr_rows = storage.list_first_responses(conn, repo_id, author=author)

    submissions_dow = [0] * 7
    submissions_hour = [0] * 24
    for r in pr_rows:
        ts = _parse_iso(r["created_at"])
        submissions_dow[ts.weekday()] += 1
        submissions_hour[ts.hour] += 1

    response_dow = [0] * 7
    response_hour = [0] * 24
    median_frt_by_dow_inputs: list[list[float]] = [[] for _ in range(7)]
    for r in fr_rows:
        if r["first_response_at"] is None:
            continue
        if since is not None and r["first_response_at"] < since:
            continue
        rts = _parse_iso(r["first_response_at"])
        response_dow[rts.weekday()] += 1
        response_hour[rts.hour] += 1
        sub_dow = _parse_iso(r["created_at"]).weekday()
        days = (rts - _parse_iso(r["created_at"])).total_seconds() / 86400.0
        median_frt_by_dow_inputs[sub_dow].append(days)

    rows: list[list] = []
    for i, day in enumerate(DAYS_OF_WEEK):
        rows.append([f"submissions_dow_{day}", submissions_dow[i]])
    for i, day in enumerate(DAYS_OF_WEEK):
        rows.append([f"responses_dow_{day}", response_dow[i]])
    for i, day in enumerate(DAYS_OF_WEEK):
        vals = median_frt_by_dow_inputs[i]
        median = (
            float(pl.Series(vals, dtype=pl.Float64).quantile(0.5, interpolation="linear"))
            if vals
            else None
        )
        rows.append([f"median_frt_days_when_submitted_{day}", median])
    for h in range(24):
        rows.append([f"submissions_hour_{h:02d}", submissions_hour[h]])
    for h in range(24):
        rows.append([f"responses_hour_{h:02d}", response_hour[h]])

    metadata: dict = {
        "repo": f"{owner}/{name}",
        "since": since,
        "submissions_total": len(pr_rows),
        "responses_total": sum(response_dow),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if author:
        metadata["author"] = author

    title_scope = f" by {author}" if author else ""
    return AnalysisResult(
        title=f"temporal patterns for {owner}/{name}{title_scope}",
        columns=["metric", "value"],
        rows=rows,
        metadata=metadata,
    )


__all__ = [
    "DAYS_OF_WEEK",
    "FetchSummary",
    "compute_first_response",
    "compute_temporal_patterns",
    "compute_throughput",
    "fetch_and_persist",
    "parse_since",
]
