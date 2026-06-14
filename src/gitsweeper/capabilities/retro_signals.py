"""Retro signals computed from cached PRs and a local comments cache.

Forge-agnostic and deterministic: every signal is derived from the locally
cached pull requests plus the `pr_comments` cache with no LLM and no scoring
model. The cues mirror the team-retro half of `Road_to_el_DORA-do` — stale
open PRs, long discussion threads, friction language, tech-debt markers, and
smooth merges — translated from Road's GitHub-Project issue threads onto
gitsweeper's PR-centric cache.

Every signal is reported at team level: each references a PR by number (and,
for the keyword signals, a match count) and never surfaces a comment author or
PR author, even though the cache stores comment authors for possible future
use. "Speel op de bal, niet op de mens", encoded so it cannot regress.

The keyword sets below are carried verbatim from
``Road_to_el_DORA-do/.github/prompts/sprint-retro.md`` so this capability is
continuous with the workflow it supersedes. They are documented module
constants — one per list — so they are auditable and adjustable in one place.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from gitsweeper.capabilities._pr_fields import (
    days_between as _days_between,
)
from gitsweeper.capabilities._pr_fields import (
    parse_iso as _parse_iso,
)
from gitsweeper.capabilities._pr_fields import (
    title_of as _title_of,
)
from gitsweeper.lib import storage
from gitsweeper.lib.forge import ForgeProvider
from gitsweeper.lib.rendering import AnalysisResult

# --- keyword sets (locked, verbatim from Road's sprint-retro prompt) --------
#
# Case-insensitive whole-phrase matches counted over each PR's comment bodies
# plus its title. Friction is bilingual (Dutch + English) as Road had it.

FRICTION_KEYWORDS_NL: tuple[str, ...] = (
    "loopt vast",
    "wacht op",
    "onduidelijk",
    "blokkeert",
    "geen idee",
    "frustrerend",
    "lastig",
)

FRICTION_KEYWORDS_EN: tuple[str, ...] = (
    "blocked",
    "stuck",
    "waiting on",
    "unclear",
    "no idea",
    "frustrating",
)

TECH_DEBT_KEYWORDS: tuple[str, ...] = (
    "hack",
    "workaround",
    "todo",
    "fixme",
    "wtf",
    "ugly",
    "tijdelijk",
    "quick fix",
)

# --- thresholds (documented, adjustable) ------------------------------------
#
# stale-open  = open PR whose created_at is older than STALE_DAYS (the
#               --stale-days default) — the PR-cache analogue of sprint
#               spillover.
# long-thread = a PR with strictly more than LONG_THREAD cached comments
#               (Road's number).
# smooth      = merged within SMOOTH_MAX_DAYS with strictly fewer than
#               SMOOTH_MAX_COMMENTS comments — the positive counterpart.
STALE_DAYS: int = 14
LONG_THREAD: int = 10
SMOOTH_MAX_DAYS: float = 3.0
SMOOTH_MAX_COMMENTS: int = 2


# --- report model -----------------------------------------------------------


@dataclass(frozen=True)
class RetroReport:
    """Team-level retro signals over a scoped PR population.

    Every field references PRs by number only. ``friction`` and ``tech_debt``
    carry ``(number, count)`` pairs (highest count first); the others carry
    plain PR numbers. ``tech_debt_total`` is the total marker count across the
    population. An empty population yields empty lists / zero — no error.
    """

    repo: str
    since: str | None
    stale_days: int
    prs_considered: int
    stale_open: list[int]
    long_threads: list[tuple[int, int]]
    friction: list[tuple[int, int]]
    tech_debt: list[tuple[int, int]]
    tech_debt_total: int
    smooth: list[int]


# --- keyword matching -------------------------------------------------------


def count_matches(text: str, keywords: Iterable[str]) -> int:
    """Count case-insensitive whole-phrase occurrences of ``keywords`` in ``text``.

    Each keyword is counted by non-overlapping word-boundary matches, so single
    words match only as whole words ("hack" does not fire on "hackathon") while
    multi-word phrases like "waiting on" and "loopt vast" still match across the
    space exactly as written. Deterministic and reproducible from the text alone
    — no network, no LLM.
    """
    total = 0
    for keyword in keywords:
        pattern = r"\b" + re.escape(keyword) + r"\b"
        total += len(re.findall(pattern, text, re.IGNORECASE))
    return total


FRICTION_KEYWORDS: tuple[str, ...] = FRICTION_KEYWORDS_NL + FRICTION_KEYWORDS_EN


# --- pure computation -------------------------------------------------------


def build_report(
    pr_rows: list[sqlite3.Row],
    comment_rows: list[sqlite3.Row],
    *,
    repo: str,
    since: str | None,
    stale_days: int,
    now: datetime | None = None,
) -> RetroReport:
    """Compute the retro signals over cached PR rows + cached comment rows.

    ``pr_rows`` is the storage-shaped pull-request list (``number``, ``state``,
    ``created_at``, ``merged_at``, ``raw_payload``). ``comment_rows`` is the
    ``list_comments`` shape (``number``, ``author``, ``created_at``, ``body``).
    ``now`` defaults to the current UTC time; passing it makes staleness tests
    deterministic. An empty population yields an empty report, not an error.
    """
    when = now or datetime.now(UTC)

    # Comment bodies and counts grouped per PR number.
    bodies_by_pr: dict[int, list[str]] = {}
    count_by_pr: dict[int, int] = {}
    for c in comment_rows:
        number = int(c["number"])
        bodies_by_pr.setdefault(number, []).append(c["body"] or "")
        count_by_pr[number] = count_by_pr.get(number, 0) + 1

    stale_open: list[int] = []
    long_threads: list[tuple[int, int]] = []
    friction: list[tuple[int, int]] = []
    tech_debt: list[tuple[int, int]] = []
    tech_debt_total = 0
    smooth: list[int] = []

    for pr in pr_rows:
        number = int(pr["number"])
        title = _title_of(pr["raw_payload"])
        comment_count = count_by_pr.get(number, 0)

        # stale open: open + created_at older than the threshold.
        if pr["state"] == "open" and pr["merged_at"] is None:
            age_days = (when - _parse_iso(pr["created_at"])).total_seconds() / 86400.0
            if age_days > stale_days:
                stale_open.append(number)

        # long thread: more than LONG_THREAD cached comments.
        if comment_count > LONG_THREAD:
            long_threads.append((number, comment_count))

        # keyword scans over the PR title plus every cached comment body.
        searchable = "\n".join([title, *bodies_by_pr.get(number, [])])
        friction_hits = count_matches(searchable, FRICTION_KEYWORDS)
        if friction_hits:
            friction.append((number, friction_hits))
        debt_hits = count_matches(searchable, TECH_DEBT_KEYWORDS)
        if debt_hits:
            tech_debt.append((number, debt_hits))
            tech_debt_total += debt_hits

        # smooth: merged within the window with few comments.
        if pr["merged_at"] is not None:
            cycle_days = _days_between(pr["created_at"], pr["merged_at"])
            if cycle_days <= SMOOTH_MAX_DAYS and comment_count < SMOOTH_MAX_COMMENTS:
                smooth.append(number)

    # long threads + keyword signals: highest count first, then by number.
    long_threads.sort(key=lambda pair: (-pair[1], pair[0]))
    friction.sort(key=lambda pair: (-pair[1], pair[0]))
    tech_debt.sort(key=lambda pair: (-pair[1], pair[0]))

    return RetroReport(
        repo=repo,
        since=since,
        stale_days=stale_days,
        prs_considered=len(pr_rows),
        stale_open=stale_open,
        long_threads=long_threads,
        friction=friction,
        tech_debt=tech_debt,
        tech_debt_total=tech_debt_total,
        smooth=smooth,
    )


# --- fetch + persist + render -----------------------------------------------


def fetch_and_cache_comments(
    conn: sqlite3.Connection,
    client: ForgeProvider,
    repo_id: int,
    owner: str,
    name: str,
    *,
    since: str | None = None,
) -> int:
    """Populate the comments cache for every in-scope PR not already fetched.

    Mirrors the first-response fetch loop: one comment-listing call per PR,
    skipped when the PR's comments were already fetched so a re-run does not
    re-fetch — including PRs that turned out to have zero comments, which are
    recorded via a fetched-marker rather than by the presence of comment rows.
    Returns the number of PRs fetched this call.
    """
    pr_rows = _scoped_pr_rows(conn, repo_id, since)
    already = storage.list_prs_comments_fetched(conn, repo_id)
    fetched = 0
    for pr in pr_rows:
        pr_id = int(pr["id"])
        if pr_id in already:
            continue
        comments = list(client.list_issue_comments(owner, name, int(pr["number"])))
        storage.upsert_comments(conn, pr_id, comments)
        storage.mark_comments_fetched(conn, pr_id)
        fetched += 1
    return fetched


def _scoped_pr_rows(
    conn: sqlite3.Connection, repo_id: int, since: str | None
) -> list[sqlite3.Row]:
    """All cached PRs for a repo, scoped by created_at >= since when given.

    ``retro`` measures open-PR age and discussion, so it scopes on PR creation
    (not merge date like throughput/dora) — stale and long-thread signals are
    about when work started, not when it landed.
    """
    rows = storage.list_pull_requests(conn, repo_id)
    if since is not None:
        rows = [r for r in rows if r["created_at"] >= since]
    return rows


def compute_retro_signals(
    conn: sqlite3.Connection,
    client: ForgeProvider,
    repo_id: int,
    owner: str,
    name: str,
    *,
    since: str | None = None,
    stale_days: int = STALE_DAYS,
) -> AnalysisResult:
    """Fetch+cache comments for the in-scope PRs, then render the retro report.

    `since` must already be an ISO 8601 string (validate user input with
    ``pr_throughput.parse_since`` first). The result is team-level: it carries
    no author field.
    """
    fetch_and_cache_comments(conn, client, repo_id, owner, name, since=since)
    pr_rows = _scoped_pr_rows(conn, repo_id, since)
    comment_rows = storage.list_comments(conn, repo_id)
    report = build_report(
        pr_rows,
        comment_rows,
        repo=f"{owner}/{name}",
        since=since,
        stale_days=stale_days,
    )
    return _result_from_report(report)


_EMPTY = "(none)"


def _result_from_report(report: RetroReport) -> AnalysisResult:
    """Shape a RetroReport into the renderer's AnalysisResult.

    One row group per signal: column ``signal`` names the cue, ``pr`` is the
    PR number (or ``None`` for an explicit-empty row), and ``detail`` carries
    the per-row count / note. Each signal emits at least one row so an empty
    signal is reported explicitly rather than vanishing. Carries no author
    field — retro is team-level only.
    """
    rows: list[list] = []

    def _emit(signal: str, entries: list[tuple[int, str]]) -> None:
        if not entries:
            rows.append([signal, None, _EMPTY])
            return
        for number, detail in entries:
            rows.append([signal, number, detail])

    _emit("stale_open", [(n, "open > threshold") for n in report.stale_open])
    _emit(
        "long_thread",
        [(n, f"{count} comments") for n, count in report.long_threads],
    )
    _emit(
        "friction",
        [(n, f"{count} matches") for n, count in report.friction],
    )
    _emit(
        "tech_debt",
        [(n, f"{count} markers") for n, count in report.tech_debt],
    )
    _emit("smooth", [(n, "fast, low-friction merge") for n in report.smooth])

    metadata: dict = {
        "repo": report.repo,
        "since": report.since,
        "stale_days": report.stale_days,
        "long_thread_threshold": LONG_THREAD,
        "smooth_window_days": SMOOTH_MAX_DAYS,
        "prs_considered": report.prs_considered,
        "tech_debt_total": report.tech_debt_total,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if report.prs_considered == 0:
        metadata["note"] = "empty population: no PRs in the scoped window"
    return AnalysisResult(
        title=f"retro signals for {report.repo} (team-level)",
        columns=["signal", "pr", "detail"],
        rows=rows,
        metadata=metadata,
    )


__all__ = [
    "FRICTION_KEYWORDS",
    "FRICTION_KEYWORDS_EN",
    "FRICTION_KEYWORDS_NL",
    "LONG_THREAD",
    "SMOOTH_MAX_COMMENTS",
    "SMOOTH_MAX_DAYS",
    "STALE_DAYS",
    "TECH_DEBT_KEYWORDS",
    "RetroReport",
    "build_report",
    "compute_retro_signals",
    "count_matches",
    "fetch_and_cache_comments",
]
