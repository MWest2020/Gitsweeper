"""Gitsweeper CLI entrypoints.

Each command is a thin wrapper: parse and validate options, open the
storage and GitHub-client resources, hand work off to the capability,
and render the result through the rendering capability. No analysis
logic lives in this file.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import typer

from gitsweeper.capabilities import pr_throughput
from gitsweeper.lib import storage
from gitsweeper.lib.github_client import GitHubClient
from gitsweeper.lib.rendering import get_renderer

app = typer.Typer(
    name="gitsweeper",
    help="Mine and analyse GitHub data — sweep a repo, surface patterns.",
    no_args_is_help=True,
    add_completion=False,
)


def _default_db_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "gitsweeper" / "gitsweeper.sqlite"


def _split_repo(spec: str) -> tuple[str, str]:
    if "/" not in spec:
        raise typer.BadParameter("expected owner/repo, e.g. nextcloud/app-certificate-requests")
    owner, _, name = spec.partition("/")
    if not owner or not name or "/" in name:
        raise typer.BadParameter("expected owner/repo with exactly one slash")
    return owner, name


def _open_db(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = storage.connect(db_path)
    storage.init_schema(conn)
    return conn


def _renderer_for(json_flag: bool):
    return get_renderer("json" if json_flag else "table")


def _validate_since(value: str | None) -> str | None:
    try:
        return pr_throughput.parse_since(value)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command()
def fetch(
    repo: str = typer.Argument(..., help="GitHub owner/repo"),
    db_path: Path = typer.Option(
        None, "--db-path", help="SQLite cache path (default: XDG state)"
    ),
) -> None:
    """Fetch all pull requests for a repository and persist them locally."""
    owner, name = _split_repo(repo)
    db = db_path or _default_db_path()
    conn = _open_db(db)
    with GitHubClient.from_env() as client:
        summary = pr_throughput.fetch_and_persist(conn, client, owner, name)
    typer.echo(f"Fetched {summary.pulls_written} pull requests into {db}", err=False)


@app.command()
def throughput(
    repo: str = typer.Argument(..., help="GitHub owner/repo"),
    since: str | None = typer.Option(
        None, "--since", help="Lower bound on merge date (YYYY-MM-DD UTC)"
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
    db_path: Path = typer.Option(None, "--db-path", help="SQLite cache path"),
) -> None:
    """Compute time-to-merge percentiles from the local cache."""
    owner, name = _split_repo(repo)
    since_iso = _validate_since(since)
    db = db_path or _default_db_path()
    conn = _open_db(db)
    repo_id = storage.get_or_create_repository(conn, owner, name)
    result = pr_throughput.compute_throughput(conn, repo_id, owner, name, since=since_iso)
    _renderer_for(json_out).render(result)


@app.command(name="first-response")
def first_response(
    repo: str = typer.Argument(..., help="GitHub owner/repo"),
    since: str | None = typer.Option(
        None, "--since", help="Lower bound on merge date (YYYY-MM-DD UTC)"
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
    db_path: Path = typer.Option(None, "--db-path", help="SQLite cache path"),
) -> None:
    """Compute time-to-first-response. Costs one API call per uncached PR."""
    owner, name = _split_repo(repo)
    since_iso = _validate_since(since)
    db = db_path or _default_db_path()
    conn = _open_db(db)
    repo_id = storage.get_or_create_repository(conn, owner, name)
    with GitHubClient.from_env() as client:
        result = pr_throughput.compute_first_response(
            conn, client, repo_id, owner, name, since=since_iso
        )
    _renderer_for(json_out).render(result)


def main() -> None:  # pragma: no cover - thin wrapper for entrypoint scripts
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app() or 0)
