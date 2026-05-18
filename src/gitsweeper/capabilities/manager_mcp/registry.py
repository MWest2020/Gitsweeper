"""Tool registry.

A single fixed list keyed by tool name. Adding or removing a tool is a
code change in this file — not a runtime config flag. The order matters:
the AI client receives tools in the order they appear here, so leading
with high-value tools (the composite report, then the most-asked
queries) makes for better selection.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from gitsweeper.capabilities.manager_mcp import tools as t


@dataclass(frozen=True)
class ToolSpec:
    """One MCP tool, plus enough JSON-schema to advertise it to the
    AI client. Schemas are kept inline so they stay next to the
    function they document; that beats a separate schema file that
    drifts."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., dict[str, Any] | list[Any]]


_PERIOD_DESC = (
    "Period like '2026-04', '2026-04-15', or 'last-7d'. UTC. The response "
    "echoes the resolved start/end timestamps."
)


TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="team_status_report",
        description=(
            "Composite weekly status: hours summary + plan-vs-actual + PR "
            "throughput + first-response + classification + patterns. Returns "
            "both structured data and a single markdown document. "
            "Fails fast on missing Billbird config."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": _PERIOD_DESC},
                "scope": {
                    "type": "object",
                    "description": (
                        "Optional scope filter. Keys: 'repo' (owner/name), "
                        "'client' (exact name), 'author' (GitHub login), "
                        "'hours_group_by' (one of user/client/repo/issue, "
                        "defaults to 'user')."
                    ),
                    "properties": {
                        "repo": {"type": "string"},
                        "client": {"type": "string"},
                        "author": {"type": "string"},
                        "hours_group_by": {
                            "type": "string",
                            "enum": ["user", "client", "repo", "issue"],
                        },
                    },
                    "additionalProperties": False,
                },
            },
            "required": ["period"],
            "additionalProperties": False,
        },
        handler=t.team_status_report,
    ),
    ToolSpec(
        name="billbird_hours_summary",
        description=(
            "Aggregate active log minutes for a period, grouped by user, "
            "client, repo, or issue. Output unit: minutes."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": _PERIOD_DESC},
                "group_by": {
                    "type": "string",
                    "enum": ["user", "client", "repo", "issue"],
                    "description": "One of user, client, repo, issue.",
                },
                "repository": {"type": "string", "description": "Optional owner/name filter"},
                "client": {"type": "string", "description": "Optional client name (exact match)"},
                "user": {"type": "string", "description": "Optional GitHub username filter"},
            },
            "required": ["period", "group_by"],
            "additionalProperties": False,
        },
        handler=t.billbird_hours_summary,
    ),
    ToolSpec(
        name="billbird_plan_vs_actual",
        description=(
            "Per-issue variance between active plan and active log totals. "
            "Output unit: minutes. Ordered by absolute variance descending so "
            "the issues most in need of attention lead the list."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": "Optional " + _PERIOD_DESC},
                "status": {
                    "type": "string",
                    "enum": ["no_plan", "under", "on_target", "over"],
                    "description": "Optional status filter",
                },
                "repository": {"type": "string"},
                "client": {"type": "string"},
            },
            "required": [],
            "additionalProperties": False,
        },
        handler=t.billbird_plan_vs_actual,
    ),
    ToolSpec(
        name="billbird_cycle_time",
        description=(
            "Cycle-time per issue and aggregate for a scope. Stub: returns "
            "a structured 'not_implemented' response until Billbird exposes "
            "the matching REST endpoint."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": "Optional " + _PERIOD_DESC},
                "repository": {"type": "string"},
            },
            "required": [],
            "additionalProperties": False,
        },
        handler=t.billbird_cycle_time,
    ),
    ToolSpec(
        name="billbird_recent_activity",
        description=(
            "Recent log + plan entries (combined, type-tagged 'log' or "
            "'plan'). Newest first. Output unit: minutes."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "since": {
                    "type": "string",
                    "description": (
                        "Lower bound on creation timestamp "
                        "(ISO 8601 UTC, e.g. 2026-05-17T00:00:00Z)"
                    ),
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 500,
                    "description": "Maximum number of rows returned. Default 50.",
                },
            },
            "required": ["since"],
            "additionalProperties": False,
        },
        handler=t.billbird_recent_activity,
    ),
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
