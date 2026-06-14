from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gitsweeper.capabilities import retro_signals
from gitsweeper.cli import app
from gitsweeper.lib import storage
from gitsweeper.lib.forge.base import ForgeComment, ForgePullRequest

NOW = datetime(2026, 6, 14, tzinfo=UTC)


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
    state: str | None = None,
    title: str | None = None,
    author: str = "alice",
) -> ForgePullRequest:
    resolved_state = state if state is not None else ("closed" if merged else "open")
    return ForgePullRequest(
        number=number,
        state=resolved_state,
        created_at=created,
        merged_at=merged,
        closed_at=merged,
        author=author,
        raw={
            "number": number,
            "title": title if title is not None else f"PR #{number}",
            "user": {"login": author},
        },
    )


def _row(
    number: int,
    *,
    created: str,
    merged: str | None = None,
    state: str | None = None,
    title: str | None = None,
) -> dict:
    """A pull_requests storage-row-shaped dict (build_report input)."""
    resolved_state = state if state is not None else ("merged" if merged else "open")
    return {
        "number": number,
        "state": resolved_state,
        "created_at": created,
        "merged_at": merged,
        "raw_payload": json.dumps(
            {"number": number, "title": title if title is not None else f"PR #{number}"}
        ),
    }


def _c(number: int, *, author: str = "bob", created: str = "2026-01-01T00:00:00Z",
       body: str = "") -> dict:
    """A comment_rows-shaped dict (list_comments output)."""
    return {"number": number, "author": author, "created_at": created, "body": body}


def _build(prs, comments, *, since=None, stale_days=retro_signals.STALE_DAYS):
    return retro_signals.build_report(
        prs, comments, repo="o/r", since=since, stale_days=stale_days, now=NOW
    )


# ---- keyword matching: bilingual + tech-debt ------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "dit loopt vast op de review",   # NL
        "we are blocked on infra",       # EN
        "still waiting on the API team",  # EN multi-word
        "BLOCKED in caps",               # case-insensitive
        "geen idee waarom",              # NL multi-word
    ],
)
def test_friction_positive(text: str) -> None:
    assert retro_signals.count_matches(text, retro_signals.FRICTION_KEYWORDS) >= 1


@pytest.mark.parametrize(
    "text",
    ["looks good to me", "shipping this now", "great work", ""],
)
def test_friction_negative(text: str) -> None:
    assert retro_signals.count_matches(text, retro_signals.FRICTION_KEYWORDS) == 0


def test_tech_debt_matching() -> None:
    text = "this is a hack, TODO clean up the tijdelijk workaround"
    assert retro_signals.count_matches(text, retro_signals.TECH_DEBT_KEYWORDS) == 4
    assert retro_signals.count_matches("ship it", retro_signals.TECH_DEBT_KEYWORDS) == 0


def test_count_matches_is_whole_word_only() -> None:
    # Single-word keywords must match on word boundaries, not raw substrings.
    assert retro_signals.count_matches("the hackathon was fun", ("hack",)) == 0
    assert retro_signals.count_matches("merged all the todos", ("todo",)) == 0
    assert retro_signals.count_matches("she was starstruck", ("stuck",)) == 0
    # The whole word still matches, including with adjacent punctuation/case.
    assert retro_signals.count_matches("TODO: fix this", ("todo",)) == 1
    assert retro_signals.count_matches("it is a hack", ("hack",)) == 1


def test_count_matches_multiword_and_case_insensitive() -> None:
    # Multi-word phrases still match across the space via the \b...\b boundaries.
    assert retro_signals.count_matches("just a quick fix", ("quick fix",)) == 1
    assert retro_signals.count_matches("still WAITING ON the API", ("waiting on",)) == 1
    # Case-insensitive on both sides.
    assert retro_signals.count_matches("a HACK indeed", ("hack",)) == 1


# ---- friction ranked over titles + bodies ---------------------------------


def test_friction_ranked_by_count(conn: sqlite3.Connection) -> None:
    prs = [
        _row(1, created="2026-06-01T00:00:00Z", title="blocked and stuck"),  # 2 in title
        _row(2, created="2026-06-01T00:00:00Z", title="normal"),
    ]
    comments = [
        _c(2, body="waiting on review"),  # 1 in body
    ]
    report = _build(prs, comments)
    assert report.friction == [(1, 2), (2, 1)]


