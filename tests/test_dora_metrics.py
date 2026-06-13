from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gitsweeper.capabilities import dora_metrics
from gitsweeper.cli import app
from gitsweeper.lib import storage
from gitsweeper.lib.forge.base import ForgePullRequest


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = storage.connect(tmp_path / "gs.sqlite")
    storage.init_schema(c)
    return c


def _pr(
    number: int,
    *,
    created: str,
    merged: str | None = None,
    title: str | None = None,
    author: str = "alice",
    raw: dict | None = None,
) -> ForgePullRequest:
    payload = raw if raw is not None else {
        "number": number,
        "state": "closed" if merged else "open",
        "created_at": created,
        "merged_at": merged,
        "title": title if title is not None else f"PR #{number}",
        "user": {"login": author},
    }
    return ForgePullRequest(
        number=number,
        state="closed" if merged else "open",
        created_at=created,
        merged_at=merged,
        closed_at=merged,
        author=author,
        raw=payload,
    )


def _persist(conn: sqlite3.Connection, prs: list[ForgePullRequest]) -> int:
    repo_id = storage.get_or_create_repository(conn, "o", "r")
    storage.upsert_pull_requests(conn, repo_id, prs)
    return repo_id


def _rows_by_metric(result) -> dict:
    return {row[0]: row for row in result.rows}


# ---- corrective heuristic -------------------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        'Revert "x"',
        "hotfix: y",
        "fix: z",
        "fix(api): z",
        "Rollback bad deploy",
        "FIX: shouting",
        "fix(scope with spaces): ok",
    ],
)
def test_is_corrective_positive(title: str) -> None:
    assert dora_metrics.is_corrective(title) is True


@pytest.mark.parametrize(
    "title",
    [
        "Add feature",
        "prefix fix in middle",
        "fixture for tests",  # fix not followed by colon/scope
        "refactor: tidy",
        "affix the label:",  # not a leading fix
        "",
    ],
)
def test_is_corrective_negative(title: str) -> None:
    assert dora_metrics.is_corrective(title) is False


# ---- deployment frequency + bucketing -------------------------------------


def test_deployment_frequency_week_buckets(conn: sqlite3.Connection) -> None:
    repo_id = _persist(conn, [
        _pr(1, created="2025-01-01T00:00:00Z", merged="2025-01-01T12:00:00Z"),
        _pr(2, created="2025-01-02T00:00:00Z", merged="2025-01-02T12:00:00Z"),
        _pr(3, created="2025-01-08T00:00:00Z", merged="2025-01-08T12:00:00Z"),
    ])
    result = dora_metrics.compute_dora(conn, repo_id, "o", "r", period="week")
    by_metric = _rows_by_metric(result)
    # 2025-01-01/02 fall in ISO week 1, 2025-01-08 in week 2.
    assert by_metric["deploys_in_2025-W01"][1] == 2
    assert by_metric["deploys_in_2025-W02"][1] == 1


def test_deployment_frequency_month_buckets(conn: sqlite3.Connection) -> None:
    repo_id = _persist(conn, [
        _pr(1, created="2025-01-01T00:00:00Z", merged="2025-01-15T00:00:00Z"),
        _pr(2, created="2025-02-01T00:00:00Z", merged="2025-02-10T00:00:00Z"),
        _pr(3, created="2025-02-05T00:00:00Z", merged="2025-02-20T00:00:00Z"),
    ])
    result = dora_metrics.compute_dora(conn, repo_id, "o", "r", period="month")
    by_metric = _rows_by_metric(result)
    assert by_metric["deploys_in_2025-01"][1] == 1
    assert by_metric["deploys_in_2025-02"][1] == 2


# ---- lead time ------------------------------------------------------------


def test_lead_time_only_merged_contribute(conn: sqlite3.Connection) -> None:
    repo_id = _persist(conn, [
        _pr(1, created="2025-01-01T00:00:00Z", merged="2025-01-02T00:00:00Z"),  # 1 day
        _pr(2, created="2025-01-01T00:00:00Z", merged="2025-01-08T00:00:00Z"),  # 7 days
        _pr(3, created="2025-01-01T00:00:00Z"),  # open, excluded
    ])
    result = dora_metrics.compute_dora(conn, repo_id, "o", "r")
    by_metric = _rows_by_metric(result)
    assert by_metric["lead_time_median_days"][1] == pytest.approx(4.0)
    assert by_metric["lead_time_median_days"][3] == 2  # sample size = merged only


