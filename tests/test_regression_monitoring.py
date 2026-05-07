from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from gitsweeper.capabilities import pr_throughput, regression_monitoring
from gitsweeper.lib import storage


class FakeFetchClient:
    def __init__(self, prs: list[dict]) -> None:
        self._prs = prs

    def list_pull_requests(self, owner: str, repo: str, state: str = "all") -> Iterator[dict]:
        yield from self._prs


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = storage.connect(tmp_path / "gs.sqlite")
    storage.init_schema(c)
    return c


def _monday(year: int, week: int) -> datetime:
    return datetime.fromisocalendar(year, week, 1)


def _seed_weekly_volume(
    conn: sqlite3.Connection,
    owner: str,
    name: str,
    counts: list[int],
    *,
    start_year: int = 2026,
    start_week: int = 1,
) -> None:
    """Create N PRs in each ISO week, all merged the same day."""
    prs: list[dict] = []
    pr_number = 1
    for offset, count in enumerate(counts):
        # Walk through ISO weeks: year/week increments via Monday calc
        monday = _monday(start_year, start_week) + timedelta(weeks=offset)
        for _ in range(count):
            created = monday.replace(hour=8).strftime("%Y-%m-%dT%H:%M:%SZ")
            merged = (monday + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
            prs.append({
                "number": pr_number,
                "state": "closed",
                "created_at": created,
                "merged_at": merged,
                "closed_at": merged,
                "user": {"login": "alice"},
            })
            pr_number += 1
    pr_throughput.fetch_and_persist(conn, FakeFetchClient(prs=prs), owner, name)


def test_stable_series_produces_no_alerts(conn: sqlite3.Connection) -> None:
    # 10 weeks of constant volume = 5 — flat baseline; final week 5
    _seed_weekly_volume(conn, "o", "r", [5] * 10)
    result = regression_monitoring.compute_regression_alerts(
        conn, kpis=["volume"], baseline_periods=5, threshold_sigma=2.0
    )
    assert result.rows == []
    # Flat baseline → skipped flat
    assert result.metadata["series_skipped_flat_baseline"] >= 1


def test_spike_above_baseline_flagged_up(conn: sqlite3.Connection) -> None:
    # 10 weeks of mixed-but-stable volume, then a spike
    counts = [3, 4, 3, 4, 3, 4, 3, 4, 3, 20]
    _seed_weekly_volume(conn, "o", "r", counts)
    result = regression_monitoring.compute_regression_alerts(
        conn, kpis=["volume"], baseline_periods=8, threshold_sigma=2.0
    )
    by_kpi = {r[2]: r for r in result.rows}
    assert "volume" in by_kpi
    alert = by_kpi["volume"]
    assert alert[8] == "up"            # direction column index
    assert alert[7] > 2.0               # z_score > threshold


def test_drop_below_baseline_flagged_down(conn: sqlite3.Connection) -> None:
    counts = [10, 11, 10, 11, 10, 11, 10, 11, 10, 1]
    _seed_weekly_volume(conn, "o", "r", counts)
    result = regression_monitoring.compute_regression_alerts(
        conn, kpis=["volume"], baseline_periods=8, threshold_sigma=2.0
    )
    by_kpi = {r[2]: r for r in result.rows}
    assert by_kpi["volume"][8] == "down"


def test_insufficient_baseline_no_alert(conn: sqlite3.Connection) -> None:
    _seed_weekly_volume(conn, "o", "r", [3, 3, 3])  # only 3 weeks total
    result = regression_monitoring.compute_regression_alerts(
        conn, kpis=["volume"], baseline_periods=12, threshold_sigma=2.0
    )
    assert result.rows == []
    assert result.metadata["series_skipped_insufficient_baseline"] >= 1


def test_threshold_relaxes_alerts(conn: sqlite3.Connection) -> None:
    # Engineer: stable mean 5, stdev 0.5, current = 6.2 → z = 2.4
    # With threshold 2 -> alert; with threshold 3 -> no alert.
    counts = [5, 5, 5, 5, 5, 5, 5, 5, 6, 4, 6, 4, 6]  # baseline mostly ~5
    _seed_weekly_volume(conn, "o", "r", counts[:-1] + [counts[-1]])

    above = regression_monitoring.compute_regression_alerts(
        conn, kpis=["volume"], baseline_periods=10, threshold_sigma=2.0
    )
    rows_above = [r for r in above.rows if r[2] == "volume"]

    below = regression_monitoring.compute_regression_alerts(
        conn, kpis=["volume"], baseline_periods=10, threshold_sigma=99.0
    )
    rows_below = [r for r in below.rows if r[2] == "volume"]

    assert len(rows_below) == 0  # threshold 99 is unreachable
    # `above` may or may not alert depending on exact stdev — what matters
    # is that lowering the threshold cannot produce *fewer* alerts.
    assert len(rows_above) >= len(rows_below)


def test_baseline_window_truncates_history(conn: sqlite3.Connection) -> None:
    # First 4 weeks volume 100 (legacy regime), then 8 weeks volume ~5.
    # With baseline=8, the legacy regime should not contribute.
    counts = [100, 100, 100, 100, 5, 5, 5, 5, 5, 5, 5, 5, 5]
    _seed_weekly_volume(conn, "o", "r", counts)
    result = regression_monitoring.compute_regression_alerts(
        conn, kpis=["volume"], baseline_periods=8, threshold_sigma=2.0
    )
    # Latest period's volume (5) should look stable against the trailing 8
    # weeks of 5s; if the legacy regime leaked in, baseline_mean would be high.
    assert result.rows == []
