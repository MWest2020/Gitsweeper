"""Per-author × per-repo effort-allocation pivot.

Each row describes one (repo, author) — or (period, repo, author) when
`by_period=True` — with the volume of submissions and the breakdown
of outcomes: merged, merged_rate, self_pulled, closed_by_maintainer,
closed_unenriched, still_open.

merged_rate is computed as `merged / (merged + closed_by_maintainer)`
so that a high self-pull rate (duplicates the author cleaned up) does
not deflate the rate. closed_unenriched is its own bucket so the
operator can see when the close-actor data is incomplete.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TypedDict

from gitsweeper.lib.rendering import AnalysisResult


class _Buckets(TypedDict):
    submissions: int
    merged: int
    self_pulled: int
    closed_by_maintainer: int
    closed_unenriched: int
    still_open: int


def _empty() -> _Buckets:
    return {
        "submissions": 0,
        "merged": 0,
        "self_pulled": 0,
        "closed_by_maintainer": 0,
        "closed_unenriched": 0,
        "still_open": 0,
    }


def _iso_week(value: str) -> str:
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    iso = ts.isocalendar()
    return f"{iso.year:04d}-W{iso.week:02d}"


def _classify(row: sqlite3.Row) -> str:
    if row["merged_at"]:
        return "merged"
    if row["closed_at"] is None:
        return "still_open"
    # Closed without merge: needs the close-actor data.
    actor = row["close_actor"] if "close_actor" in row.keys() else None
    enriched = (
        row["ca_fetched_at"] is not None
        if "ca_fetched_at" in row.keys()
        else False
    )
    if not enriched:
        return "closed_unenriched"
    if actor is None:
        return "closed_unenriched"
    if actor.lower() == row["author"].lower():
        return "self_pulled"
    return "closed_by_maintainer"


def compute_effort_allocation(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
    repos: Sequence[tuple[str, str]] | None = None,
    by_period: bool = False,
) -> AnalysisResult:
    """Return per-(repo, author[, period]) submission/outcome breakdown."""
    repo_rows = conn.execute(
        "SELECT id, owner, name FROM repositories"
    ).fetchall()
    target = (
        {(o.lower(), n.lower()) for (o, n) in repos} if repos is not None else None
    )
    repo_ids: list[int] = []
    label_by_id: dict[int, str] = {}
    for r in repo_rows:
        if target is not None and (r["owner"].lower(), r["name"].lower()) not in target:
            continue
        repo_ids.append(int(r["id"]))
        label_by_id[int(r["id"])] = f"{r['owner']}/{r['name']}"

    if not repo_ids:
        return _make_result(rows=[], by_period=by_period, since=since,
                            repos=repos, closed_unenriched_total=0)

    placeholders = ",".join("?" * len(repo_ids))
    sql = (
        "SELECT pr.repo_id, pr.author, pr.created_at, pr.merged_at, "
        "       pr.closed_at, "
        "       ca.actor AS close_actor, ca.fetched_at AS ca_fetched_at "
        "FROM pull_requests pr "
        "LEFT JOIN pr_close_actors ca ON ca.pr_id = pr.id "
        f"WHERE pr.repo_id IN ({placeholders})"
    )
    params: list = list(repo_ids)
    if since is not None:
        sql += " AND pr.created_at >= ?"
        params.append(since)
    sql += " ORDER BY pr.created_at"
    cursor = conn.execute(sql, params)

    buckets: dict[tuple, _Buckets] = {}
    closed_unenriched_total = 0
    for row in cursor:
        repo = label_by_id[int(row["repo_id"])]
        author = row["author"]
        period = _iso_week(row["created_at"]) if by_period else None
        key = (period, repo, author) if by_period else (repo, author)
        if key not in buckets:
            buckets[key] = _empty()
        b = buckets[key]
        b["submissions"] += 1
        kind = _classify(row)
        if kind == "merged":
            b["merged"] += 1
        elif kind == "still_open":
            b["still_open"] += 1
        elif kind == "self_pulled":
            b["self_pulled"] += 1
        elif kind == "closed_by_maintainer":
            b["closed_by_maintainer"] += 1
        else:
            b["closed_unenriched"] += 1
            closed_unenriched_total += 1

    rows: list[list] = []
    for key in sorted(buckets):
        b = buckets[key]
        denom = b["merged"] + b["closed_by_maintainer"]
        merged_rate = (b["merged"] / denom) if denom > 0 else None
        if by_period:
            period, repo, author = key
            rows.append([
                period, repo, author,
                b["submissions"], b["merged"], merged_rate,
                b["self_pulled"], b["closed_by_maintainer"],
                b["closed_unenriched"], b["still_open"],
            ])
        else:
            repo, author = key
            rows.append([
                repo, author,
                b["submissions"], b["merged"], merged_rate,
                b["self_pulled"], b["closed_by_maintainer"],
                b["closed_unenriched"], b["still_open"],
            ])

    return _make_result(
        rows=rows,
        by_period=by_period,
        since=since,
        repos=repos,
        closed_unenriched_total=closed_unenriched_total,
    )


def _make_result(
    *,
    rows: list[list],
    by_period: bool,
    since: str | None,
    repos: Sequence[tuple[str, str]] | None,
    closed_unenriched_total: int,
) -> AnalysisResult:
    columns_base = [
        "submissions", "merged", "merged_rate",
        "self_pulled", "closed_by_maintainer",
        "closed_unenriched", "still_open",
    ]
    if by_period:
        columns = ["period", "repo", "author", *columns_base]
        title = "effort allocation per period × repo × author"
    else:
        columns = ["repo", "author", *columns_base]
        title = "effort allocation per repo × author"

    metadata: dict = {
        "row_count": len(rows),
        "since": since,
        "by_period": by_period,
        "closed_unenriched_total": closed_unenriched_total,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if repos is not None:
        metadata["repos"] = [f"{o}/{n}" for (o, n) in repos]

    return AnalysisResult(title=title, columns=columns, rows=rows, metadata=metadata)


__all__ = ["compute_effort_allocation"]
