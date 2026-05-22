"""Tool registry — Gitsweeper analytics only.

A single fixed list keyed by tool name. Adding or removing a tool is
a code change in this file — not a runtime config flag. The order
matters: the AI client receives tools in this order and tends to
prefer the first ones it sees.

After the `gitsweeper-billbird-extract` change, every Billbird-only
read tool has moved to the standalone `billbird-client` package (see
`billbird-mcp`). The single Billbird-touching tool that remains here
is `gitsweeper_reconcile`, because reconcile is genuinely cross-source
(commits from GitHub + logs from Billbird) and lives in the analytics
workbench.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from gitsweeper.capabilities.manager_mcp import tools as t


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., dict[str, Any] | list[Any]]


TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="gitsweeper_pr_throughput",
        description=(
            "Time-to-merge percentiles (p25/median/p75/p95/max) over the local "
            "Gitsweeper cache. Output unit: days. Errors with cache_missing "
            "if the repo has not been fetched."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "repository": {"type": "string", "description": "owner/name"},
                "since": {"type": "string", "description": "Optional YYYY-MM-DD lower bound (UTC)"},
                "author": {"type": "string", "description": "Optional GitHub login filter"},
            },
            "required": ["repository"],
            "additionalProperties": False,
        },
        handler=t.gitsweeper_pr_throughput,
    ),
    ToolSpec(
        name="gitsweeper_first_response",
        description=(
            "Time-to-first-response percentiles. Cache-only — never fetches. "
            "Errors with cache_missing if any in-scope PR lacks a first-response "
            "row; the caller is expected to run `gitsweeper first-response` first."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "repository": {"type": "string"},
                "since": {"type": "string"},
                "author": {"type": "string"},
            },
            "required": ["repository"],
            "additionalProperties": False,
        },
        handler=t.gitsweeper_first_response,
    ),
    ToolSpec(
        name="gitsweeper_classify",
        description=(
            "Self-pulled vs maintainer-closed classification for "
            "closed-without-merge PRs. Cache-only."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "repository": {"type": "string"},
                "author": {"type": "string"},
            },
            "required": ["repository"],
            "additionalProperties": False,
        },
        handler=t.gitsweeper_classify,
    ),
    ToolSpec(
        name="gitsweeper_reconcile",
        description=(
            "Reconcile commit Time: footers against Billbird /log entries. "
            "Returns one row per (repo, author, issue) with commit minutes, "
            "log minutes, drift, and status (aligned / commits_only / "
            "logs_only / over_committed / over_logged). Output unit: minutes. "
            "Requires the `billbird-client` optional dependency."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "repository": {"type": "string", "description": "owner/name"},
                "since": {
                    "type": "string",
                    "description": "Optional YYYY-MM-DD or ISO 8601 lower bound",
                },
                "branch": {
                    "type": "string",
                    "description": "Optional branch name; default branch when omitted",
                },
                "author": {
                    "type": "string",
                    "description": "Optional GitHub login filter",
                },
            },
            "required": ["repository"],
            "additionalProperties": False,
        },
        handler=t.gitsweeper_reconcile,
    ),
    ToolSpec(
        name="gitsweeper_patterns",
        description=(
            "Day-of-week and hour-of-day patterns for submissions and "
            "responses. Output unit: count."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "repository": {"type": "string"},
                "since": {"type": "string"},
                "author": {"type": "string"},
            },
            "required": ["repository"],
            "additionalProperties": False,
        },
        handler=t.gitsweeper_patterns,
    ),
]


def tool_names() -> list[str]:
    """Return the tool names in registry order. Used by tests and by
    docs that need to keep their list in sync."""
    return [spec.name for spec in TOOLS]


def find(name: str) -> ToolSpec | None:
    for spec in TOOLS:
        if spec.name == name:
            return spec
    return None