def test_tech_debt_total_and_prs(conn: sqlite3.Connection) -> None:
    prs = [
        _row(1, created="2026-06-01T00:00:00Z", title="quick fix"),
        _row(2, created="2026-06-01T00:00:00Z", title="feature"),
    ]
    comments = [_c(2, body="fixme this hack")]
    report = _build(prs, comments)
    assert report.tech_debt == [(2, 2), (1, 1)]
    assert report.tech_debt_total == 3


# ---- stale open at boundary -----------------------------------------------


def test_stale_open_threshold(conn: sqlite3.Connection) -> None:
    prs = [
        _row(1, created="2026-05-01T00:00:00Z"),                       # ~44d open: stale
        _row(2, created="2026-06-13T00:00:00Z"),                       # 1d open: fresh
        _row(3, created="2026-01-01T00:00:00Z", merged="2026-01-02T00:00:00Z"),  # merged: never
    ]
    report = _build(prs, [], stale_days=14)
    assert report.stale_open == [1]


def test_stale_open_exact_boundary_excluded(conn: sqlite3.Connection) -> None:
    # created exactly stale_days ago → age == threshold → NOT older than → excluded
    created = "2026-05-31T00:00:00Z"  # 14 days before NOW
    report = _build([_row(1, created=created, state="open")], [], stale_days=14)
    assert report.stale_open == []


# ---- long thread at boundary ----------------------------------------------


def test_long_thread_threshold(conn: sqlite3.Connection) -> None:
    prs = [
        _row(1, created="2026-06-01T00:00:00Z"),
        _row(2, created="2026-06-01T00:00:00Z"),
    ]
    comments = [_c(1, created=f"2026-01-01T00:{i:02d}:00Z") for i in range(11)]  # 11 > 10
    comments += [_c(2, created=f"2026-02-01T00:{i:02d}:00Z") for i in range(10)]  # 10 = 10
    report = _build(prs, comments)
    assert report.long_threads == [(1, 11)]


# ---- smooth merges --------------------------------------------------------


def test_smooth_merges(conn: sqlite3.Connection) -> None:
    prs = [
        _row(1, created="2026-06-01T00:00:00Z", merged="2026-06-02T00:00:00Z"),  # 1d, 0 comments
        _row(2, created="2026-06-01T00:00:00Z", merged="2026-06-10T00:00:00Z"),  # 9d: too slow
        _row(3, created="2026-06-01T00:00:00Z", merged="2026-06-02T00:00:00Z"),  # 1d but 2 comments
    ]
    comments = [_c(3, created="2026-06-01T00:01:00Z"), _c(3, created="2026-06-01T00:02:00Z")]
    report = _build(prs, comments)
    assert report.smooth == [1]


# ---- empty population -----------------------------------------------------


def test_empty_population_explicit(conn: sqlite3.Connection) -> None:
    report = _build([], [])
    assert report.stale_open == []
    assert report.long_threads == []
    assert report.friction == []
    assert report.tech_debt == []
    assert report.smooth == []
    result = retro_signals._result_from_report(report)
    by_signal = {}
    for row in result.rows:
        by_signal.setdefault(row[0], []).append(row)
    # Each signal still emits exactly one explicit-empty row.
    for signal in ("stale_open", "long_thread", "friction", "tech_debt", "smooth"):
        assert len(by_signal[signal]) == 1
        assert by_signal[signal][0][1] is None
    assert "empty population" in result.metadata["note"]


# ---- team-level: no author anywhere in the rendered output ----------------


def test_no_author_in_result(conn: sqlite3.Connection) -> None:
    prs = [
        _row(1, created="2026-06-01T00:00:00Z", title="blocked"),
    ]
    comments = [_c(1, author="bob", body="waiting on carol, this is a hack")]
    report = _build(prs, comments)
    result = retro_signals._result_from_report(report)
    assert "author" not in result.columns
    assert "author" not in result.metadata
    blob = json.dumps({"columns": result.columns, "rows": result.rows,
                       "metadata": result.metadata})
    assert "alice" not in blob
    assert "bob" not in blob
    # "carol" appears only in a comment body, which is never surfaced.
    assert "carol" not in blob
    assert "author" not in blob


