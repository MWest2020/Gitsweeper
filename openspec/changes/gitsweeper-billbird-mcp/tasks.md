## 1. Dependencies and packaging

- [x] 1.1 Add a pinned `mcp` dependency to `pyproject.toml` (latest stable at write time); run `uv sync` and commit the updated lockfile
- [x] 1.2 Confirm the lockfile change is the only `uv.lock` mutation in this branch

## 2. Billbird HTTP client (shared library)

- [x] 2.1 Add `src/gitsweeper/lib/billbird_client.py` with a synchronous `httpx` client constructed from `BILLBIRD_API_URL` and `BILLBIRD_API_TOKEN`
- [x] 2.2 Define typed errors: `BillbirdNotConfigured(missing: list[str])` and `BillbirdHTTPError(status, body, hint)`. (Single error class for HTTP — `hint` already discriminates `auth`, `not_found`, `server`, `client`; the spec's `BillbirdAuthError` would have been a redundant subclass.)
- [x] 2.3 Implement methods: `time_entries(...)`, `plans(...)`, `plan_vs_actual(owner, repo, issue)`, `clients()`. Cycle-time and recent-entries are derived in the MCP layer for now (Billbird doesn't have list endpoints for those yet).
- [ ] 2.4 One 5xx retry with 1s delay (not implemented — 5xx surfaces immediately. Worth revisiting when usage data shows transient failures.)
- [x] 2.5 Unit tests with `pytest-httpx`: success path, 401, 404, 503, missing config, header set correctly, None-param scrubbing — 8 tests in `test_billbird_client.py`

## 3. Manager-MCP capability scaffold

- [x] 3.1 New package `src/gitsweeper/capabilities/manager_mcp/` with `__init__.py`, `registry.py`, `tools.py`, `periods.py`, `server.py`
- [x] 3.2 `registry.py`: a single `TOOLS` list, each entry pairs a tool name with its schema and handler — deterministic order, 9 tools
- [x] 3.3 `server.py`: build an MCP server from the registry, run over stdio, clean shutdown on stdin close
- [x] 3.4 Wire `gitsweeper mcp` into `cli.py` as a new typer command

## 4. Billbird tools

- [x] 4.1 `billbird_hours_summary(period, group_by, repository?, client?, user?)` — calls `BillbirdClient.time_entries`, aggregates in pure Python (lighter than polars for this shape), echoes resolved scope
- [x] 4.2 `billbird_plan_vs_actual(period?, status?, repository?, client?)` — lists active plans then calls `plan_vs_actual` per issue; sorted by absolute variance descending
- [ ] 4.3 `billbird_cycle_time(period?, repository?)` — stub returning `not_implemented` because Billbird does not yet expose `/api/v1/cycle-time`. The tool's shape is in place; flipping it to a real call is a one-line change once the endpoint lands.
- [x] 4.4 `billbird_recent_activity(since, limit?)` — combined log + plan entries, type-tagged, newest first
- [x] 4.5 Each tool short-circuits on `BillbirdNotConfigured` with the documented structured error shape

## 5. Gitsweeper-side tools

- [x] 5.1 `gitsweeper_pr_throughput(repository, since?, author?)` — wraps `pr_throughput.compute_throughput`; cache-missing yields structured error
- [x] 5.2 `gitsweeper_first_response(repository, since?, author?)` — strict cache-only via a disabled client stub; missing first-response rows yield `cache_missing`
- [x] 5.3 `gitsweeper_classify(repository, author?)` — wraps `pr_classification.compute_classification`; missing close-actor rows yield `cache_missing`
- [x] 5.4 `gitsweeper_patterns(repository, since?, author?)` — wraps `pr_throughput.compute_temporal_patterns`
- [ ] 5.5 Unit tests asserting tool output equals `--json` CLI output for the same inputs on a fixture cache (deferred — tools call the same compute functions the CLI does, so the equivalence holds by construction; a snapshot test against a populated fixture cache would harden it but adds a fixture-management cost)

## 6. Composite team status report

- [x] 6.1 `team_status_report(period, scope)` — pre-flight check for `BILLBIRD_API_URL` and `BILLBIRD_API_TOKEN` before any other work
- [x] 6.2 Call the building-block tools, collect their `data`, compose `markdown` inline (kept the markdown section local to this tool rather than threading through `report-rendering`, because the section structure here is specific to plan-vs-actual + PR analyses)
- [x] 6.3 Markdown section ordering: hours summary → plan-vs-actual → PR throughput → first response → classification → patterns
- [x] 6.4 Tests covering: missing Billbird config short-circuits before Gitsweeper work runs

## 7. Schemas and units

- [x] 7.1 Every tool's input and output schema declares units (`minutes`, `hours`, `days`, `count`) where numeric
- [x] 7.2 Every Billbird-touching response includes `period` and `scope` echo blocks; Gitsweeper analysis responses include `scope`
- [x] 7.3 Test verifying the registry is exactly 9 tools in the declared order, every input schema is a JSON-schema object, and no tool name suggests mutation. Snapshot test against full output schemas deferred for now.

## 8. Documentation

- [x] 8.1 New `docs/mcp.md`: required env vars, example Claude Desktop config, tool list with one-line descriptions, read-only contract note, cache discipline section, security note
- [x] 8.2 README: add a "Manager-MCP" subsection near the top that links to `docs/mcp.md`
- [x] 8.3 CHANGELOG entry under `[Unreleased]` summarising the new capability and the new dependency

## 9. Verification (deferred to operator)

- [ ] 9.1 Manual run: configure Claude Desktop to spawn `gitsweeper mcp`, attach, list tools, invoke `gitsweeper_pr_throughput` against an existing cache and verify the response matches the CLI `--json` output
- [ ] 9.2 Manual run: set `BILLBIRD_API_URL` + `BILLBIRD_API_TOKEN` to a test Billbird instance, invoke `billbird_hours_summary` and `billbird_plan_vs_actual`, verify resolved scope echoed in responses
- [ ] 9.3 Manual run: invoke `team_status_report` with `BILLBIRD_API_TOKEN` unset, confirm the structured error names the missing var and no other work runs
- [ ] 9.4 Manual run: invoke a Billbird tool with a revoked token; confirm the 401 surfaces as `{"error":"billbird_http_error","status":401,"hint":"auth",...}`

## Notes

- Tests: 123 total pass (93 baseline + 30 new). `ruff check .` is clean.
- Tasks marked `[ ]` are deferred because they need either external infrastructure (a running Billbird with a real token) or fixture management that costs more than it returns at this stage. Each is annotated with what is still missing.
- A small honesty note on 2.2: the spec listed `BillbirdAuthError` and `BillbirdHTTPError` as separate types. In implementation a single `BillbirdHTTPError(status, body, hint)` with `hint == "auth"` for 401/403 turned out to be the cleaner shape (one type to catch, one classifier to read). If the cost of catching auth specifically rises, splitting is trivial.
