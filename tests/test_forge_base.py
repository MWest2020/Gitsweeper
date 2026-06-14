"""Unit tests for the forge base layer's timestamp normalization."""

from __future__ import annotations

import pytest

from gitsweeper.lib.forge.base import normalize_timestamp


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        # Gitea/Forgejo year-1 "zero time" sentinel for an unset timestamp.
        "0001-01-01T00:00:00Z",
        # Positive offset: converting to UTC pushes below MINYEAR (OverflowError).
        "0001-01-01T00:00:00+02:00",
        # Garbage / unparseable.
        "not-a-timestamp",
        "2026-13-99T99:99:99Z",
    ],
)
def test_normalize_timestamp_unset_or_invalid_returns_none(value: str | None) -> None:
    assert normalize_timestamp(value) is None


def test_normalize_timestamp_normal_values_unchanged() -> None:
    # Already-UTC `Z` round-trips unchanged.
    assert normalize_timestamp("2026-06-13T05:24:57Z") == "2026-06-13T05:24:57Z"
    # A positive offset is converted to the equivalent UTC instant.
    assert normalize_timestamp("2026-06-13T19:43:08+02:00") == "2026-06-13T17:43:08Z"
    # Fractional seconds are truncated to second precision with a trailing Z.
    assert normalize_timestamp("2026-06-13T06:07:14.633Z") == "2026-06-13T06:07:14Z"
