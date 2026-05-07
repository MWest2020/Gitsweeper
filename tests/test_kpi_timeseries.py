from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gitsweeper import cli
from gitsweeper.capabilities import kpi_timeseries, pr_throughput
from gitsweeper.lib import storage


class FakeFetchClient:
    def __init__(self, prs: list[dict]) -> None:
        self._prs = prs

    def list_pull_requests(self, owner: str, repo: str, state: str = "all") -> Iterator[dict]:
        yield from self._prs


def _pr(
    number: int,
    *,
    created: str,
    merged: str | None = None,
    author: str = "alice",
) -> dict:
    return {
        "number": number,
        "state": "closed" if merged else "open",
        "created_at": created,
        "merged_at": merged,
        "closed_at": merged,
        "user": {"login": author},
    }


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = storage.connect(tmp_path / "gs.sqlite")
    storage.init_schema(c)
    return c


def _seed(conn: sqlite3.Connection, owner: str, name: str, prs: list[dict]) -> int:
    return pr_throughput.fetch_and_persist(
        conn, FakeFetchClient(prs=prs), owner, name
    ).repo_id


def test_validate_kpis_rejects_unknown() -> None:
    with pytest.raises(ValueError) as e:
        kpi_timeseries._validate_kpis(["volume", "made-up-metric"])
    assert "made-up-metric" in str(e.value)


def test_iso_week_bucketing(conn: sqlite3.Connection) -> None:
    # 2026-01-05 is a Monday → ISO 2026-W02 (because 2026-01-01 is Thursday)
    # 2026-01-12 is the following Monday → ISO 2026-W03
    _seed(
        conn, "o", "r",
        prs=[
            _pr(1, created="2026-01-05T08:00:00Z", merged="2026-01-06T08:00:00Z"),
            _pr(2, created="2026-01-05T09:00:00Z", merged="2026-01-07T09:00:00Z"),
            _pr(3, created="2026-01-12T10:00:00Z", merged="2026-01-13T10:00:00Z"),
        ],
    )
    result = kpi_timeseries.compute_kpi_timeseries(
        conn, kpis=["median-time-to-merge", "volume"]
    )
    by_period_kpi = {(r[0], r[3]): r for r in result.rows}
    assert ("2026-W02", "volume") in by_period_kpi
    assert ("2026-W03", "volume") in by_period_kpi
    assert by_period_kpi[("2026-W02", "volume")][4] == 2
    assert by_period_kpi[("2026-W03", "volume")][4] == 1
    # Median TTM in W02: median of [1.0, 2.0] = 1.5d
    assert by_period_kpi[("2026-W02", "median-time-to-merge")][4] == pytest.approx(1.5)
    assert by_period_kpi[("2026-W03", "median-time-to-merge")][4] == pytest.approx(1.0)


def test_empty_buckets_omitted_for_medians_but_volume_emitted(
    conn: sqlite3.Connection,
) -> None:
    # All open: median TTM should be omitted; volume should be present.
    _seed(conn, "o", "r", prs=[_pr(1, created="2026-01-05T08:00:00Z")])
    result = kpi_timeseries.compute_kpi_timeseries(
        conn, kpis=["median-time-to-merge", "volume"]
    )
    metrics = {(r[0], r[3]) for r in result.rows}
    assert ("2026-W02", "volume") in metrics
    assert ("2026-W02", "median-time-to-merge") not in metrics


def test_multi_repo_aggregation(conn: sqlite3.Connection) -> None:
    _seed(
        conn, "ConductionNL", "openregister",
        prs=[_pr(1, created="2026-01-05T08:00:00Z", merged="2026-01-06T08:00:00Z")],
    )
    _seed(
        conn, "ConductionNL", "opencatalogi",
        prs=[_pr(1, created="2026-01-05T08:00:00Z", merged="2026-01-08T08:00:00Z")],
    )
    result = kpi_timeseries.compute_kpi_timeseries(
        conn, kpis=["volume", "median-time-to-merge"]
    )
    by_repo_kpi = {(r[1], r[3]): r for r in result.rows if r[0] == "2026-W02"}
    assert by_repo_kpi[("ConductionNL/openregister", "median-time-to-merge")][4] == 1.0
    assert by_repo_kpi[("ConductionNL/opencatalogi", "median-time-to-merge")][4] == 3.0


def test_repos_filter_restricts_population(conn: sqlite3.Connection) -> None:
    _seed(
        conn, "ConductionNL", "openregister",
        prs=[_pr(1, created="2026-01-05T08:00:00Z", merged="2026-01-06T08:00:00Z")],
    )
    _seed(
        conn, "ConductionNL", "opencatalogi",
        prs=[_pr(1, created="2026-01-05T08:00:00Z", merged="2026-01-08T08:00:00Z")],
    )
    result = kpi_timeseries.compute_kpi_timeseries(
        conn,
        kpis=["volume"],
        repos=[("ConductionNL", "openregister")],
    )
    repos_seen = {r[1] for r in result.rows}
    assert repos_seen == {"ConductionNL/openregister"}


def test_by_author_breakdown(conn: sqlite3.Connection) -> None:
    _seed(
        conn, "o", "r",
        prs=[
            _pr(1, created="2026-01-05T08:00:00Z", merged="2026-01-06T08:00:00Z", author="alice"),
            _pr(2, created="2026-01-05T08:00:00Z", merged="2026-01-09T08:00:00Z", author="bob"),
        ],
    )
    result = kpi_timeseries.compute_kpi_timeseries(
        conn, kpis=["volume"], by_author=True
    )
    authors_seen = {r[2] for r in result.rows}
    assert authors_seen == {"alice", "bob"}
    assert result.metadata["by_author"] is True


def test_since_filter(conn: sqlite3.Connection) -> None:
    _seed(
        conn, "o", "r",
        prs=[
            _pr(1, created="2025-12-29T08:00:00Z", merged="2025-12-30T08:00:00Z"),
            _pr(2, created="2026-01-05T08:00:00Z", merged="2026-01-06T08:00:00Z"),
        ],
    )
    result = kpi_timeseries.compute_kpi_timeseries(
        conn, kpis=["volume"], since="2026-01-01T00:00:00Z"
    )
    periods_seen = {r[0] for r in result.rows}
    assert periods_seen == {"2026-W02"}


# CLI integration

def test_cli_timeseries_json_smoke(tmp_path: Path) -> None:
    db = tmp_path / "gs.sqlite"
    conn = storage.connect(db)
    storage.init_schema(conn)
    _seed(
        conn, "o", "r",
        prs=[_pr(1, created="2026-01-05T08:00:00Z", merged="2026-01-06T08:00:00Z")],
    )
    conn.close()

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        ["timeseries", "--kpis", "volume", "--json", "--db-path", str(db)],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert any(r[3] == "volume" for r in payload["rows"])


def test_cli_timeseries_unknown_kpi_rejected(tmp_path: Path) -> None:
    db = tmp_path / "gs.sqlite"
    conn = storage.connect(db)
    storage.init_schema(conn)
    conn.close()
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        ["timeseries", "--kpis", "made-up", "--db-path", str(db)],
    )
    assert result.exit_code != 0
    assert "made-up" in (result.stdout + result.stderr)
