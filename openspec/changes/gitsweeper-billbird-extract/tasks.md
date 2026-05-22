## 1. Move Billbird HTTP client out

- [x] 1.1 Delete `src/gitsweeper/lib/billbird_client.py`
- [x] 1.2 Delete `tests/test_billbird_client.py`
- [x] 1.3 Delete `src/gitsweeper/capabilities/manager_mcp/periods.py` (only used by Billbird tools)

## 2. Shrink the MCP tool registry

- [x] 2.1 Remove `billbird_hours_summary`, `billbird_plan_vs_actual`, `billbird_cycle_time`, `billbird_recent_activity`, `team_status_report` from `capabilities/manager_mcp/tools.py`
- [x] 2.2 Remove their entries from `capabilities/manager_mcp/registry.py`; remaining list has 5 tools (PR throughput, first-response, classify, patterns, reconcile)
- [x] 2.3 Delete `tests/test_mcp_against_fake_billbird.py`
- [x] 2.4 Update `tests/test_manager_mcp.py`: registry has 5 tools, drop the Billbird-config-error assertions

## 3. Reconcile uses the external billbird-client

- [x] 3.1 `capabilities/commit_time_reconcile.py` imports `BillbirdClient`, `BillbirdHTTPError`, `BillbirdNotConfigured` from the external `billbird_client` package
- [x] 3.2 Wrap the import in a try/except so a missing optional dep yields a `billbird_client_unavailable` error envelope rather than an import crash
- [x] 3.3 Update `tests/test_commit_time_reconcile.py` imports to match
- [x] 3.4 Add a small unit test for the "package not installed" branch (use a stub that raises ImportError when the importer is called)

## 4. Optional dependency declaration

- [x] 4.1 Add `[project.optional-dependencies] billbird = ["billbird-client>=0.1.0"]` to `pyproject.toml`
- [x] 4.2 For development against an unreleased `billbird-client`, also support a `--with` git-URL install path in docs (`uv add billbird-client@git+https://github.com/MWest2020/billbird-client.git`)
- [x] 4.3 Re-sync the lockfile (`uv sync --no-install-project` or similar to update without installing the project itself)

## 5. Documentation

- [x] 5.1 `docs/mcp.md` — trim the tool table from 10 to 5; add a "Billbird tools live elsewhere" section linking `billbird-client`
- [x] 5.2 `docs/reconcile.md` — note the optional `billbird-client` dependency; instruct the install path
- [x] 5.3 `README.md` — add a short paragraph about the decoupling and the `billbird` extra
- [x] 5.4 `CHANGELOG.md` — breaking-change entry naming the removed tools and the migration

## 6. Smoke

- [x] 6.1 `scripts/mcp_smoke.py` — drop the Billbird-tool assertions; only check Gitsweeper analytics tools
- [x] 6.2 `uv run pytest`: every remaining test green
- [x] 6.3 `uv run ruff check .`: clean
- [x] 6.4 If `billbird-client` is installable (git URL works), run `gitsweeper reconcile` against the live test stack once more to confirm the new dependency wiring works end-to-end. Otherwise document that the reconcile path needs the dep
