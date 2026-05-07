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

from gitsweeper.capabilities import (
    kpi_timeseries,
    pr_classification,
    pr_throughput,
    regression_monitoring,
)
from gitsweeper.capabilities import process_report as _process_report
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
    repos: list[str] = typer.Argument(
        None, help="One or more GitHub owner/repo arguments"
    ),
    org: str | None = typer.Option(
        None, "--org", help="Fetch every repository in this GitHub organisation"
    ),
    db_path: Path = typer.Option(
        None, "--db-path", help="SQLite cache path (default: XDG state)"
    ),
) -> None:
    """Fetch all pull requests for one or more repositories.

    Repositories can be passed positionally as `owner/repo` arguments
    and/or sourced from a GitHub organisation via `--org`. Combining
    sources is allowed; duplicates are de-duplicated."""
    if not repos and not org:
        raise typer.BadParameter(
            "specify at least one owner/repo argument or use --org"
        )
    db = db_path or _default_db_path()
    conn = _open_db(db)
    targets: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    with GitHubClient.from_env() as client:
        if org:
            try:
                for body in client.list_org_repos(org):
                    pair = (body.get("owner", {}).get("login") or org, body["name"])
                    if pair not in seen:
                        seen.add(pair)
                        targets.append(pair)
            except Exception as exc:  # noqa: BLE001 - top-level CLI error
                typer.echo(f"failed to list org {org!r}: {exc}", err=True)
                raise typer.Exit(code=2) from exc
            if not targets:
                typer.echo(f"org {org!r} returned no repositories", err=True)
                raise typer.Exit(code=2)
        for repo in repos or []:
            owner, name = _split_repo(repo)
            pair = (owner, name)
            if pair not in seen:
                seen.add(pair)
                targets.append(pair)

        any_failed = False
        for owner, name in targets:
            try:
                summary = pr_throughput.fetch_and_persist(conn, client, owner, name)
                typer.echo(
                    f"Fetched {summary.pulls_written:>5} PRs from {owner}/{name}",
                    err=False,
                )
            except Exception as exc:  # noqa: BLE001 - we want the batch to continue
                any_failed = True
                typer.echo(f"  FAILED  {owner}/{name}: {exc}", err=True)

    typer.echo(f"Cache at {db}", err=False)
    if any_failed:
        raise typer.Exit(code=1)


