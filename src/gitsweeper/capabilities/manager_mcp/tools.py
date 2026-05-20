"""MCP tool implementations.

Each tool is a small function that:

- declares its own input schema (next to the function, in registry.py)
- returns a JSON-serialisable dict or list
- echoes the resolved ``period`` and ``scope`` blocks where applicable
- declares units on every numeric field via ``unit`` keys, so the AI
  client cannot drop context when it re-presents numbers to the manager

Tools are read-only. The Billbird client only exposes GETs; the
Gitsweeper-side tools either reuse the existing capability functions
directly against the local SQLite cache, or refuse with a structured
error when the cache is incomplete.
"""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from gitsweeper.capabilities.manager_mcp.periods import Period, parse_period
from gitsweeper.lib.billbird_client import (
    BillbirdClient,
    BillbirdHTTPError,
    BillbirdNotConfigured,
)

# --- Error envelopes -------------------------------------------------------

ERR_NOT_CONFIGURED = "billbird_not_configured"
ERR_HTTP = "billbird_http_error"


def _not_configured_response(exc: BillbirdNotConfigured) -> dict[str, Any]:
    return {
        "error": ERR_NOT_CONFIGURED,
        "missing": exc.missing,
        "docs": "docs/mcp.md",
    }


def _http_error_response(exc: BillbirdHTTPError) -> dict[str, Any]:
    return {
        "error": ERR_HTTP,
        "status": exc.status,
        "hint": exc.hint,
        "body": exc.body,
    }


def _analysis_to_payload(result) -> dict[str, Any]:
    """Convert a Gitsweeper AnalysisResult into a JSON-serialisable dict."""
    rows = [
        dict(zip(result.columns, row, strict=True)) for row in result.rows
    ]
    return {
        "title": result.title,
        "columns": list(result.columns),
        "rows": rows,
        "metadata": dict(result.metadata or {}),
    }


# --- Billbird tools --------------------------------------------------------


def billbird_hours_summary(
    period: str,
    group_by: str,
    repository: str | None = None,
    client: str | None = None,
    user: str | None = None,
) -> dict[str, Any]:
    """Aggregate active log minutes for a period, grouped by one axis."""
    if group_by not in {"user", "client", "repo", "issue"}:
        return {
            "error": "invalid_argument",
            "field": "group_by",
            "hint": "must be one of 'user', 'client', 'repo', 'issue'",
        }
    try:
        p = parse_period(period)
    except ValueError as exc:
        return {"error": "invalid_argument", "field": "period", "hint": str(exc)}

    try:
        with BillbirdClient.from_env() as bb:
            client_id = _resolve_client_id(bb, client) if client else None
            if client and client_id is None:
                return {
                    "error": "client_not_found",
                    "client": client,
                    "hint": "exact name match; check /api/v1/clients",
                }
            entries = bb.time_entries(
                repository=repository,
                username=user,
                client_id=client_id,
                date_from=_iso_to_date(p.from_iso),
                date_to=_iso_to_date(p.until_iso),
            )
            clients = {c["id"]: c["name"] for c in bb.clients()} if group_by == "client" else {}
    except BillbirdNotConfigured as exc:
        return _not_configured_response(exc)
    except BillbirdHTTPError as exc:
        return _http_error_response(exc)

    groups = _group_minutes(entries, group_by, clients)
    return {
        "unit": "minutes",
        "period": p.to_dict(),
        "scope": {
            "repository": repository,
            "client": client,
            "user": user,
            "group_by": group_by,
        },
        "groups": groups,
        "total_minutes": sum(g["minutes"] for g in groups),
        "entry_count": len(entries),
    }


def billbird_plan_vs_actual(
    period: str | None = None,
    status: str | None = None,
    repository: str | None = None,
    client: str | None = None,
) -> dict[str, Any]:
    """List per-issue plan-vs-actual variance for the given filter."""
    p: Period | None = None
    if period:
        try:
            p = parse_period(period)
        except ValueError as exc:
            return {"error": "invalid_argument", "field": "period", "hint": str(exc)}
    if status is not None and status not in {"no_plan", "under", "on_target", "over"}:
        return {
            "error": "invalid_argument",
            "field": "status",
            "hint": "must be one of 'no_plan', 'under', 'on_target', 'over'",
        }

    try:
        with BillbirdClient.from_env() as bb:
            plans = bb.plans(
                repository=repository,
                status="active",
                since=_iso_to_date(p.from_iso) if p else None,
                until=_iso_to_date(p.until_iso) if p else None,
            )
            results: list[dict[str, Any]] = []
            for plan in plans:
                repo_full = plan.get("Repository") or plan.get("repository") or ""
                issue_num = plan.get("IssueNumber") or plan.get("issue_number")
                if not repo_full or issue_num is None:
                    continue
                owner, name = _split_repo(repo_full)
                pva = bb.plan_vs_actual(owner, name, issue_num)
                if status and pva.get("status") != status:
                    continue
                results.append(
                    {
                        "repository": pva.get("repository"),
                        "issue_number": pva.get("issue_number"),
                        "planned_minutes": pva.get("planned_minutes", 0),
                        "logged_minutes": pva.get("logged_minutes", 0),
                        "variance_minutes": pva.get("variance_minutes", 0),
                        "status": pva.get("status", "no_plan"),
                    }
                )
            # Lead with the issues that need attention.
            results.sort(key=lambda r: abs(r["variance_minutes"]), reverse=True)
    except BillbirdNotConfigured as exc:
        return _not_configured_response(exc)
    except BillbirdHTTPError as exc:
        return _http_error_response(exc)

    return {
        "unit": "minutes",
        "period": p.to_dict() if p else None,
        "scope": {"repository": repository, "client": client, "status": status},
        "issues": results,
        "count": len(results),
    }


