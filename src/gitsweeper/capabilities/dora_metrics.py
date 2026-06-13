"""DORA metrics computed from the cached pull requests.

Forge-agnostic and deterministic: the four DORA metrics (deployment
frequency, lead time for changes, change failure rate, time to restore
service) are derived from the locally cached pull requests with no LLM
and no forge API calls. Each metric is computed at team level only — no
author filter, no per-person breakdown — and is annotated with its DORA
performance band plus the sample count it was computed from.

The cache holds no releases/tags, per-PR commit lists, or issue status
history, so v1 uses documented proxies (see ``design.md``):

- deployment frequency = merged PRs per ``--period`` bucket (merge ≈
  deploy);
- lead time = median/p75/p90 of ``created_at`` → ``merged_at`` (PR cycle
  time ≈ lead time);
- change failure rate = corrective merged PRs ÷ all merged PRs, where
  "corrective" is a deterministic title heuristic;
- time to restore = median ``created_at`` → ``merged_at`` over the
  corrective merged PRs.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

import polars as pl

from gitsweeper.lib import storage
from gitsweeper.lib.rendering import AnalysisResult

# --- corrective-PR heuristic ------------------------------------------------
#
# A merged PR is "corrective" when its title (case-insensitive) starts with
# one of these keywords, or matches a conventional-commit `fix:` / `fix(scope):`
# prefix. One documented constant so the heuristic can be audited and adjusted
# in a single place rather than spread across the module as literals.
CORRECTIVE_KEYWORDS: tuple[str, ...] = ("revert", "hotfix", "rollback")

# `fix` optionally followed by a `(scope)`, then a mandatory colon — the
# conventional-commit corrective prefix. Anchored to the start of the title.
_FIX_PREFIX = re.compile(r"^fix(\([^)]*\))?:", re.IGNORECASE)


def is_corrective(title: str) -> bool:
    """Return True when a PR title marks it as a fix/revert/hotfix.

    Case-insensitive. True when the title starts with one of
    ``CORRECTIVE_KEYWORDS`` or matches the conventional-commit
    ``fix:`` / ``fix(scope):`` prefix. A `fix` that appears mid-title
    (e.g. "prefix fix in middle") does not match.
    """
    stripped = title.strip()
    lowered = stripped.lower()
    if any(lowered.startswith(keyword) for keyword in CORRECTIVE_KEYWORDS):
        return True
    return _FIX_PREFIX.match(stripped) is not None


# --- DORA performance bands -------------------------------------------------
#
# Published DORA report thresholds, one documented constant per metric so the
# bands are auditable and adjustable. Units match the metric: deployment
# frequency in deploys/day, lead time and time-to-restore in days, change
# failure rate as a fraction in [0, 1]. Each list is ordered best → worst and
# read as: assign this band when the value satisfies the bound.

# Deployment frequency (deploys per day): Elite ≥ ~1/day, High weekly–monthly,
# Medium monthly–6-monthly, Low < 6-monthly. Lower bounds, best → worst.
DEPLOY_FREQUENCY_BANDS: tuple[tuple[str, float], ...] = (
    ("Elite", 1.0),          # ≥ ~daily
    ("High", 1.0 / 30.0),    # ≥ ~monthly (weekly–monthly)
    ("Medium", 1.0 / 182.5),  # ≥ ~every 6 months
    ("Low", 0.0),            # < every 6 months
)

# Lead time for changes (days): Elite < 1 day, High < 1 week, Medium < 1 month,
# Low ≥ 1 month. Upper bounds, best → worst.
LEAD_TIME_BANDS: tuple[tuple[str, float], ...] = (
    ("Elite", 1.0),
    ("High", 7.0),
    ("Medium", 30.0),
    ("Low", float("inf")),
)

# Change failure rate (fraction): Elite ≤ 15%, High ≤ 30%, Medium ≤ 45%,
# Low > 45%. Upper bounds, best → worst.
CHANGE_FAILURE_BANDS: tuple[tuple[str, float], ...] = (
    ("Elite", 0.15),
    ("High", 0.30),
    ("Medium", 0.45),
    ("Low", float("inf")),
)

# Time to restore service (days): Elite < 1 hour, High < 1 day, Medium < 1 week,
# Low ≥ 1 week. Upper bounds, best → worst.
TIME_TO_RESTORE_BANDS: tuple[tuple[str, float], ...] = (
    ("Elite", 1.0 / 24.0),
    ("High", 1.0),
    ("Medium", 7.0),
    ("Low", float("inf")),
)


def _band_lower_bound(
    bands: tuple[tuple[str, float], ...], value: float | None
) -> str | None:
    """Classify a value against best → worst *lower*-bound thresholds.

    Higher is better (deployment frequency). Returns None for a missing value.
    """
    if value is None:
        return None
    for name, bound in bands:
        if value >= bound:
            return name
    return bands[-1][0]


def _band_upper_bound(
    bands: tuple[tuple[str, float], ...], value: float | None
) -> str | None:
    """Classify a value against best → worst *upper*-bound thresholds.

    Lower is better (lead time, change failure rate, time to restore).
    Returns None for a missing value.
    """
    if value is None:
        return None
    for name, bound in bands:
        if value <= bound:
            return name
    return bands[-1][0]


# --- metric model -----------------------------------------------------------


@dataclass(frozen=True)
class Metric:
    """A single DORA metric: its value, performance band, and sample count."""

    value: float | None
    band: str | None
    sample_size: int


@dataclass(frozen=True)
class DoraReport:
    """The four DORA metrics over a scoped, team-level PR population.

    `deploy_buckets` is the per-period merge count series (list of
    ``(bucket_label, count)`` in chronological order). The metrics carry
    their own value, band, and sample count.
    """

    repo: str
    period: str
    since: str | None
    merged_total: int
    deploy_frequency: Metric
    deploy_buckets: list[tuple[str, int]]
    lead_time: dict[str, float | None]
    lead_time_band: str | None
    change_failure_rate: Metric
    time_to_restore: Metric


# --- time helpers -----------------------------------------------------------


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _days_between(start: str, end: str) -> float:
    return (_parse_iso(end) - _parse_iso(start)).total_seconds() / 86400.0


def _bucket_label(period: str, ts: datetime) -> str:
    if period == "week":
        iso = ts.isocalendar()
        return f"{iso.year:04d}-W{iso.week:02d}"
    if period == "month":
        return f"{ts.year:04d}-{ts.month:02d}"
    raise ValueError(f"unsupported period {period!r}; supported: week, month")


def _percentiles(values: list[float]) -> dict[str, float | None]:
    """median / p75 / p90 over a list of durations (days). Empty → all None."""
    if not values:
        return {"median": None, "p75": None, "p90": None}
    series = pl.Series("days", values, dtype=pl.Float64)
    return {
        "median": float(series.quantile(0.5, interpolation="linear")),
        "p75": float(series.quantile(0.75, interpolation="linear")),
        "p90": float(series.quantile(0.90, interpolation="linear")),
    }


def _title_of(raw_payload: str) -> str:
    """Read the PR title from the stored raw payload (uniform across forges)."""
    try:
        parsed = json.loads(raw_payload)
    except (TypeError, ValueError):
        return ""
    title = parsed.get("title") if isinstance(parsed, dict) else None
    return title if isinstance(title, str) else ""


# --- pure computation -------------------------------------------------------


def build_report(
    rows: list[sqlite3.Row],
    *,
    repo: str,
    period: str,
    since: str | None,
) -> DoraReport:
    """Compute the four DORA metrics over a list of cached PR rows.

    `rows` is the storage-shaped list of pull-request rows (each with
    ``created_at``, ``merged_at``, and ``raw_payload``). Only PRs with a
    non-null ``merged_at`` contribute. An empty population yields an
    explicit empty report — no NaN, no division-by-zero.
    """
    if period not in ("week", "month"):
        raise ValueError(f"unsupported period {period!r}; supported: week, month")

    merged = [r for r in rows if r["merged_at"] is not None]
    merged_total = len(merged)

    # --- deployment frequency: count merges per period bucket ---
    bucket_counts: dict[str, int] = {}
    for r in merged:
        label = _bucket_label(period, _parse_iso(r["merged_at"]))
        bucket_counts[label] = bucket_counts.get(label, 0) + 1
    deploy_buckets = sorted(bucket_counts.items())

    # Headline rate: merges per day over the observed merge span. With zero or
    # one merge there is no span to average, so the rate is the count itself
    # (still avoids divide-by-zero) and bands on the count's daily equivalent.
    deploy_rate = _deploy_rate_per_day(merged)
    deploy_frequency = Metric(
        value=deploy_rate,
        band=_band_lower_bound(DEPLOY_FREQUENCY_BANDS, deploy_rate),
        sample_size=merged_total,
    )

    # --- lead time: created → merged percentiles over merged PRs ---
    lead_durations = [_days_between(r["created_at"], r["merged_at"]) for r in merged]
    lead_time = _percentiles(lead_durations)
    lead_time_band = _band_upper_bound(LEAD_TIME_BANDS, lead_time["median"])

    # --- change failure rate: corrective merged PRs ÷ all merged PRs ---
    corrective = [r for r in merged if is_corrective(_title_of(r["raw_payload"]))]
    cfr_value = (len(corrective) / merged_total) if merged_total else None
    change_failure_rate = Metric(
        value=cfr_value,
        band=_band_upper_bound(CHANGE_FAILURE_BANDS, cfr_value),
        sample_size=merged_total,
    )

    # --- time to restore: median created → merged over corrective PRs ---
    restore_durations = [
        _days_between(r["created_at"], r["merged_at"]) for r in corrective
    ]
    ttr_value = _percentiles(restore_durations)["median"]
    time_to_restore = Metric(
        value=ttr_value,
        band=_band_upper_bound(TIME_TO_RESTORE_BANDS, ttr_value),
        sample_size=len(corrective),
    )

    return DoraReport(
        repo=repo,
        period=period,
        since=since,
        merged_total=merged_total,
        deploy_frequency=deploy_frequency,
        deploy_buckets=deploy_buckets,
        lead_time=lead_time,
        lead_time_band=lead_time_band,
        change_failure_rate=change_failure_rate,
        time_to_restore=time_to_restore,
    )


def _deploy_rate_per_day(merged: list[sqlite3.Row]) -> float | None:
    """Headline deployment frequency in deploys per day.

    None when there are no merges. With a single merge (no span) the rate is
    1.0/day so the band reflects "at least one deploy". Otherwise it is the
    merge count divided by the span (in days) from first to last merge.
    """
    if not merged:
        return None
    if len(merged) == 1:
        return 1.0
    times = sorted(_parse_iso(r["merged_at"]) for r in merged)
    span_days = (times[-1] - times[0]).total_seconds() / 86400.0
    if span_days <= 0:
        return float(len(merged))
    return len(merged) / span_days


def compute_dora(
    conn: sqlite3.Connection,
    repo_id: int,
    owner: str,
    name: str,
    *,
    period: str = "month",
    since: str | None = None,
) -> AnalysisResult:
    """Read the cached PRs for a repo and render a DORA report.

    `since` must already be an ISO 8601 string (validate user input with
    ``pr_throughput.parse_since`` first). Reads cache only — no forge calls.
    The result is team-level: it carries no author field.
    """
    rows = storage.list_pull_requests(conn, repo_id)
    if since is not None:
        rows = [
            r for r in rows if r["merged_at"] is not None and r["merged_at"] >= since
        ]
    report = build_report(
        rows, repo=f"{owner}/{name}", period=period, since=since
    )
    return _result_from_report(report)


def _result_from_report(report: DoraReport) -> AnalysisResult:
    """Shape a DoraReport into the renderer's AnalysisResult.

    One row per metric (and one row per deployment-frequency bucket) so the
    table / JSON / markdown renderers format it uniformly. Carries no author
    field — DORA is team-level only.
    """
    rows: list[list] = [
        [
            "deployment_frequency_per_day",
            report.deploy_frequency.value,
            report.deploy_frequency.band,
            report.deploy_frequency.sample_size,
        ],
        [
            "lead_time_median_days",
            report.lead_time["median"],
            report.lead_time_band,
            report.merged_total,
        ],
        ["lead_time_p75_days", report.lead_time["p75"], None, report.merged_total],
        ["lead_time_p90_days", report.lead_time["p90"], None, report.merged_total],
        [
            "change_failure_rate",
            report.change_failure_rate.value,
            report.change_failure_rate.band,
            report.change_failure_rate.sample_size,
        ],
        [
            "time_to_restore_median_days",
            report.time_to_restore.value,
            report.time_to_restore.band,
            report.time_to_restore.sample_size,
        ],
    ]
    for label, count in report.deploy_buckets:
        rows.append([f"deploys_in_{label}", count, None, count])

    metadata: dict = {
        "repo": report.repo,
        "period": report.period,
        "since": report.since,
        "merged_prs": report.merged_total,
        "proxies": "merge=deploy; PR cycle time=lead time; title heuristic=fix/restore",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    title = f"DORA metrics for {report.repo} (team-level, {report.period})"
    if report.merged_total == 0:
        metadata["note"] = "empty population: no merged PRs in the scoped window"
    return AnalysisResult(
        title=title,
        columns=["metric", "value", "band", "sample_size"],
        rows=rows,
        metadata=metadata,
    )


__all__ = [
    "CHANGE_FAILURE_BANDS",
    "CORRECTIVE_KEYWORDS",
    "DEPLOY_FREQUENCY_BANDS",
    "LEAD_TIME_BANDS",
    "TIME_TO_RESTORE_BANDS",
    "DoraReport",
    "Metric",
    "build_report",
    "compute_dora",
    "is_corrective",
]