@app.command()
def throughput(
    repo: str = typer.Argument(..., help="GitHub owner/repo"),
    since: str | None = typer.Option(
        None, "--since", help="Lower bound on merge date (YYYY-MM-DD UTC)"
    ),
    author: str | None = typer.Option(
        None, "--author", help="Restrict to PRs by this GitHub login (case-insensitive)"
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
    result = pr_throughput.compute_throughput(
        conn, repo_id, owner, name, since=since_iso, author=author
    )
    _renderer_for(json_out).render(result)


@app.command(name="first-response")
def first_response(
    repo: str = typer.Argument(..., help="GitHub owner/repo"),
    since: str | None = typer.Option(
        None, "--since", help="Lower bound on merge date (YYYY-MM-DD UTC)"
    ),
    author: str | None = typer.Option(
        None, "--author", help="Restrict reporting to PRs by this GitHub login"
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
            conn, client, repo_id, owner, name, since=since_iso, author=author
        )
    _renderer_for(json_out).render(result)


@app.command()
def patterns(
    repo: str = typer.Argument(..., help="GitHub owner/repo"),
    since: str | None = typer.Option(
        None, "--since", help="Lower bound on response date (YYYY-MM-DD UTC)"
    ),
    author: str | None = typer.Option(
        None, "--author", help="Restrict to PRs by this GitHub login"
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
    db_path: Path = typer.Option(None, "--db-path", help="SQLite cache path"),
) -> None:
    """Day-of-week and hour-of-day patterns for submissions and responses."""
    owner, name = _split_repo(repo)
    since_iso = _validate_since(since)
    db = db_path or _default_db_path()
    conn = _open_db(db)
    repo_id = storage.get_or_create_repository(conn, owner, name)
    result = pr_throughput.compute_temporal_patterns(
        conn, repo_id, owner, name, author=author, since=since_iso
    )
    _renderer_for(json_out).render(result)


@app.command()
def classify(
    repo: str = typer.Argument(..., help="GitHub owner/repo"),
    author: str | None = typer.Option(
        None, "--author", help="Restrict reporting to PRs by this GitHub login"
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
    db_path: Path = typer.Option(None, "--db-path", help="SQLite cache path"),
) -> None:
    """Categorise closed-without-merge PRs as self-pulled vs maintainer-closed.

    Costs one API call per uncached closed-without-merge PR; cached on
    subsequent runs.
    """
    owner, name = _split_repo(repo)
    db = db_path or _default_db_path()
    conn = _open_db(db)
    repo_id = storage.get_or_create_repository(conn, owner, name)
    with GitHubClient.from_env() as client:
        summary = pr_classification.enrich_close_actors(
            conn, client, repo_id, owner, name
        )
    if summary.fetched:
        typer.echo(
            f"Enriched {summary.fetched} PR(s); {summary.skipped_cached} already cached.",
            err=True,
        )
    result = pr_classification.compute_classification(
        conn, repo_id, owner, name, author=author
    )
    _renderer_for(json_out).render(result)


@app.command()
def timeseries(
    kpis: str = typer.Option(
        "median-time-to-merge,volume",
        "--kpis",
        help=(
            "Comma-separated KPI names. Recognised: "
            "median-time-to-merge, median-first-response, response-rate, volume"
        ),
    ),
    period: str = typer.Option(
        "iso-week", "--period", help="Time bucket: iso-week (default)"
    ),
    since: str | None = typer.Option(
        None, "--since", help="Lower bound on PR creation date (YYYY-MM-DD UTC)"
    ),
    author: str | None = typer.Option(
        None, "--author", help="Restrict to PRs by this GitHub login"
    ),
    by_author: bool = typer.Option(
        False, "--by-author", help="Break each (period, repo) row down by author"
    ),
    repos: list[str] = typer.Option(
        None,
        "--repos",
        help="Restrict the series to these owner/repo entries (repeatable)",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
    db_path: Path = typer.Option(None, "--db-path", help="SQLite cache path"),
) -> None:
    """Long-format time-series of KPIs across the cached repositories."""
    kpi_list = [k.strip() for k in kpis.split(",") if k.strip()]
    try:
        kpi_timeseries._validate_kpis(kpi_list)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if period != "iso-week":
        raise typer.BadParameter(
            f"unsupported --period {period!r}; supported: iso-week"
        )
    since_iso = _validate_since(since)
    repo_pairs: list[tuple[str, str]] | None = None
    if repos:
        repo_pairs = [_split_repo(r) for r in repos]
    db = db_path or _default_db_path()
    conn = _open_db(db)
    result = kpi_timeseries.compute_kpi_timeseries(
        conn,
        kpis=kpi_list,
        period="iso-week",
        since=since_iso,
        author=author,
        by_author=by_author,
        repos=repo_pairs,
    )
    _renderer_for(json_out).render(result)


@app.command()
def regressions(
    kpis: str = typer.Option(
        "median-time-to-merge,median-first-response,response-rate,volume",
        "--kpis",
        help="Comma-separated KPI names to scan",
    ),
    baseline: int = typer.Option(
        12, "--baseline", help="Number of trailing periods that form the baseline"
    ),
    threshold: float = typer.Option(
        2.0, "--threshold", help="Z-score threshold for emitting an alert"
    ),
    since: str | None = typer.Option(
        None, "--since", help="Lower bound on PR creation date (YYYY-MM-DD UTC)"
    ),
    author: str | None = typer.Option(
        None, "--author", help="Restrict to PRs by this GitHub login"
    ),
    by_author: bool = typer.Option(
        False, "--by-author", help="Compute alerts per (repo, author) instead of per repo"
    ),
    repos: list[str] = typer.Option(
        None, "--repos", help="Restrict to these owner/repo entries (repeatable)"
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
    db_path: Path = typer.Option(None, "--db-path", help="SQLite cache path"),
) -> None:
    """Trailing-baseline alerts: KPIs that moved beyond noise this period."""
    kpi_list = [k.strip() for k in kpis.split(",") if k.strip()]
    try:
        kpi_timeseries._validate_kpis(kpi_list)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    since_iso = _validate_since(since)
    repo_pairs: list[tuple[str, str]] | None = None
    if repos:
        repo_pairs = [_split_repo(r) for r in repos]
    db = db_path or _default_db_path()
    conn = _open_db(db)
    result = regression_monitoring.compute_regression_alerts(
        conn,
        kpis=kpi_list,
        baseline_periods=baseline,
        threshold_sigma=threshold,
        since=since_iso,
        author=author,
        by_author=by_author,
        repos=repo_pairs,
    )
    _renderer_for(json_out).render(result)


@app.command()
def report(
    repo: str = typer.Argument(..., help="GitHub owner/repo"),
    author: str | None = typer.Option(
        None, "--author", help="Restrict every section to PRs by this GitHub login"
    ),
    since: str | None = typer.Option(
        None, "--since", help="Lower bound on dates (YYYY-MM-DD UTC)"
    ),
    refresh: bool = typer.Option(
        False, "--refresh", help="Fetch + enrich before composing the report"
    ),
    out: Path | None = typer.Option(
        None, "--out", help="Write the markdown report to this path instead of stdout"
    ),
    db_path: Path = typer.Option(None, "--db-path", help="SQLite cache path"),
) -> None:
    """Compose a single shareable markdown process report."""
    owner, name = _split_repo(repo)
    since_iso = _validate_since(since)
    db = db_path or _default_db_path()
    conn = _open_db(db)
    try:
        with GitHubClient.from_env() as client:
            markdown = _process_report.generate_report(
                conn, client, owner, name,
                author=author, since=since_iso, refresh=refresh,
            )
    except _process_report.CacheEmpty as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
        typer.echo(f"Wrote {out}", err=True)
    else:
        typer.echo(markdown, nl=False)


def main() -> None:  # pragma: no cover - thin wrapper for entrypoint scripts
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app() or 0)