def billbird_cycle_time(
    period: str | None = None, repository: str | None = None
) -> dict[str, Any]:
    """Cycle-time API is not yet exposed by Billbird; this returns a
    structured 'not implemented' response so the MCP client knows to
    re-run later rather than failing silently."""
    _ = period, repository
    return {
        "error": "not_implemented",
        "hint": (
            "Billbird's cycle-time REST endpoint is not exposed yet. "
            "Once /api/v1/cycle-time lands, this tool will return per-issue "
            "and aggregate records."
        ),
    }


def billbird_recent_activity(since: str, limit: int = 50) -> dict[str, Any]:
    """Return recent log + plan entries (combined, type-tagged) since
    a timestamp. Useful for the 'what happened yesterday' question."""
    try:
        with BillbirdClient.from_env() as bb:
            since_date = since[:10] if len(since) >= 10 else since
            entries = bb.time_entries(date_from=since_date)
            plans = bb.plans(since=since_date)
    except BillbirdNotConfigured as exc:
        return _not_configured_response(exc)
    except BillbirdHTTPError as exc:
        return _http_error_response(exc)

    combined: list[dict[str, Any]] = []
    for e in entries:
        combined.append(_normalise_activity(e, "log"))
    for p in plans:
        combined.append(_normalise_activity(p, "plan"))
    combined.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return {
        "unit": "minutes",
        "since": since,
        "limit": limit,
        "entries": combined[:limit],
        "count": min(len(combined), limit),
    }


