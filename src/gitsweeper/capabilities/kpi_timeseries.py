"""Time-bucketed KPI series across one or more cached repositories.

Output is long-format: one row per (period, repo, author, kpi) tuple
that has at least one qualifying pull request. Empty buckets are
omitted, never reported as `NaN` or `0` — long format already
self-describes its sparsity. The renderer interface
(`report-rendering`) consumes this directly.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Literal

import polars as pl

from gitsweeper.lib.rendering import AnalysisResult

KPI_NAMES = (
    "median-time-to-merge",
    "median-first-response",
    "response-rate",
    "volume",
)

PeriodSpec = Literal["iso-week"]
DEFAULT_PERIOD: PeriodSpec = "iso-week"


def _validate_kpis(requested: Sequence[str]) -> list[str]:
    unknown = [k for k in requested if k not in KPI_NAMES]
    if unknown:
        raise ValueError(
            f"unknown KPI(s): {', '.join(unknown)}. "
            f"Recognised: {', '.join(KPI_NAMES)}"
        )
    return list(requested)


def _bucket_label(period: PeriodSpec, ts: datetime) -> str:
    if period == "iso-week":
        iso = ts.isocalendar()
        return f"{iso.year:04d}-W{iso.week:02d}"
    raise ValueError(f"unsupported period {period!r}")


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _select_rows(
    conn: sqlite3.Connection,
    *,
    repos: Sequence[tuple[str, str]] | None,
    author: str | None,
    since: str | None,
) -> pl.DataFrame:
    """Pull the union of rows across the requested repos into a single
    polars DataFrame keyed by repo, author, created_at, merged_at, and
    first_response_at."""
    repo_rows = conn.execute(
        "SELECT id, owner, name FROM repositories"
    ).fetchall()
    repo_ids: list[int] = []
    repo_label_by_id: dict[int, str] = {}
    target = (
        {(o.lower(), n.lower()) for (o, n) in repos} if repos is not None else None
    )
    for r in repo_rows:
        label = f"{r['owner']}/{r['name']}"
        key = (r["owner"].lower(), r["name"].lower())
        if target is not None and key not in target:
            continue
        repo_ids.append(int(r["id"]))
        repo_label_by_id[int(r["id"])] = label
    if not repo_ids:
        return pl.DataFrame(schema={
            "repo": pl.String, "author": pl.String,
            "created_at": pl.String, "merged_at": pl.String,
            "first_response_at": pl.String,
        })

    placeholders = ",".join("?" * len(repo_ids))
    sql = (
        "SELECT pr.repo_id, pr.author, pr.created_at, pr.merged_at, "
        "       fr.first_response_at "
        "FROM pull_requests pr "
        "LEFT JOIN pr_first_responses fr ON fr.pr_id = pr.id "
        f"WHERE pr.repo_id IN ({placeholders})"
    )
    params: list = list(repo_ids)
    if since is not None:
        sql += " AND pr.created_at >= ?"
        params.append(since)
    if author is not None:
        sql += " AND LOWER(pr.author) = LOWER(?)"
        params.append(author)
    rows = conn.execute(sql, params).fetchall()

    return pl.DataFrame({
        "repo": [repo_label_by_id[int(r["repo_id"])] for r in rows],
        "author": [r["author"] for r in rows],
        "created_at": [r["created_at"] for r in rows],
        "merged_at": [r["merged_at"] for r in rows],
        "first_response_at": [r["first_response_at"] for r in rows],
    })


def _hours_to_days(start: str, end: str) -> float:
    return (_parse_ts(end) - _parse_ts(start)).total_seconds() / 86400.0


def compute_kpi_timeseries(
    conn: sqlite3.Connection,
    *,
    kpis: Sequence[str] = ("median-time-to-merge", "volume"),
    period: PeriodSpec = DEFAULT_PERIOD,
    since: str | None = None,
    author: str | None = None,
    by_author: bool = False,
    repos: Sequence[tuple[str, str]] | None = None,
) -> AnalysisResult:
    """Compute long-format KPI time-series.

    `kpis` is validated against the closed registry; unknown names
    raise ValueError so the CLI layer can convert to BadParameter.
    """
    kpi_list = _validate_kpis(kpis)
    df = _select_rows(conn, repos=repos, author=author, since=since)

    rows: list[list] = []
    if df.is_empty():
        return _make_result(rows, kpi_list, period, since, author, by_author, repos)

    # Pre-compute bucket labels and durations
    df = df.with_columns(
        pl.Series(
            "period",
            [_bucket_label(period, _parse_ts(ts)) for ts in df["created_at"].to_list()],
            dtype=pl.String,
        ),
    )

    group_cols = ["period", "repo"]
    if by_author:
        group_cols.append("author")

    for keys, sub in df.group_by(group_cols, maintain_order=True):
        period_label = keys[0]
        repo_label = keys[1]
        author_label = keys[2] if by_author else None

        scope = (period_label, repo_label, author_label)
        for kpi in kpi_list:
            value, sample = _kpi_value(kpi, sub)
            if value is None and kpi != "volume":
                # Empty-bucket omission: don't emit the row at all.
                # Volume is always emitted (it's a count).
                continue
            rows.append([*scope, kpi, value, sample])

    return _make_result(rows, kpi_list, period, since, author, by_author, repos)


def _kpi_value(kpi: str, sub: pl.DataFrame) -> tuple[float | int | None, int]:
    if kpi == "volume":
        return int(sub.height), int(sub.height)
    if kpi == "median-time-to-merge":
        merged = sub.filter(pl.col("merged_at").is_not_null())
        if merged.is_empty():
            return None, 0
        days = [
            _hours_to_days(c, m)
            for c, m in zip(
                merged["created_at"].to_list(),
                merged["merged_at"].to_list(),
                strict=True,
            )
        ]
        return (
            float(pl.Series(days, dtype=pl.Float64).quantile(0.5, "linear")),
            len(days),
        )
    if kpi == "median-first-response":
        responded = sub.filter(pl.col("first_response_at").is_not_null())
        if responded.is_empty():
            return None, 0
        days = [
            _hours_to_days(c, f)
            for c, f in zip(
                responded["created_at"].to_list(),
                responded["first_response_at"].to_list(),
                strict=True,
            )
        ]
        return (
            float(pl.Series(days, dtype=pl.Float64).quantile(0.5, "linear")),
            len(days),
        )
    if kpi == "response-rate":
        if sub.is_empty():
            return None, 0
        responded = sub.filter(pl.col("first_response_at").is_not_null()).height
        rate = responded / sub.height
        return float(rate), int(sub.height)
    raise ValueError(f"unhandled KPI {kpi!r}")


def _make_result(
    rows: Iterable[list],
    kpis: Sequence[str],
    period: PeriodSpec,
    since: str | None,
    author: str | None,
    by_author: bool,
    repos: Sequence[tuple[str, str]] | None,
) -> AnalysisResult:
    materialised = list(rows)
    materialised.sort(key=lambda r: (r[0], r[1], r[2] or "", r[3]))
    metadata: dict = {
        "period": period,
        "kpis": list(kpis),
        "row_count": len(materialised),
        "since": since,
        "by_author": by_author,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if author:
        metadata["author"] = author
    if repos is not None:
        metadata["repos"] = [f"{o}/{n}" for (o, n) in repos]

    return AnalysisResult(
        title=f"KPI time-series ({period})",
        columns=["period", "repo", "author", "kpi", "value", "sample_size"],
        rows=materialised,
        metadata=metadata,
    )


__all__ = [
    "DEFAULT_PERIOD",
    "KPI_NAMES",
    "compute_kpi_timeseries",
]
