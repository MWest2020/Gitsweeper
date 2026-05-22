"""Tests for the Manager-MCP capability.

Two surfaces are covered:

1. The fixed tool registry — ordering, names, no mutation tools.
2. Each remaining tool's structured error envelopes when its cache /
   dependency is missing.

After the `gitsweeper-billbird-extract` change, Billbird-only read
tools live in the separate `billbird-client` package; only
`gitsweeper_reconcile` remains as a Billbird-touching tool here, and
it imports `billbird-client` as an optional dependency.
"""

from __future__ import annotations

import pytest

from gitsweeper.capabilities.manager_mcp.registry import TOOLS, find, tool_names
from gitsweeper.capabilities.manager_mcp.tools import (
    gitsweeper_classify,
    gitsweeper_first_response,
    gitsweeper_patterns,
    gitsweeper_pr_throughput,
    gitsweeper_reconcile,
)

# --- Registry --------------------------------------------------------------


def test_registry_has_five_tools_in_declared_order():
    assert len(TOOLS) == 5
    assert tool_names() == [
        "gitsweeper_pr_throughput",
        "gitsweeper_first_response",
        "gitsweeper_classify",
        "gitsweeper_reconcile",
        "gitsweeper_patterns",
    ]


def test_registry_has_no_mutation_tools():
    forbidden_prefixes = ("create_", "update_", "delete_", "revoke_", "post_")
    for name in tool_names():
        assert not name.startswith(forbidden_prefixes), name


def test_find_returns_none_for_unknown():
    assert find("nope") is None


def test_every_tool_schema_is_jsonschema_object():
    for spec in TOOLS:
        assert spec.input_schema["type"] == "object"
        assert "properties" in spec.input_schema


def test_registry_has_no_billbird_only_tools():
    """Guard the extract: billbird-only read tools must not regress in."""
    forbidden = {
        "billbird_hours_summary",
        "billbird_plan_vs_actual",
        "billbird_cycle_time",
        "billbird_recent_activity",
        "team_status_report",
    }
    assert forbidden.isdisjoint(tool_names())


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


# --- Reconcile depends on billbird-client ---------------------------------


@pytest.fixture
def _no_billbird_env(monkeypatch):
    monkeypatch.delenv("BILLBIRD_API_URL", raising=False)
    monkeypatch.delenv("BILLBIRD_API_TOKEN", raising=False)
    yield


def test_reconcile_invalid_repo_spec():
    out = gitsweeper_reconcile(repository="not-a-pair")
    assert out["error"] == "invalid_argument"


def test_reconcile_without_billbird_config(_no_billbird_env):
    """`billbird-client` is installed in dev; without env vars set the
    Billbird-not-configured branch fires."""
    out = gitsweeper_reconcile(repository="org/repo")
    assert out["error"] == "billbird_not_configured"
    assert "BILLBIRD_API_URL" in out["missing"]
    assert "BILLBIRD_API_TOKEN" in out["missing"]


def test_reconcile_handles_missing_billbird_client(monkeypatch):
    """When `billbird-client` is not installed, the tool surfaces a
    `billbird_client_unavailable` error rather than crashing with
    ImportError."""
    import builtins

    real_import = builtins.__import__

    def _raise_for_billbird(name, *args, **kwargs):
        if name == "billbird_client":
            raise ImportError("simulated: billbird-client is not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _raise_for_billbird)

    out = gitsweeper_reconcile(repository="org/repo")
    assert out["error"] == "billbird_client_unavailable"
    assert "billbird-client" in out["hint"]