def _normalise_activity(row: dict[str, Any], kind: str) -> dict[str, Any]:
    return {
        "type": kind,
        "id": row.get("ID") or row.get("id"),
        "created_at": row.get("CreatedAt") or row.get("created_at"),
        "repository": row.get("Repository") or row.get("repository"),
        "issue_number": row.get("IssueNumber") or row.get("issue_number"),
        "duration_minutes": row.get("DurationMinutes") or row.get("duration_minutes"),
        "github_username": row.get("GitHubUsername") or row.get("github_username"),
        "description": row.get("Description") or row.get("description"),
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
            int(r["pr_id"]): r
            for r in storage.list_first_responses(conn, repo_id)
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


# --- Composite tool --------------------------------------------------------


def team_status_report(period: str, scope: dict[str, Any] | None = None) -> dict[str, Any]:
    """Composite report combining hours summary, plan-vs-actual, and PR analyses.

    Returns both a ``data`` block (every input the report drew from)
    and a ``markdown`` block (the same content rendered as a single
    document the manager can paste into Slack or save to disk).

    Short-circuits on missing Billbird config *before* any Gitsweeper
    work runs, so the manager sees one error instead of a partial
    report.
    """
    scope = dict(scope or {})
    try:
        p = parse_period(period)
    except ValueError as exc:
        return {"error": "invalid_argument", "field": "period", "hint": str(exc)}

    try:
        with BillbirdClient.from_env():
            pass
    except BillbirdNotConfigured as exc:
        return _not_configured_response(exc)

    data: dict[str, Any] = {
        "period": p.to_dict(),
        "scope": scope,
    }

    repo = scope.get("repo") or scope.get("repository")
    client = scope.get("client")
    author = scope.get("author")

    data["hours_summary"] = billbird_hours_summary(
        period=period,
        group_by=scope.get("hours_group_by", "user"),
        repository=repo,
        client=client,
        user=author,
    )
    data["plan_vs_actual"] = billbird_plan_vs_actual(
        period=period,
        repository=repo,
        client=client,
    )

    if repo:
        since = _iso_to_date(p.from_iso)
        data["pr_throughput"] = gitsweeper_pr_throughput(repo, since=since, author=author)
        data["first_response"] = gitsweeper_first_response(repo, since=since, author=author)
        data["classify"] = gitsweeper_classify(repo, author=author)
        data["patterns"] = gitsweeper_patterns(repo, since=since, author=author)
    else:
        skip = {"skipped": "no repository in scope"}
        data["pr_throughput"] = dict(skip)
        data["first_response"] = dict(skip)
        data["classify"] = dict(skip)
        data["patterns"] = dict(skip)

    return {
        "data": data,
        "markdown": _render_markdown(p, scope, data),
    }


# --- Internal helpers -------------------------------------------------------


class _DisabledClient:
    """Stand-in for the GitHubClient used by compute_first_response.

    Raises on any call, which is the right thing: the MCP layer has
    already verified that the function will not need to fetch anything.
    """

    def list_issue_comments(self, *args, **kwargs):  # noqa: D401 - mirrors GitHubClient
        raise RuntimeError(
            "MCP layer must not fetch; cache should already be complete"
        )


def _split_repo(spec: str) -> tuple[str, str]:
    owner, _, name = spec.partition("/")
    if not owner or not name:
        raise ValueError(f"invalid repository spec {spec!r}; expected owner/repo")
    return owner, name


def _iso_to_date(iso: str | None) -> str:
    return iso[:10] if iso else ""


def _open_local_db():
    """Open the Gitsweeper SQLite cache the same way the CLI does."""
    from gitsweeper.lib import storage

    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    path = Path(base) / "gitsweeper" / "gitsweeper.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = storage.connect(path)
    storage.init_schema(conn)
    return conn


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


def _resolve_client_id(bb: BillbirdClient, name: str) -> int | None:
    for c in bb.clients():
        if c.get("name") == name:
            return c.get("id")
    return None


def _group_minutes(
    entries: Iterable[dict[str, Any]],
    group_by: str,
    clients: dict[int, str],
) -> list[dict[str, Any]]:
    totals: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    for e in entries:
        if group_by == "user":
            key = e.get("GitHubUsername") or e.get("github_username") or "unknown"
        elif group_by == "client":
            cid = e.get("ClientID") or e.get("client_id")
            key = clients.get(cid, "(no client)") if cid else "(no client)"
        elif group_by == "repo":
            key = e.get("Repository") or e.get("repository") or "unknown"
        elif group_by == "issue":
            repo = e.get("Repository") or e.get("repository") or "unknown"
            issue = e.get("IssueNumber") or e.get("issue_number")
            key = f"{repo}#{issue}"
        else:
            key = "unknown"
        minutes = e.get("DurationMinutes") or e.get("duration_minutes") or 0
        totals[key] += minutes
        counts[key] += 1
    rows = [
        {"group": key, "minutes": totals[key], "entries": counts[key]}
        for key in totals
    ]
    rows.sort(key=lambda r: r["minutes"], reverse=True)
    return rows


def _render_markdown(p: Period, scope: dict[str, Any], data: dict[str, Any]) -> str:
    scope_label = ", ".join(f"{k}={v}" for k, v in scope.items() if v) or "(none)"
    lines: list[str] = [
        "# Team status report",
        "",
        f"- Period: `{p.label}` ({p.from_iso} → {p.until_iso})",
        f"- Scope: {scope_label}",
        "",
    ]

    lines.append("## Hours logged")
    hours = data.get("hours_summary", {})
    if hours.get("error"):
        lines.append(_render_error(hours))
    else:
        lines.append(
            f"- Total: **{_minutes_to_hours(hours.get('total_minutes', 0))}** "
            f"({hours.get('entry_count', 0)} entries)"
        )
        groups = hours.get("groups", [])
        if groups:
            lines.append(f"- Top groups (by {hours['scope']['group_by']}):")
            for row in groups[:10]:
                lines.append(f"  - `{row['group']}` — {_minutes_to_hours(row['minutes'])}")
    lines.append("")

    lines.append("## Plan vs actual")
    pva = data.get("plan_vs_actual", {})
    if pva.get("error"):
        lines.append(_render_error(pva))
    else:
        issues = pva.get("issues", [])
        lines.append(f"- {len(issues)} issues with an active plan in scope.")
        for row in issues[:10]:
            lines.append(
                f"  - {row['repository']}#{row['issue_number']} — "
                f"planned **{_minutes_to_hours(row['planned_minutes'])}**, "
                f"logged **{_minutes_to_hours(row['logged_minutes'])}**, "
                f"variance `{row['variance_minutes']:+d}m` "
                f"(*{row['status']}*)"
            )
    lines.append("")

    for label, key in [
        ("PR throughput", "pr_throughput"),
        ("First-response latency", "first_response"),
        ("Classification", "classify"),
        ("Patterns", "patterns"),
    ]:
        section = data.get(key, {})
        lines.append(f"## {label}")
        if section.get("skipped"):
            lines.append(f"- _Skipped: {section['skipped']}_")
        elif section.get("error"):
            lines.append(_render_error(section))
        else:
            lines.append(f"- _{section.get('title', '')}_")
            for row in (section.get("rows") or [])[:10]:
                lines.append(f"  - {row}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _minutes_to_hours(minutes: int) -> str:
    if minutes >= 60:
        h, m = divmod(minutes, 60)
        return f"{h}h{m}m" if m else f"{h}h"
    return f"{minutes}m"


def _render_error(obj: dict[str, Any]) -> str:
    err = obj.get("error")
    if err == ERR_NOT_CONFIGURED:
        return f"- _Error: {err}, missing {obj.get('missing')} — see {obj.get('docs')}_"
    if err == ERR_HTTP:
        return f"- _Error: Billbird HTTP {obj.get('status')} ({obj.get('hint')})_"
    return f"- _Error: {err} — {obj.get('hint', obj.get('next_step', ''))}_"
