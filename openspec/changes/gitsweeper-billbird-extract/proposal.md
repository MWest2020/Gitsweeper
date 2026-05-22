## Why

Gitsweeper accreted Billbird-specific code while solving urgent problems: `lib/billbird_client.py`, five Billbird-touching MCP tools (`billbird_hours_summary`, `billbird_plan_vs_actual`, `billbird_recent_activity`, `billbird_cycle_time`, `team_status_report`), and a Billbird-centric flavour to the composite report. That made sense when Billbird was the only consumer of Gitsweeper's MCP layer. It does not match the stated architecture: **Gitsweeper is a generic analytics workbench; Billbird is one of many possible sources.**

The newly-released [`billbird-client`](https://github.com/MWest2020/billbird-client) is now the home for Billbird-only reads — both the Python library and a Billbird-only MCP server. Routing Gitsweeper's Billbird needs through that package removes the implicit coupling, shrinks Gitsweeper's MCP surface to its actual analytics scope, and makes the dependency direction visible at the package-graph level.

## What Changes

- Remove `src/gitsweeper/lib/billbird_client.py` — the new `billbird-client` package supersedes it.
- Remove the five Billbird-touching tools from `src/gitsweeper/capabilities/manager_mcp/tools.py` and from the registry (`billbird_hours_summary`, `billbird_plan_vs_actual`, `billbird_recent_activity`, `billbird_cycle_time`, `team_status_report`). The composite `team_status_report` retires here entirely — the Billbird half belongs in `billbird-client`; the PR-side half is already covered by the individual analytics tools.
- Remove `src/gitsweeper/capabilities/manager_mcp/periods.py` — only the Billbird tools needed it. Gitsweeper-side tools accept `--since YYYY-MM-DD` already.
- Add `billbird-client` as an **optional** dependency under the `[project.optional-dependencies]` group `billbird`. Default installs of Gitsweeper do not pull it; reconcile users install with `pip install gitsweeper[billbird]` (or the uv equivalent).
- Rewire `capabilities/commit_time_reconcile.py` to import `BillbirdClient` from `billbird_client` instead of the in-tree shim. If the import fails (package not installed), `gitsweeper reconcile` and the `gitsweeper_reconcile` MCP tool degrade to a structured `billbird_client_unavailable` error rather than crashing.
- Update the MCP registry — 10 tools → 5 (PR throughput, first-response, classify, patterns, reconcile). Update `tests/test_manager_mcp.py` and `scripts/mcp_smoke.py` to match.
- Update `docs/mcp.md` — drop the Billbird tools from the table; add a "Billbird tools live elsewhere" note pointing at the new package.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `manager-mcp`: registry shrinks to Gitsweeper-native analytics + reconcile; Billbird-only tools are removed; the composite team-status-report tool retires.
- `commit-time-reconcile`: now sources `BillbirdClient` from the external `billbird-client` package; gracefully degrades when that optional dependency is absent.

## Impact

- **Code (Python)**: deletion of `lib/billbird_client.py`, `capabilities/manager_mcp/periods.py`; ~150 lines removed from `manager_mcp/tools.py` (the five Billbird-touching tools + composite) and ~30 from `registry.py`. `commit_time_reconcile.py` switches one import.
- **Tests**: `tests/test_billbird_client.py` and `tests/test_mcp_against_fake_billbird.py` retire here (their concerns now live in `billbird-client`'s own test suite). `tests/test_manager_mcp.py` expectations move from 10 to 5 tools. `tests/test_commit_time_reconcile.py` adjusts its imports.
- **`pyproject.toml`**: gains `[project.optional-dependencies] billbird = ["billbird-client>=0.1.0"]`. For now, because `billbird-client` is not yet on PyPI, that dependency resolves via a git URL; switch to the PyPI version as soon as it lands.
- **`scripts/mcp_smoke.py`**: drops Billbird-tool calls (they're tested by `billbird-client`'s own smoke); keeps the analytics-tool checks.
- **Documentation**: `docs/mcp.md` shortened; a "Manager surface for Billbird specifically" note points readers at `billbird-client`.
- **Backwards compatibility**: this is a **breaking change** for anyone who was calling the Billbird MCP tools through Gitsweeper. The migration is one line in their MCP client config — point at `billbird-mcp` (from `billbird-client`) instead of (or alongside) `gitsweeper mcp`. Documented in the CHANGELOG.
