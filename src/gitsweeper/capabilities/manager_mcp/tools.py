"""MCP tool implementations — Gitsweeper analytics only.

Each tool is a small function that:

- declares its own input schema (next to the function, in registry.py)
- returns a JSON-serialisable dict or list
- echoes the resolved ``scope`` block where applicable
- declares units on every numeric field via ``unit`` keys

Tools are read-only. They either reuse the existing capability
functions directly against the local SQLite cache, or refuse with a
structured ``cache_missing`` error when the cache is incomplete.
Billbird-only read tools live in the separate ``billbird-client``
package (see ``billbird-mcp``); the only Billbird-touching tool that
remains here is ``gitsweeper_reconcile``, and it uses ``billbird-client``
as an optional dependency.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _analysis_to_payload(result) -> dict[str, Any]:
    """Convert a Gitsweeper AnalysisResult into a JSON-serialisable dict."""
    rows = [dict(zip(result.columns, row, strict=True)) for row in result.rows]
    return {
        "title": result.title,
        "columns": list(result.columns),
        "rows": rows,
        "metadata": dict(result.metadata or {}),
    }


# --- Gitsweeper tools ------------------------------------------------------


def gitsweeper_pr_throughput(
    repository: str,
    since: str | None = None,
    author: str | None = None,
) -> dict[str, Any]:
    """Time-to-merge percentiles for a repository's PR history."""
    from gitsweeper.capabilities import pr_throughput
    from gitsweeper.lib import storage

    try:
        owner, name = _split_repo(repository)
        since_iso = pr_throughput.parse_since(since) if since else None
    except ValueError as exc:
        return {"error": "invalid_argument", "hint": str(exc)}

    conn = _open_local_db()
    try:
        repo_id = storage.get_or_create_repository(conn, owner, name)
        if not _has_pr_cache(conn, repo_id):
            return _cache_missing_response(repository, ["gitsweeper fetch"])
        result = pr_throughput.compute_throughput(
            conn, repo_id, owner, name, since=since_iso, author=author
        )
    finally:
        conn.close()

    payload = _analysis_to_payload(result)
    payload.update(
        {
            "unit": "days",
            "scope": {"repository": repository, "since": since, "author": author},
        }
    )
    return payload


def gitsweeper_first_response(
    repository: str,
    since: str | None = None,
    author: str | None = None,
) -> dict[str, Any]:
    """First-response latency percentiles — cache-only.

    Differs from the CLI version in that this never enriches: if any
    in-scope PR is missing a cached first-response row, the tool
    returns a structured ``cache_missing`` error and asks the operator
    to run ``gitsweeper first-response`` first.
    """
    from gitsweeper.capabilities import pr_throughput
    from gitsweeper.lib import storage

    try:
        owner, name = _split_repo(repository)
        since_iso = pr_throughput.parse_since(since) if since else None
    except ValueError as exc:
        return {"error": "invalid_argument", "hint": str(exc)}

    conn = _open_local_db()
    try:
        repo_id = storage.get_or_create_repository(conn, owner, name)
        pr_rows = storage.list_pull_requests(conn, repo_id, merged_since=since_iso)
        if not pr_rows:
            return _cache_missing_response(repository, ["gitsweeper fetch"])
        cached = {
            int(r["pr_id"]): r for r in storage.list_first_responses(conn, repo_id)
        }
        uncached = [int(p["id"]) for p in pr_rows if int(p["id"]) not in cached]
        if uncached:
            return {
                "error": "cache_missing",
                "repository": repository,
                "missing_count": len(uncached),
                "next_step": (
                    "run `gitsweeper first-response "
                    f"{repository}` first; the MCP layer never auto-fetches"
                ),
            }
        result = pr_throughput.compute_first_response(
            conn, _DisabledClient(), repo_id, owner, name, since=since_iso, author=author
        )
    finally:
        conn.close()

    payload = _analysis_to_payload(result)
    payload.update(
        {
            "unit": "days",
            "scope": {"repository": repository, "since": since, "author": author},
        }
    )
    return payload


def gitsweeper_classify(repository: str, author: str | None = None) -> dict[str, Any]:
    """Self-pulled vs maintainer-closed classification for closed-unmerged PRs.

    Cache-only: if any closed-without-merge PR lacks a cached close
    actor, the tool returns a ``cache_missing`` error rather than
    issuing API calls.
    """
    from gitsweeper.capabilities import pr_classification
    from gitsweeper.lib import storage

    try:
        owner, name = _split_repo(repository)
    except ValueError as exc:
        return {"error": "invalid_argument", "hint": str(exc)}

    conn = _open_local_db()
    try:
        repo_id = storage.get_or_create_repository(conn, owner, name)
        pr_rows = storage.list_pull_requests(conn, repo_id)
        if not pr_rows:
            return _cache_missing_response(repository, ["gitsweeper fetch"])
        cached_actors = {
            int(r["pr_id"]) for r in storage.list_close_actors(conn, repo_id)
        }
        closed_unmerged = [
            int(p["id"])
            for p in pr_rows
            if p["state"] == "closed" and p["merged_at"] is None
        ]
        uncached = [pr_id for pr_id in closed_unmerged if pr_id not in cached_actors]
        if uncached:
            return {
                "error": "cache_missing",
                "repository": repository,
                "missing_count": len(uncached),
                "next_step": (
                    f"run `gitsweeper classify {repository}` first; "
                    "the MCP layer never auto-fetches"
                ),
            }
        result = pr_classification.compute_classification(
            conn, repo_id, owner, name, author=author
        )
    finally:
        conn.close()

    payload = _analysis_to_payload(result)
    payload.update(
        {
            "unit": "count",
            "scope": {"repository": repository, "author": author},
        }
    )
    return payload


