## Why

Two existing repositories produce a manager's view of a development team's reality: Billbird records the hours and (soon) plans, Gitsweeper analyses the pull-request process. Today a manager who wants to answer "how is client X tracking against budget while the team's PR throughput holds up?" has to read two CLIs and merge the answers in their head. An MCP server fronting both is the smallest piece that closes that loop without inventing a new dashboard.

This change earns its place by serving real manager questions — variance against plan, who logged what against which client, where PRs are stuck — not by exposing every endpoint Billbird has. Tools that are merely possible (list every entry, fetch one row by ID) are deliberately out of scope because they do not move a manager forward.

The change is also the consumer that justifies API tokens in Billbird (`billbird-plan-command`): without an MCP-side caller, the token capability has no production user.

## What Changes

- New `gitsweeper mcp` command that runs an MCP server over stdio (default) so Claude Desktop and similar clients can attach.
- New shared library `lib/billbird_client.py`: thin synchronous HTTP client around Billbird's `/api/v1/*` using a bearer token from `BILLBIRD_API_TOKEN`. No retries beyond Billbird's own; surfaces 4xx/5xx as typed errors.
- New MCP tools — read-only, structured output (no pre-rendered prose) so the AI client renders responses to the manager:
  - `billbird_hours_summary(period, group_by, repo?, client?, user?)`
  - `billbird_plan_vs_actual(period?, status?, repo?, client?)`
  - `billbird_cycle_time(period?, repo?)`
  - `billbird_recent_activity(since, limit?)`
  - `gitsweeper_pr_throughput(repo, since?, author?)`
  - `gitsweeper_first_response(repo, since?, author?)`
  - `gitsweeper_classify(repo, author?)`
  - `gitsweeper_patterns(repo, since?, author?)`
  - `team_status_report(period, scope)` — composite tool returning a structured payload that an MCP client can render as the manager-facing summary.
- New configuration: `BILLBIRD_API_URL` and `BILLBIRD_API_TOKEN` env vars. Both required when a `billbird_*` tool is invoked; absence is reported as a tool error, not a startup failure.
- New dependency: the official `mcp` Python SDK. No further runtime dependencies.
- Documentation: a "Manager MCP" section in the README plus a short `docs/mcp.md` with example Claude Desktop config.

Out of scope explicitly:
- Write operations through MCP (creating clients, plans, tokens, or log entries). Slash commands in GitHub stay the only write path.
- Per-tool caching of Billbird responses; the data is current and the volumes are small.
- Multi-Billbird configuration. One Gitsweeper installation points at one Billbird instance — matching the "one Billbird per organisation" decision.
- HTTP transport for the MCP server. stdio is enough until a remote use case appears.

## Capabilities

### New Capabilities
- `manager-mcp`: MCP server transport, tool registry, and the read-only tools listed above. The capability owns *what a manager can ask through an MCP client*; the Billbird HTTP client and existing Gitsweeper capabilities are shared infrastructure it depends on.

### Modified Capabilities
<!-- None. The MCP layer wraps existing capabilities; it does not change their behaviour. -->

## Impact

- **Code (Python)**: new package `src/gitsweeper/capabilities/manager_mcp/` (server entry, tool registry, tool handlers); new shared library `src/gitsweeper/lib/billbird_client.py`; one new typer command in `cli.py`.
- **Dependencies**: add `mcp` to `pyproject.toml`. No other runtime additions. Dev: nothing new (pytest-httpx already mocks HTTP).
- **Config**: two new env vars; both consumed lazily inside Billbird tools, so the server itself starts even without Billbird configured (Gitsweeper-only tools remain usable).
- **Cross-repo coupling**: the bearer-token contract is owned by `billbird-plan-command` in the Billbird repo. This change consumes the contract; it does not own it.
- **Operational**: `gitsweeper mcp` exits non-zero if the `mcp` package is missing, the env var setup is invalid only when a Billbird tool is called, and otherwise logs structured errors to stderr so the MCP client can surface them.
- **Backwards compatibility**: additive. Existing `fetch`, `throughput`, `first-response`, `classify`, `patterns`, `report` commands unchanged.
