"""Gitsweeper CLI entrypoints.

Each command is a thin wrapper: parse and validate options, open the
storage and GitHub-client resources, hand work off to the capability,
and render the result through the rendering capability. No analysis
logic lives in this file.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import typer

from gitsweeper.capabilities import dashboard as _dashboard
from gitsweeper.capabilities import (
    dora_metrics,
    effort_allocation,
    kpi_timeseries,
    pr_classification,
    pr_throughput,
    regression_monitoring,
    retro_signals,
    scheduled_delivery,
)
from gitsweeper.capabilities import process_report as _process_report
from gitsweeper.lib import storage
from gitsweeper.lib.forge import SUPPORTED_FORGES, get_forge_provider
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
    # Split on the FIRST slash only: owner = first segment, name = the rest.
    # GitHub/Forgejo names never contain a slash, so `owner/repo` is unchanged.
    # GitLab projects live in (possibly nested) namespaces — `group/sub/project`
    # → owner="group", name="sub/project" — which the GitLab provider URL-encodes
    # into the full project path.
    owner, _, name = spec.partition("/")
    if not owner or not name:
        raise typer.BadParameter(
            "expected owner/repo (GitHub/Forgejo) or group/.../project "
            "(GitLab nested namespaces), e.g. nextcloud/app-certificate-requests"
        )
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


def _validate_forge(value: str) -> str:
    if value.lower() not in SUPPORTED_FORGES:
        available = ", ".join(SUPPORTED_FORGES)
        raise typer.BadParameter(
            f"unsupported forge {value!r}; available providers: {available}"
        )
    return value.lower()


_FORGE_OPTION = typer.Option(
    "github",
    "--forge",
    callback=_validate_forge,
    help="Source forge: 'github' (default), 'forgejo' (Codeberg/Gitea), or 'gitlab'",
)


@app.command()
def fetch(
    repos: list[str] = typer.Argument(
        None, help="One or more GitHub owner/repo arguments"
    ),
    forge: str = _FORGE_OPTION,
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
    with get_forge_provider(forge=forge) as client:
        if org:
            try:
                for repo_obj in client.list_org_repos(org):
                    pair = (repo_obj.owner or org, repo_obj.name)
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
    forge: str = _FORGE_OPTION,
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
    with get_forge_provider(forge=forge) as client:
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
def dora(
    repo: str = typer.Argument(..., help="owner/repo"),
    since: str | None = typer.Option(
        None, "--since", help="Lower bound on merge date (YYYY-MM-DD UTC)"
    ),
    period: str = typer.Option(
        "month", "--period", help="Deployment-frequency bucket: week or month (default)"
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
    db_path: Path = typer.Option(None, "--db-path", help="SQLite cache path"),
) -> None:
    """Compute the four DORA metrics (team-level) from the local cache.

    Deployment frequency, lead time for changes, change failure rate, and
    time to restore service — derived from the cached merged PRs with
    documented proxies. Reads cache only; no forge API calls and no
    per-author filter (DORA is team-level by design).
    """
    if period not in ("week", "month"):
        raise typer.BadParameter(
            f"unsupported --period {period!r}; supported: week, month"
        )
    owner, name = _split_repo(repo)
    since_iso = _validate_since(since)
    db = db_path or _default_db_path()
    conn = _open_db(db)
    repo_id = storage.get_or_create_repository(conn, owner, name)
    result = dora_metrics.compute_dora(
        conn, repo_id, owner, name, period=period, since=since_iso
    )
    _renderer_for(json_out).render(result)


@app.command()
def retro(
    repo: str = typer.Argument(..., help="owner/repo"),
    forge: str = _FORGE_OPTION,
    since: str | None = typer.Option(
        None, "--since", help="Lower bound on PR creation date (YYYY-MM-DD UTC)"
    ),
    stale_days: int = typer.Option(
        retro_signals.STALE_DAYS,
        "--stale-days",
        help="An open PR older than this many days counts as stale (default 14)",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
    db_path: Path = typer.Option(None, "--db-path", help="SQLite cache path"),
) -> None:
    """Surface team-level retro signals for a repo's cached PRs.

    Stale open PRs, long discussion threads, friction language, tech-debt
    markers, and smooth merges — every signal referenced by PR number only,
    never by author (retro is team-level by design, with no per-author
    filter). Fetches each in-scope PR's comments once into a local cache
    (one comment-listing call per uncached PR); subsequent runs read the
    cache. Friction/tech-debt keyword sets are documented, deterministic
    constants — no LLM.
    """
    owner, name = _split_repo(repo)
    since_iso = _validate_since(since)
    db = db_path or _default_db_path()
    conn = _open_db(db)
    repo_id = storage.get_or_create_repository(conn, owner, name)
    with get_forge_provider(forge=forge) as client:
        result = retro_signals.compute_retro_signals(
            conn, client, repo_id, owner, name,
            since=since_iso, stale_days=stale_days,
        )
    _renderer_for(json_out).render(result)


@app.command()
def deliver(
    repo: str = typer.Argument(..., help="owner/repo"),
    forge: str = _FORGE_OPTION,
    since: str | None = typer.Option(
        None, "--since", help="Lower bound on dates (YYYY-MM-DD UTC)"
    ),
    period: str = typer.Option(
        "month",
        "--period",
        help="DORA deployment-frequency bucket: week or month (default)",
    ),
    out_format: str = typer.Option(
        "slack",
        "--format",
        help="Render as 'slack' Block Kit (default) or 'markdown'",
    ),
    out: Path | None = typer.Option(
        None, "--out", help="Write the rendered payload to this path instead of stdout"
    ),
    post: bool = typer.Option(
        False,
        "--post",
        help="POST the Block Kit payload to SLACK_WEBHOOK_URL (opt-in egress)",
    ),
    db_path: Path = typer.Option(None, "--db-path", help="SQLite cache path"),
) -> None:
    """Compose DORA + retro into one team-level message and deliver it.

    Reuses the `dora` and `retro` capabilities (it fetches+caches comments
    like `retro`, hence `--forge`) and renders the blended result as a Slack
    Block Kit payload (default) or markdown. Team-level by design: no per-author
    filter, no login or `@`-mention anywhere in the output.

    Egress is opt-in and explicit: by default the payload goes to stdout (or
    `--out FILE`) with no network call. With `--post`, the Block Kit payload is
    POSTed to the single incoming webhook in `SLACK_WEBHOOK_URL`; `--post`
    without that variable is a named error and makes no request. The webhook is
    read from the environment only — never printed, written, or logged.
    """
    if period not in ("week", "month"):
        raise typer.BadParameter(
            f"unsupported --period {period!r}; supported: week, month"
        )
    if out_format not in ("slack", "markdown"):
        raise typer.BadParameter(
            f"unsupported --format {out_format!r}; supported: slack, markdown"
        )

    # Gate egress before any work: --post requires the webhook in the env, and
    # we resolve it here so a missing variable fails fast with no network call.
    webhook_url: str | None = None
    if post:
        webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
        if not webhook_url:
            raise typer.BadParameter(
                "--post requires the SLACK_WEBHOOK_URL environment variable to be set"
            )

    owner, name = _split_repo(repo)
    since_iso = _validate_since(since)
    db = db_path or _default_db_path()
    conn = _open_db(db)
    repo_id = storage.get_or_create_repository(conn, owner, name)

    # Fetch + cache comments (like `retro`), then compute both halves from the
    # cache. We call the pure build_report functions directly so we hold the
    # report dataclasses to render, rather than the table/JSON AnalysisResult.
    with get_forge_provider(forge=forge) as client:
        retro_signals.fetch_and_cache_comments(
            conn, client, repo_id, owner, name, since=since_iso
        )

    repo_full = f"{owner}/{name}"
    all_rows = storage.list_pull_requests(conn, repo_id)

    # DORA scopes on merge date; retro scopes on creation date (mirrors each
    # capability's own scoping).
    dora_rows = all_rows
    if since_iso is not None:
        dora_rows = [
            r for r in all_rows if r["merged_at"] is not None and r["merged_at"] >= since_iso
        ]
    dora_report = dora_metrics.build_report(
        dora_rows, repo=repo_full, period=period, since=since_iso
    )

    retro_rows = all_rows
    if since_iso is not None:
        retro_rows = [r for r in all_rows if r["created_at"] >= since_iso]
    comment_rows = storage.list_comments(conn, repo_id)
    retro_report = retro_signals.build_report(
        retro_rows,
        comment_rows,
        repo=repo_full,
        since=since_iso,
        stale_days=retro_signals.STALE_DAYS,
    )

    meta = {
        "repo": repo_full,
        "window": f"since {since_iso}" if since_iso else "all time",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if out_format == "slack":
        payload = scheduled_delivery.build_blockkit(dora_report, retro_report, meta)
        rendered = json.dumps(payload, indent=2)
    else:
        rendered = scheduled_delivery.build_markdown(dora_report, retro_report, meta)

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
        typer.echo(f"Wrote {out}", err=True)
    else:
        typer.echo(rendered, nl=False if out_format == "markdown" else True)

    if post:
        # Always post the Block Kit payload (Slack incoming webhooks expect it),
        # regardless of --format. The webhook URL is never echoed.
        block_payload = scheduled_delivery.build_blockkit(
            dora_report, retro_report, meta
        )
        try:
            scheduled_delivery.post_to_webhook(webhook_url, block_payload)
        except scheduled_delivery.DeliveryError as exc:
            typer.echo(f"delivery failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        typer.echo("Posted to the configured Slack webhook.", err=True)


@app.command()
def classify(
    repo: str = typer.Argument(..., help="GitHub owner/repo"),
    forge: str = _FORGE_OPTION,
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
    with get_forge_provider(forge=forge) as client:
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
def effort(
    since: str | None = typer.Option(
        None, "--since", help="Lower bound on PR creation date (YYYY-MM-DD UTC)"
    ),
    repos: list[str] = typer.Option(
        None, "--repos", help="Restrict to these owner/repo entries (repeatable)"
    ),
    by_period: bool = typer.Option(
        False, "--by-period", help="Break each row out per ISO week"
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
    db_path: Path = typer.Option(None, "--db-path", help="SQLite cache path"),
) -> None:
    """Per-author × per-repo effort-allocation pivot."""
    since_iso = _validate_since(since)
    repo_pairs: list[tuple[str, str]] | None = None
    if repos:
        repo_pairs = [_split_repo(r) for r in repos]
    db = db_path or _default_db_path()
    conn = _open_db(db)
    result = effort_allocation.compute_effort_allocation(
        conn,
        since=since_iso,
        repos=repo_pairs,
        by_period=by_period,
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
    forge: str = _FORGE_OPTION,
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
        with get_forge_provider(forge=forge) as client:
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


@app.command()
def publish(
    out: Path = typer.Option(
        Path("docs/examples/dashboard"),
        "--out",
        help="Directory to write the HTML+SVG bundle into",
    ),
    repos: list[str] = typer.Option(
        None, "--repos", help="Restrict the bundle to these owner/repo entries"
    ),
    since: str | None = typer.Option(
        None, "--since", help="Lower bound on PR creation date (YYYY-MM-DD UTC)"
    ),
    baseline: int = typer.Option(
        12, "--baseline", help="Number of trailing periods that form the baseline"
    ),
    threshold: float = typer.Option(
        2.0, "--threshold", help="Z-score threshold for emitting an alert"
    ),
    db_path: Path = typer.Option(None, "--db-path", help="SQLite cache path"),
) -> None:
    """Publish a static HTML+SVG dashboard from the local cache."""
    since_iso = _validate_since(since)
    repo_pairs: list[tuple[str, str]] | None = None
    if repos:
        repo_pairs = [_split_repo(r) for r in repos]
    db = db_path or _default_db_path()
    conn = _open_db(db)
    try:
        summary = _dashboard.publish(
            conn,
            out_dir=out,
            repos=repo_pairs,
            since=since_iso,
            baseline_periods=baseline,
            threshold_sigma=threshold,
        )
    except _dashboard.CacheEmpty as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"Wrote dashboard for {len(summary['repos'])} repo(s) "
        f"({summary['series_rows']} series rows, {summary['alerts_emitted']} alerts) "
        f"to {summary['out_dir']}",
        err=True,
    )


@app.command()
def reconcile(
    repo: str = typer.Argument(..., help="GitHub owner/repo"),
    since: str | None = typer.Option(
        None, "--since", help="Lower bound on commit / log date (YYYY-MM-DD UTC)"
    ),
    branch: str | None = typer.Option(
        None, "--branch", help="Branch to read commits from (default: repo's default branch)"
    ),
    author: str | None = typer.Option(
        None, "--author", help="Restrict reporting to this GitHub login"
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
) -> None:
    """Reconcile commit Time: footers against Billbird /log entries.

    Pulls commits from GitHub (via the standard GITHUB_TOKEN) and time
    entries from Billbird (via BILLBIRD_API_URL + BILLBIRD_API_TOKEN),
    groups both per (repo, author, issue), and prints drift per group.
    """
    from gitsweeper.capabilities import commit_time_reconcile as reconcile_cap
    try:
        from billbird_client import BillbirdNotConfigured
    except ImportError as exc:
        typer.echo(
            "the `billbird-client` package is not installed; "
            "install with `uv add billbird-client` or `pip install gitsweeper[billbird]`",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    owner, name = _split_repo(repo)
    since_iso: str | None = None
    if since:
        try:
            # Normalise YYYY-MM-DD to ISO 8601 midnight UTC.
            since_iso = pr_throughput.parse_since(since)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

    try:
        result = reconcile_cap.reconcile_from_env(
            owner=owner,
            name=name,
            since=since_iso,
            branch=branch,
            author=author,
        )
    except BillbirdNotConfigured as exc:
        typer.echo(
            f"Billbird is not configured: missing {', '.join(exc.missing)}",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    _renderer_for(json_out).render(result)


@app.command()
def mcp() -> None:
    """Run the Manager-MCP server over stdio.

    Reads Billbird credentials from BILLBIRD_API_URL and BILLBIRD_API_TOKEN
    lazily — the server starts even without them, and Billbird-touching
    tools return a structured ``billbird_not_configured`` error if called
    without credentials. Blocks until stdin closes (i.e. until the parent
    AI client disconnects).
    """
    try:
        from gitsweeper.capabilities.manager_mcp import run_stdio
    except ImportError as exc:
        typer.echo(
            f"MCP support requires the 'mcp' package: {exc}",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    run_stdio()


def main() -> None:  # pragma: no cover - thin wrapper for entrypoint scripts
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app() or 0)
