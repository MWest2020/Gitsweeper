"""Shared helpers for reading PR fields from cached storage rows.

These three helpers parse the ISO-8601 timestamps and read the PR title out
of the stored ``raw_payload`` JSON. They are byte-identical needs of the
``dora_metrics`` and ``retro_signals`` capabilities, kept in one place so the
parsing rules cannot drift between the two. Pure functions, no I/O.
"""

from __future__ import annotations

import json
from datetime import datetime


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def days_between(start: str, end: str) -> float:
    return (parse_iso(end) - parse_iso(start)).total_seconds() / 86400.0


def title_of(raw_payload: str) -> str:
    """Read the PR title from the stored raw payload (uniform across forges)."""
    try:
        parsed = json.loads(raw_payload)
    except (TypeError, ValueError):
        return ""
    title = parsed.get("title") if isinstance(parsed, dict) else None
    return title if isinstance(title, str) else ""


__all__ = ["days_between", "parse_iso", "title_of"]