def gitsweeper_patterns(
    repository: str,
    since: str | None = None,
    author: str | None = None,
) -> dict[str, Any]:
    """Day-of-week / hour-of-day patterns for submissions and responses."""
    from gitsweeper.capabilities import pr_throughput
    from gitsweeper.lib import storage

    try:
        owner, name = _split_repo(repository)
        since_iso = pr_throughput.parse_since(since) if since else None
    except ValueError as exc:
        return {"error": "invalid_argument", "hint": str(exc)}

    conn = _open_local_db()
    try:
        repo_id = storage.get_or_create_repository(conn, owner, name)
        if not _has_pr_cache(conn, repo_id):
            return _cache_missing_response(repository, ["gitsweeper fetch"])
        result = pr_throughput.compute_temporal_patterns(
            conn, repo_id, owner, name, since=since_iso, author=author
        )
    finally:
        conn.close()

    payload = _analysis_to_payload(result)
    payload.update(
        {
            "unit": "count",
            "scope": {"repository": repository, "since": since, "author": author},
        }
    )
    return payload


def gitsweeper_reconcile(
    repository: str,
    since: str | None = None,
    branch: str | None = None,
    author: str | None = None,
) -> dict[str, Any]:
    """Reconcile commit Time: footers against Billbird /log entries.

    Imports ``billbird-client`` lazily so a Gitsweeper install without
    the optional ``[billbird]`` extra fails with a structured
    ``billbird_client_unavailable`` envelope instead of an
    ``ImportError`` traceback.
    """
    from gitsweeper.capabilities import commit_time_reconcile as reconcile_cap

    try:
        owner, name = _split_repo(repository)
    except ValueError as exc:
        return {"error": "invalid_argument", "hint": str(exc)}

    try:
        from billbird_client import (
            BillbirdClient,
            BillbirdHTTPError,
            BillbirdNotConfigured,
        )
    except ImportError:
        return {
            "error": "billbird_client_unavailable",
            "hint": (
                "the `billbird-client` package is not installed; "
                "install with `pip install gitsweeper[billbird]` "
                "or `uv add billbird-client`"
            ),
        }

    try:
        with BillbirdClient.from_env() as bb:
            result = reconcile_cap.reconcile(
                github=_open_github(),
                billbird=bb,
                owner=owner,
                name=name,
                since=since,
                branch=branch,
                author=author,
            )
    except BillbirdNotConfigured as exc:
        return {
            "error": "billbird_not_configured",
            "missing": exc.missing,
            "docs": "docs/reconcile.md",
        }
    except BillbirdHTTPError as exc:
        return {
            "error": "billbird_http_error",
            "status": exc.status,
            "hint": exc.hint,
            "body": exc.body,
        }

    payload = _analysis_to_payload(result)
    payload.update(
        {
            "unit": "minutes",
            "scope": {
                "repository": repository,
                "since": since,
                "branch": branch,
                "author": author,
            },
        }
    )
    return payload


# --- Internal helpers -------------------------------------------------------


class _DisabledClient:
    """Stand-in for the GitHubClient used by compute_first_response.

    Raises on any call, which is the right thing: the MCP layer has
    already verified that the function will not need to fetch anything.
    """

    def list_issue_comments(self, *args, **kwargs):  # noqa: D401
        raise RuntimeError(
            "MCP layer must not fetch; cache should already be complete"
        )


def _split_repo(spec: str) -> tuple[str, str]:
    owner, _, name = spec.partition("/")
    if not owner or not name:
        raise ValueError(f"invalid repository spec {spec!r}; expected owner/repo")
    return owner, name


def _open_local_db():
    """Open the Gitsweeper SQLite cache the same way the CLI does."""
    from gitsweeper.lib import storage

    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    path = Path(base) / "gitsweeper" / "gitsweeper.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = storage.connect(path)
    storage.init_schema(conn)
    return conn


def _open_github():
    """Build a GitHubClient from env. Used by reconcile."""
    from gitsweeper.lib.github_client import GitHubClient

    return GitHubClient.from_env()


def _has_pr_cache(conn, repo_id: int) -> bool:
    from gitsweeper.lib import storage

    rows = storage.list_pull_requests(conn, repo_id)
    return bool(rows)


def _cache_missing_response(repository: str, next_steps: list[str]) -> dict[str, Any]:
    return {
        "error": "cache_missing",
        "repository": repository,
        "next_steps": next_steps,
        "hint": (
            "the local Gitsweeper cache has no data for this repo; "
            "run the listed commands before invoking this tool"
        ),
    }
