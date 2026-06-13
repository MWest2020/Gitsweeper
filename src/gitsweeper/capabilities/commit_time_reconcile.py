"""Reconcile commit ``Time:`` footers against Billbird ``/log`` entries.

Pure read-only: pulls both sides, aggregates per
``(repo, author, issue)``, computes drift, classifies. No persistence
of the commit data (we re-fetch on each run; caching is a future
follow-up once a scale wall actually shows up).

The classifier rule:

- ``aligned`` when ``|drift| <= max(15min, 10% of commit_minutes)``
- ``commits_only`` when commits > 0 and logs == 0
- ``logs_only`` when logs > 0 and commits == 0
- ``over_committed`` when commits - logs exceeds tolerance
- ``over_logged`` when logs - commits exceeds tolerance

The two tolerance halves matter: small commits (a 10-minute typo
fix) can drift 5 minutes without that being a sign of anything; large
commits (a 4-hour session) should align within ~24 minutes.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from billbird_client import (
    BillbirdClient,
    BillbirdHTTPError,
    BillbirdNotConfigured,
)

from gitsweeper.lib.commit_time import parse_issue_refs, parse_time_footer
from gitsweeper.lib.forge import ForgeProvider, get_forge_provider
from gitsweeper.lib.forge.base import ForgeCommit
from gitsweeper.lib.rendering import AnalysisResult

MIN_TOLERANCE_MINUTES = 15


@dataclass(frozen=True)
class _Key:
    """One bucket the reconciler aggregates into.

    ``issue`` is ``None`` for commits without a same-repo issue
    reference; those still get grouped per author so the gap remains
    visible.
    """

    repo: str
    author: str
    issue: int | None


def classify(commit_minutes: int, logged_minutes: int) -> str:
    if commit_minutes == 0 and logged_minutes == 0:
        # An empty bucket never reaches the result rows in practice,
        # but kept here so the function is total.
        return "aligned"
    if commit_minutes == 0:
        return "logs_only"
    if logged_minutes == 0:
        return "commits_only"
    diff = logged_minutes - commit_minutes
    tolerance = max(MIN_TOLERANCE_MINUTES, commit_minutes // 10)
    if abs(diff) <= tolerance:
        return "aligned"
    return "over_logged" if diff > 0 else "over_committed"


def _author_of(commit: ForgeCommit) -> str:
    """Best-effort author identifier: forge login if known, else the
    name in the commit metadata, else "unknown". We use one canonical
    string so commits and logs end up in the same bucket."""
    if commit.author:
        return commit.author
    if commit.author_name:
        return commit.author_name
    return "unknown"


def _aggregate_commits(
    commits: Iterable[ForgeCommit], repo: str
) -> dict[_Key, int]:
    """Walk commits, parse footers + issue refs, bucket per
    ``(repo, author, issue)``. Commits without a footer are skipped
    silently (they're not opinions about time)."""
    buckets: dict[_Key, int] = defaultdict(int)
    for commit in commits:
        message = commit.message
        minutes = parse_time_footer(message)
        if minutes is None:
            continue
        author = _author_of(commit)
        refs = parse_issue_refs(message)
        if not refs:
            buckets[_Key(repo=repo, author=author, issue=None)] += minutes
            continue
        # When a commit references multiple issues, the convention is
        # that the footer time is attributed to all of them. Until we
        # have a sharper signal, we count the full duration against
        # each — the manager can ratio it down at read time. (This is
        # the same pragmatic choice GitHub itself makes for the issue
        # closing references.)
        for issue in refs:
            buckets[_Key(repo=repo, author=author, issue=issue)] += minutes
    return buckets


def _aggregate_logs(
    entries: Iterable[dict[str, Any]], repo: str
) -> dict[_Key, int]:
    """Same shape, for Billbird's time-entries payload."""
    buckets: dict[_Key, int] = defaultdict(int)
    for entry in entries:
        if (entry.get("Status") or entry.get("status")) not in ("active", None):
            # Skip non-active rows; only "active" counts toward billed totals.
            continue
        author = entry.get("GitHubUsername") or entry.get("github_username") or "unknown"
        issue = entry.get("IssueNumber") or entry.get("issue_number")
        minutes = entry.get("DurationMinutes") or entry.get("duration_minutes") or 0
        buckets[_Key(repo=repo, author=author, issue=issue)] += minutes
    return buckets


def _sort_rows(rows: list[list[Any]]) -> list[list[Any]]:
    """Lead with the rows that need attention. Drift descending by
    absolute value, then the issue number ascending for stable
    output across runs."""

    def key(r: list[Any]) -> tuple[int, int]:
        drift = r[5]
        issue = r[2] if r[2] is not None else 10**9
        return (-abs(drift), issue)

    return sorted(rows, key=key)


def reconcile(
    *,
    github: ForgeProvider,
    billbird: BillbirdClient,
    owner: str,
    name: str,
    since: str | None = None,
    branch: str | None = None,
    author: str | None = None,
) -> AnalysisResult:
    """End-to-end reconciliation.

    Caller owns the ``GitHubClient`` and ``BillbirdClient`` lifecycles;
    we just read from them. ``since`` is an ISO 8601 timestamp; the
    Billbird side accepts only YYYY-MM-DD, so we truncate as needed.
    """
    repo = f"{owner}/{name}"
    commits = list(github.list_commits(owner, name, since=since, sha=branch))
    commit_buckets = _aggregate_commits(commits, repo)

    log_buckets = _aggregate_logs(
        billbird.time_entries(
            repository=repo,
            username=author,
            date_from=since[:10] if since else None,
        ),
        repo,
    )

    every_key = set(commit_buckets) | set(log_buckets)
    rows: list[list[Any]] = []
    for k in every_key:
        if author and k.author != author:
            continue
        cm = commit_buckets.get(k, 0)
        lm = log_buckets.get(k, 0)
        rows.append(
            [
                k.repo,
                k.author,
                k.issue,
                cm,
                lm,
                lm - cm,
                classify(cm, lm),
            ]
        )

    rows = _sort_rows(rows)

    title_scope = f" since {since}" if since else ""
    if branch:
        title_scope += f" on {branch}"
    return AnalysisResult(
        title=f"reconcile commits vs /log for {repo}{title_scope}",
        columns=[
            "repo",
            "author",
            "issue",
            "commit_minutes",
            "log_minutes",
            "drift_minutes",
            "status",
        ],
        rows=rows,
        metadata={
            "repo": repo,
            "since": since,
            "branch": branch,
            "author_filter": author,
            "unit": "minutes",
            "commit_total_minutes": sum(commit_buckets.values()),
            "log_total_minutes": sum(log_buckets.values()),
            "status_legend": {
                "aligned": "commit and log within tolerance",
                "commits_only": "commit footer exists, no /log",
                "logs_only": "/log exists, no commit footer",
                "over_committed": "commit footer larger than /log beyond tolerance",
                "over_logged": "/log larger than commit footer beyond tolerance",
            },
        },
    )


def reconcile_from_env(
    *,
    owner: str,
    name: str,
    since: str | None = None,
    branch: str | None = None,
    author: str | None = None,
) -> AnalysisResult:
    """Convenience wrapper that constructs both clients from env vars
    (``GITHUB_TOKEN``, ``BILLBIRD_API_URL``, ``BILLBIRD_API_TOKEN``)
    and closes them when the call finishes.

    Raises :class:`BillbirdNotConfigured` when the Billbird env vars
    are missing. Lets ``BillbirdHTTPError`` propagate so callers see
    auth/server problems verbatim.
    """
    with get_forge_provider() as github, BillbirdClient.from_env() as billbird:
        return reconcile(
            github=github,
            billbird=billbird,
            owner=owner,
            name=name,
            since=since,
            branch=branch,
            author=author,
        )


# Re-export for caller convenience.
__all__ = [
    "BillbirdHTTPError",
    "BillbirdNotConfigured",
    "classify",
    "reconcile",
    "reconcile_from_env",
]
