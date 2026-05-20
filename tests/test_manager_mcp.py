"""Tests for the Manager-MCP capability.

Two surfaces are covered:

1. The fixed tool registry — ordering, names, schemas.
2. Each tool's error envelopes when Billbird is misconfigured or
   returns errors. The Gitsweeper-side tools' cache-missing paths are
   exercised against a temporary SQLite cache.
"""

from __future__ import annotations

import pytest

from gitsweeper.capabilities.manager_mcp.periods import parse_period
from gitsweeper.capabilities.manager_mcp.registry import TOOLS, find, tool_names
from gitsweeper.capabilities.manager_mcp.tools import (
    billbird_cycle_time,
    billbird_hours_summary,
    billbird_plan_vs_actual,
    billbird_recent_activity,
    gitsweeper_classify,
    gitsweeper_first_response,
    gitsweeper_patterns,
    gitsweeper_pr_throughput,
    team_status_report,
)

# --- Registry --------------------------------------------------------------


def test_registry_has_nine_tools_in_declared_order():
    assert len(TOOLS) == 9
    assert tool_names() == [
        "team_status_report",
        "billbird_hours_summary",
        "billbird_plan_vs_actual",
        "billbird_cycle_time",
        "billbird_recent_activity",
        "gitsweeper_pr_throughput",
        "gitsweeper_first_response",
        "gitsweeper_classify",
        "gitsweeper_patterns",
    ]


def test_registry_has_no_mutation_tools():
    # Read-only contract: refuse any tool whose name suggests mutation.
    forbidden_prefixes = ("create_", "update_", "delete_", "revoke_", "post_")
    for name in tool_names():
        assert not name.startswith(forbidden_prefixes), name


def test_find_returns_none_for_unknown():
    assert find("nope") is None


def test_every_tool_schema_is_jsonschema_object():
    for spec in TOOLS:
        assert spec.input_schema["type"] == "object"
        assert "properties" in spec.input_schema


# --- Period parsing --------------------------------------------------------


def test_parse_period_month():
    p = parse_period("2026-04")
    assert p.label == "2026-04"
    assert p.from_iso.startswith("2026-04-01")
    assert p.until_iso.startswith("2026-04-30")


def test_parse_period_day():
    p = parse_period("2026-04-15")
    assert p.label == "2026-04-15"
    assert p.from_iso.startswith("2026-04-15")
    assert p.until_iso.startswith("2026-04-15")


def test_parse_period_last_n():
    p = parse_period("last-7d")
    # both timestamps should be ISO Z
    assert p.from_iso.endswith("Z")
    assert p.until_iso.endswith("Z")


def test_parse_period_invalid():
    with pytest.raises(ValueError):
        parse_period("nope")


def test_parse_period_zero_days():
    with pytest.raises(ValueError):
        parse_period("last-0d")


# --- Billbird tools — config and error envelopes ---------------------------


@pytest.fixture(autouse=True)
def clear_billbird_env(monkeypatch):
    """Make sure no test inherits Billbird env vars from the host."""
    monkeypatch.delenv("BILLBIRD_API_URL", raising=False)
    monkeypatch.delenv("BILLBIRD_API_TOKEN", raising=False)
    yield


def test_hours_summary_without_billbird_config_returns_structured_error():
    out = billbird_hours_summary(period="2026-04", group_by="user")
    assert out["error"] == "billbird_not_configured"
    assert "BILLBIRD_API_URL" in out["missing"]
    assert "BILLBIRD_API_TOKEN" in out["missing"]
    assert out["docs"] == "docs/mcp.md"


def test_hours_summary_invalid_group_by():
    out = billbird_hours_summary(period="2026-04", group_by="bogus")
    assert out["error"] == "invalid_argument"
    assert out["field"] == "group_by"


def test_hours_summary_invalid_period(monkeypatch):
    monkeypatch.setenv("BILLBIRD_API_URL", "https://example.test")
    monkeypatch.setenv("BILLBIRD_API_TOKEN", "bb_x")
    out = billbird_hours_summary(period="bad", group_by="user")
    assert out["error"] == "invalid_argument"
    assert out["field"] == "period"


def test_plan_vs_actual_without_billbird_config():
    out = billbird_plan_vs_actual()
    assert out["error"] == "billbird_not_configured"


def test_plan_vs_actual_invalid_status(monkeypatch):
    monkeypatch.setenv("BILLBIRD_API_URL", "https://example.test")
    monkeypatch.setenv("BILLBIRD_API_TOKEN", "bb_x")
    out = billbird_plan_vs_actual(status="bogus")
    assert out["error"] == "invalid_argument"
    assert out["field"] == "status"


def test_recent_activity_without_billbird_config():
    out = billbird_recent_activity(since="2026-05-01")
    assert out["error"] == "billbird_not_configured"


def test_cycle_time_returns_not_implemented():
    out = billbird_cycle_time()
    assert out["error"] == "not_implemented"


def test_team_status_report_fails_fast_without_billbird():
    out = team_status_report(period="2026-04", scope={"repo": "org/repo"})
    # Pre-flight Billbird check should short-circuit BEFORE the
    # Gitsweeper sections run, so no partial result keys exist.
    assert out["error"] == "billbird_not_configured"
    assert "data" not in out


# --- Gitsweeper-side tools — cache-missing path ---------------------------


def test_pr_throughput_returns_cache_missing_when_unknown_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    out = gitsweeper_pr_throughput(repository="org/repo-never-fetched")
    assert out["error"] == "cache_missing"
    assert out["repository"] == "org/repo-never-fetched"


def test_pr_throughput_invalid_repo_spec():
    out = gitsweeper_pr_throughput(repository="not-a-pair")
    assert out["error"] == "invalid_argument"


def test_first_response_returns_cache_missing_for_unknown_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    out = gitsweeper_first_response(repository="org/repo-never-fetched")
    assert out["error"] == "cache_missing"


def test_classify_returns_cache_missing_for_unknown_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    out = gitsweeper_classify(repository="org/repo-never-fetched")
    assert out["error"] == "cache_missing"


def test_patterns_returns_cache_missing_for_unknown_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    out = gitsweeper_patterns(repository="org/repo-never-fetched")
    assert out["error"] == "cache_missing"
