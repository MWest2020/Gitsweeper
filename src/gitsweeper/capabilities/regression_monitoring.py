"""Trailing-baseline regression alerts.

Consumes the same long-format KPI series as `kpi-timeseries`,
groups by `(repo, [author], kpi)`, and emits an alert row for each
series whose latest period sits outside the trailing baseline by
more than the configured z-score threshold.

Stable series produce no rows. Series with too few trailing
periods, or a flat baseline, are skipped silently and counted in
metadata so the absence of an alert is interpretable.
"""

from __future__ import annotations

import math
import sqlite3
import statistics
from collections.abc import Sequence
from datetime import UTC, datetime

from gitsweeper.capabilities import kpi_timeseries
from gitsweeper.lib.rendering import AnalysisResult


def compute_regression_alerts(
    conn: sqlite3.Connection,
    *,
    kpis: Sequence[str] = (
        "median-time-to-merge",
        "median-first-response",
        "response-rate",
        "volume",
    ),
    baseline_periods: int = 12,
    threshold_sigma: float = 2.0,
    since: str | None = None,
    author: str | None = None,
    by_author: bool = False,
    repos: Sequence[tuple[str, str]] | None = None,
) -> AnalysisResult:
    """Emit one alert row per (repo, [author], kpi) series whose
    latest period departs from the trailing baseline by more than
    `threshold_sigma`. Stable, insufficient, or flat series are
    skipped silently."""
    series = kpi_timeseries.compute_kpi_timeseries(
        conn,
        kpis=kpis,
        period="iso-week",
        since=since,
        author=author,
        by_author=by_author,
        repos=repos,
    )

    by_key: dict[tuple, list[tuple[str, float]]] = {}
    for row in series.rows:
        period, repo, row_author, kpi, value, _ = row
        if value is None:
            continue
        key = (repo, row_author, kpi)
        by_key.setdefault(key, []).append((period, float(value)))

    rows: list[list] = []
    skipped_insufficient = 0
    skipped_flat = 0
    inspected = 0

    for (repo, row_author, kpi), values in by_key.items():
        values.sort(key=lambda pair: pair[0])
        if len(values) < baseline_periods + 1:
            skipped_insufficient += 1
            continue
        inspected += 1

        baseline = values[-(baseline_periods + 1) : -1]
        latest_period, current_value = values[-1]
        baseline_values = [v for (_, v) in baseline]
        mean = statistics.fmean(baseline_values)
        try:
            stdev = statistics.stdev(baseline_values)
        except statistics.StatisticsError:
            stdev = 0.0
        if math.isclose(stdev, 0.0):
            skipped_flat += 1
            continue
        z = (current_value - mean) / stdev
        if abs(z) < threshold_sigma:
            continue
        direction = "up" if z > 0 else "down"
        rows.append([
            repo,
            row_author,
            kpi,
            latest_period,
            current_value,
            mean,
            stdev,
            z,
            direction,
        ])

    rows.sort(key=lambda r: (-abs(r[7]), r[0], r[2]))

    metadata: dict = {
        "baseline_periods": baseline_periods,
        "threshold_sigma": threshold_sigma,
        "series_inspected": inspected,
        "series_skipped_insufficient_baseline": skipped_insufficient,
        "series_skipped_flat_baseline": skipped_flat,
        "alerts_emitted": len(rows),
        "since": since,
        "by_author": by_author,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if author:
        metadata["author"] = author
    if repos is not None:
        metadata["repos"] = [f"{o}/{n}" for (o, n) in repos]

    return AnalysisResult(
        title="regression alerts (trailing-baseline z-score)",
        columns=[
            "repo", "author", "kpi", "period",
            "current_value", "baseline_mean", "baseline_stdev",
            "z_score", "direction",
        ],
        rows=rows,
        metadata=metadata,
    )


__all__ = ["compute_regression_alerts"]