def test_cli_retro_options(conn: sqlite3.Connection) -> None:
    runner = CliRunner()
    res = runner.invoke(app, ["retro", "--help"])
    assert res.exit_code == 0
    assert "--forge" in res.output
    assert "--since" in res.output
    assert "--stale-days" in res.output
    assert "--json" in res.output
    assert "--author" not in res.output


# ---- forge-agnostic: ForgeComment classifies identically ------------------


class _FakeProvider:
    """Minimal ForgeProvider returning canned comments per PR number."""

    def __init__(self, comments_by_number: dict[int, list[ForgeComment]]):
        self._by_number = comments_by_number
        self.calls: list[int] = []

    def list_issue_comments(self, owner, repo, issue_number):
        self.calls.append(issue_number)
        return iter(self._by_number.get(issue_number, []))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


def test_forge_agnostic_comment_classification(conn: sqlite3.Connection) -> None:
    # Comments built as ForgeComment regardless of source forge classify the
    # same way: a GitHub-shaped and a GitLab-shaped raw dict are irrelevant to
    # the signal — only the normalized .body is read.
    repo_id = storage.get_or_create_repository(conn, "o", "r")
    storage.upsert_pull_requests(conn, repo_id, [
        _pr(1, created="2026-06-01T00:00:00Z"),
        _pr(2, created="2026-06-01T00:00:00Z"),
    ])
    gh = ForgeComment(created_at="2026-06-01T01:00:00Z", author="x",
                      body="we are blocked", raw={"id": 1})
    gl = ForgeComment(created_at="2026-06-01T01:00:00Z", author="y",
                      body="we are blocked", raw={"noteable_iid": 2})
    provider = _FakeProvider({1: [gh], 2: [gl]})
    result = retro_signals.compute_retro_signals(
        conn, provider, repo_id, "o", "r"
    )
    friction_rows = [r for r in result.rows if r[0] == "friction" and r[1] is not None]
    assert {r[1] for r in friction_rows} == {1, 2}
    assert all(r[2] == "1 matches" for r in friction_rows)


def test_fetch_caches_and_does_not_refetch(conn: sqlite3.Connection) -> None:
    repo_id = storage.get_or_create_repository(conn, "o", "r")
    storage.upsert_pull_requests(conn, repo_id, [
        _pr(1, created="2026-06-01T00:00:00Z"),
        _pr(2, created="2026-06-01T00:00:00Z"),
    ])
    c = ForgeComment(created_at="2026-06-01T01:00:00Z", author="x",
                     body="hi", raw={})
    provider = _FakeProvider({1: [c], 2: [c]})

    first = retro_signals.fetch_and_cache_comments(conn, provider, repo_id, "o", "r")
    assert first == 2
    assert sorted(provider.calls) == [1, 2]

    # Second run: PR 1 already cached. PR 2 has a comment too, so both skipped.
    provider.calls.clear()
    second = retro_signals.fetch_and_cache_comments(conn, provider, repo_id, "o", "r")
    assert second == 0
    assert provider.calls == []


def test_zero_comment_pr_fetched_once_then_skipped(conn: sqlite3.Connection) -> None:
    # A PR with no comments must be marked fetched so a re-run does not re-fetch
    # it (the skip-set is the fetched-marker, not the presence of comment rows).
    repo_id = storage.get_or_create_repository(conn, "o", "r")
    storage.upsert_pull_requests(conn, repo_id, [
        _pr(1, created="2026-06-01T00:00:00Z"),
    ])
    provider = _FakeProvider({})  # PR 1 has no comments

    first = retro_signals.fetch_and_cache_comments(conn, provider, repo_id, "o", "r")
    assert first == 1
    assert provider.calls == [1]

    provider.calls.clear()
    second = retro_signals.fetch_and_cache_comments(conn, provider, repo_id, "o", "r")
    assert second == 0
    assert provider.calls == []