# ---- change failure rate --------------------------------------------------


def test_change_failure_rate(conn: sqlite3.Connection) -> None:
    repo_id = _persist(conn, [
        _pr(1, created="2025-01-01T00:00:00Z", merged="2025-01-02T00:00:00Z",
            title="Add feature"),
        _pr(2, created="2025-01-01T00:00:00Z", merged="2025-01-02T00:00:00Z",
            title="fix: crash"),
        _pr(3, created="2025-01-01T00:00:00Z", merged="2025-01-02T00:00:00Z",
            title="hotfix: prod"),
        _pr(4, created="2025-01-01T00:00:00Z", merged="2025-01-02T00:00:00Z",
            title="Refactor"),
    ])
    result = dora_metrics.compute_dora(conn, repo_id, "o", "r")
    by_metric = _rows_by_metric(result)
    assert by_metric["change_failure_rate"][1] == pytest.approx(0.5)


# ---- time to restore ------------------------------------------------------


def test_time_to_restore_over_corrective(conn: sqlite3.Connection) -> None:
    repo_id = _persist(conn, [
        _pr(1, created="2025-01-01T00:00:00Z", merged="2025-01-03T00:00:00Z",
            title="fix: a"),  # 2 days
        _pr(2, created="2025-01-01T00:00:00Z", merged="2025-01-05T00:00:00Z",
            title="hotfix: b"),  # 4 days
        _pr(3, created="2025-01-01T00:00:00Z", merged="2025-01-20T00:00:00Z",
            title="Add feature"),  # not corrective, excluded
    ])
    result = dora_metrics.compute_dora(conn, repo_id, "o", "r")
    by_metric = _rows_by_metric(result)
    assert by_metric["time_to_restore_median_days"][1] == pytest.approx(3.0)
    assert by_metric["time_to_restore_median_days"][3] == 2  # corrective sample


# ---- band classification at boundaries ------------------------------------


def test_lead_time_bands_at_boundaries() -> None:
    b = dora_metrics.LEAD_TIME_BANDS
    assert dora_metrics._band_upper_bound(b, 1.0) == "Elite"  # ≤ 1 day
    assert dora_metrics._band_upper_bound(b, 1.0001) == "High"
    assert dora_metrics._band_upper_bound(b, 7.0) == "High"
    assert dora_metrics._band_upper_bound(b, 30.0) == "Medium"
    assert dora_metrics._band_upper_bound(b, 30.0001) == "Low"
    assert dora_metrics._band_upper_bound(b, None) is None


def test_change_failure_bands_at_boundaries() -> None:
    b = dora_metrics.CHANGE_FAILURE_BANDS
    assert dora_metrics._band_upper_bound(b, 0.15) == "Elite"
    assert dora_metrics._band_upper_bound(b, 0.1501) == "High"
    assert dora_metrics._band_upper_bound(b, 0.30) == "High"
    assert dora_metrics._band_upper_bound(b, 0.45) == "Medium"
    assert dora_metrics._band_upper_bound(b, 0.46) == "Low"


def test_deploy_frequency_bands_at_boundaries() -> None:
    b = dora_metrics.DEPLOY_FREQUENCY_BANDS
    assert dora_metrics._band_lower_bound(b, 1.0) == "Elite"  # ≥ daily
    assert dora_metrics._band_lower_bound(b, 0.5) == "High"
    assert dora_metrics._band_lower_bound(b, 1.0 / 30.0) == "High"
    assert dora_metrics._band_lower_bound(b, 1.0 / 100.0) == "Medium"
    assert dora_metrics._band_lower_bound(b, 0.0) == "Low"
    assert dora_metrics._band_lower_bound(b, None) is None


def test_time_to_restore_bands_at_boundaries() -> None:
    b = dora_metrics.TIME_TO_RESTORE_BANDS
    assert dora_metrics._band_upper_bound(b, 1.0 / 24.0) == "Elite"  # ≤ 1 hour
    assert dora_metrics._band_upper_bound(b, 0.5) == "High"
    assert dora_metrics._band_upper_bound(b, 1.0) == "High"
    assert dora_metrics._band_upper_bound(b, 7.0) == "Medium"
    assert dora_metrics._band_upper_bound(b, 8.0) == "Low"


