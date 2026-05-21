"""Tests for the commit-message footer parser.

Pure unit tests — no I/O. Covers footer extraction, multi-footer
behaviour, issue references, and the cross-repo-ignore rule.
"""

from __future__ import annotations

import pytest

from gitsweeper.lib.commit_time import parse_issue_refs, parse_time_footer


@pytest.mark.parametrize(
    "message,want",
    [
        ("fix the regression\n\nTime: 1h30m", 90),
        ("small refactor\n\nTime: 45m", 45),
        ("only hours\n\nTime: 2h", 120),
        ("lowercase prefix\n\ntime: 30m", 30),
        ("mixed case prefix\n\nTIME: 1h", 60),
        ("trailing whitespace\n\nTime: 30m   ", 30),
        ("leading whitespace\n\n   Time: 30m", 30),
        ("no footer\n\njust a regular commit body", None),
        ("empty footer\n\nTime: ", None),
        ("zero duration\n\nTime: 0h0m", None),
        ("inline mention ignored: took 2h to write", None),
        ("multi-line message\n\nbody talks about 2h here\n\nTime: 45m", 45),
    ],
)
def test_parse_time_footer(message: str, want: int | None) -> None:
    assert parse_time_footer(message) == want


def test_parse_time_footer_last_wins() -> None:
    # Amended commits sometimes leave two footers; the more recent
    # one is the dev's current intent.
    msg = "first version\n\nTime: 1h\n\namended\n\nTime: 2h"
    assert parse_time_footer(msg) == 120


def test_parse_time_footer_empty_input() -> None:
    assert parse_time_footer("") is None


@pytest.mark.parametrize(
    "message,want",
    [
        ("Closes #42: rewrite the parser", [42]),
        ("fixes #5, related to #7", [5, 7]),
        ("Refs #100", [100]),
        ("bare #1 reference", [1]),
        ("no refs here", []),
        ("ignore other/repo#10", []),
        ("local #5 keeps; foreign owner/proj#9 drops", [5]),
        ("dedupe #3 and #3 again", [3]),
        ("#1 #2 #3", [1, 2, 3]),
        # Word-boundary: must not match inside another token.
        ("commit abc#123 hash-like noise", []),
        # Word boundary: must not match an SHA-like trailing number.
        ("sha def123 not an issue ref", []),
    ],
)
def test_parse_issue_refs(message: str, want: list[int]) -> None:
    assert parse_issue_refs(message) == want


def test_parse_issue_refs_empty_input() -> None:
    assert parse_issue_refs("") == []
