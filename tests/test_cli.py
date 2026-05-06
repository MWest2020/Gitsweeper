from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gitsweeper import cli
from gitsweeper.lib import storage


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _seed_cache(db: Path) -> None:
    conn = storage.connect(db)
    storage.init_schema(conn)
    repo_id = storage.get_or_create_repository(conn, "octocat", "hello")
    storage.upsert_pull_requests(
        conn,
        repo_id,
        [
            {
                "number": 1,
                "state": "closed",
                "created_at": "2025-01-01T00:00:00Z",
                "merged_at": "2025-01-02T00:00:00Z",
                "closed_at": "2025-01-02T00:00:00Z",
                "user": {"login": "alice"},
            },
            {
                "number": 2,
                "state": "closed",
                "created_at": "2025-01-01T00:00:00Z",
                "merged_at": "2025-01-08T00:00:00Z",
                "closed_at": "2025-01-08T00:00:00Z",
                "user": {"login": "alice"},
            },
        ],
    )
    conn.close()


def test_help_lists_three_commands(runner: CliRunner) -> None:
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    out = result.stdout
    assert "fetch" in out
    assert "throughput" in out
    assert "first-response" in out


def test_throughput_table_default(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "gs.sqlite"
    _seed_cache(db)
    result = runner.invoke(
        cli.app,
        ["throughput", "octocat/hello", "--db-path", str(db)],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "median" in result.stdout
    assert "p95" in result.stdout


def test_throughput_json_emits_valid_json(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "gs.sqlite"
    _seed_cache(db)
    result = runner.invoke(
        cli.app,
        ["throughput", "octocat/hello", "--json", "--db-path", str(db)],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    metrics = dict(payload["rows"])
    assert metrics["count"] == 2
    assert metrics["median"] == pytest.approx(4.0)
    assert payload["metadata"]["repo"] == "octocat/hello"


def test_malformed_since_exits_non_zero(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "gs.sqlite"
    _seed_cache(db)
    result = runner.invoke(
        cli.app,
        ["throughput", "octocat/hello", "--since", "yesterday", "--db-path", str(db)],
    )
    assert result.exit_code != 0
    assert "since" in (result.stderr + result.stdout).lower()


def test_repo_argument_must_be_owner_slash_name(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "gs.sqlite"
    _seed_cache(db)
    result = runner.invoke(
        cli.app,
        ["throughput", "octocat-hello", "--db-path", str(db)],
    )
    assert result.exit_code != 0


def test_since_filter_applied(runner: CliRunner, tmp_path: Path) -> None:
    db = tmp_path / "gs.sqlite"
    _seed_cache(db)
    result = runner.invoke(
        cli.app,
        [
            "throughput",
            "octocat/hello",
            "--since",
            "2025-01-05",
            "--json",
            "--db-path",
            str(db),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    metrics = dict(payload["rows"])
    assert metrics["count"] == 1  # only PR #2 (merged 2025-01-08)