# ---- empty population -----------------------------------------------------


def test_empty_population_no_crash(conn: sqlite3.Connection) -> None:
    repo_id = _persist(conn, [
        _pr(1, created="2025-01-01T00:00:00Z"),  # open, never merged
    ])
    result = dora_metrics.compute_dora(conn, repo_id, "o", "r")
    by_metric = _rows_by_metric(result)
    assert by_metric["change_failure_rate"][1] is None
    assert by_metric["lead_time_median_days"][1] is None
    assert by_metric["time_to_restore_median_days"][1] is None
    assert by_metric["deployment_frequency_per_day"][1] is None
    assert result.metadata["merged_prs"] == 0
    assert "empty population" in result.metadata["note"]


# ---- team-level: no author field ------------------------------------------


def test_no_author_field_in_result(conn: sqlite3.Connection) -> None:
    repo_id = _persist(conn, [
        _pr(1, created="2025-01-01T00:00:00Z", merged="2025-01-02T00:00:00Z",
            author="alice"),
        _pr(2, created="2025-01-01T00:00:00Z", merged="2025-01-02T00:00:00Z",
            author="bob"),
    ])
    result = dora_metrics.compute_dora(conn, repo_id, "o", "r")
    assert "author" not in result.columns
    assert "author" not in result.metadata
    blob = json.dumps({"columns": result.columns, "rows": result.rows,
                       "metadata": result.metadata})
    assert "alice" not in blob
    assert "bob" not in blob
    assert "author" not in blob


def test_cli_dora_has_no_author_option() -> None:
    runner = CliRunner()
    res = runner.invoke(app, ["dora", "--help"])
    assert res.exit_code == 0
    assert "--period" in res.output
    assert "--author" not in res.output


# ---- forge-agnostic: titles from each forge shape -------------------------


def test_forge_agnostic_titles_classify(conn: sqlite3.Connection) -> None:
    # GitHub-shaped, Forgejo/Gitea-shaped, GitLab-shaped raw payloads all
    # expose a top-level `title`; the heuristic reads only that.
    github_raw = {
        "number": 1, "title": "fix: gh crash", "user": {"login": "a"},
        "created_at": "2025-01-01T00:00:00Z", "merged_at": "2025-01-02T00:00:00Z",
    }
    forgejo_raw = {
        "number": 2, "title": "hotfix: forgejo", "user": {"login": "b"},
        "created_at": "2025-01-01T00:00:00Z", "merged_at": "2025-01-02T00:00:00Z",
    }
    gitlab_raw = {
        "iid": 3, "title": 'Revert "gl change"', "author": {"username": "c"},
        "created_at": "2025-01-01T00:00:00Z", "merged_at": "2025-01-02T00:00:00Z",
    }
    repo_id = _persist(conn, [
        _pr(1, created="2025-01-01T00:00:00Z", merged="2025-01-02T00:00:00Z",
            raw=github_raw),
        _pr(2, created="2025-01-01T00:00:00Z", merged="2025-01-02T00:00:00Z",
            raw=forgejo_raw),
        _pr(3, created="2025-01-01T00:00:00Z", merged="2025-01-02T00:00:00Z",
            raw=gitlab_raw),
    ])
    result = dora_metrics.compute_dora(conn, repo_id, "o", "r")
    by_metric = _rows_by_metric(result)
    # All three titles are corrective → CFR 100%.
    assert by_metric["change_failure_rate"][1] == pytest.approx(1.0)


# ---- since filter ---------------------------------------------------------


def test_since_filters_merged(conn: sqlite3.Connection) -> None:
    repo_id = _persist(conn, [
        _pr(1, created="2024-12-01T00:00:00Z", merged="2024-12-02T00:00:00Z"),
        _pr(2, created="2025-01-01T00:00:00Z", merged="2025-01-02T00:00:00Z"),
    ])
    result = dora_metrics.compute_dora(
        conn, repo_id, "o", "r", since="2025-01-01T00:00:00Z"
    )
    assert result.metadata["merged_prs"] == 1
