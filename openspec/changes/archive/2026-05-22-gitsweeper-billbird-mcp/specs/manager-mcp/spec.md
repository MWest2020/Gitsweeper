## ADDED Requirements

### Requirement: MCP server entry point

The system SHALL provide a `gitsweeper mcp` command that starts an MCP server speaking JSON-RPC 2.0 over stdio. The server SHALL terminate cleanly when its stdin is closed by the parent process.

#### Scenario: Manager attaches Claude Desktop

- **GIVEN** Claude Desktop is configured to spawn `gitsweeper mcp` as an MCP server
- **WHEN** the client connects
- **THEN** the server completes the MCP initialise handshake, advertises its tool registry, and stays running until stdin closes

#### Scenario: Server exits when parent closes the pipe

- **GIVEN** the server is running attached to a parent's stdin
- **WHEN** the parent closes the pipe
- **THEN** the server exits with status 0 within one second, releasing any open Billbird HTTP connections

### Requirement: Read-only tool boundary

The MCP server SHALL expose only read-only tools. No tool in this capability SHALL perform writes against Billbird, against GitHub, against the Gitsweeper cache, or against the local file system other than the cache that the wrapped Gitsweeper capabilities already use for reads.

#### Scenario: Mutating Billbird endpoint is unreachable through MCP

- **WHEN** any client invokes any MCP tool exposed by this capability
- **THEN** none of the tools sends a non-GET HTTP request to Billbird, and the absence is verifiable by inspecting the tool registry

#### Scenario: Tool registry contains no admin tools

- **WHEN** the server completes its `initialize` handshake
- **THEN** the advertised tool list contains no tool whose name implies a mutation (no `create_*`, `update_*`, `delete_*`, `revoke_*`)

### Requirement: Tool — Billbird hours summary

The server SHALL expose a tool `billbird_hours_summary(period, group_by, repo?, client?, user?)` that returns aggregated minutes from Billbird's active log entries for the given period, grouped by one of `user`, `client`, `repo`, or `issue`. Minutes SHALL come from Billbird's `/api/v1/time-entries` filtered to `status=active`.

#### Scenario: Hours by client for one month
- **WHEN** a manager invokes the tool with `period="2026-04"` and `group_by="client"`
- **THEN** the response is a list of `{client_id, client_name, minutes}` items, each minutes value summing only active entries in that month

#### Scenario: Hours by user for a repo
- **WHEN** the tool is invoked with `period="last-7d"`, `group_by="user"`, `repo="org/repo"`
- **THEN** the response groups active entries from that repository in the last 7 days by `github_username`

#### Scenario: Period uses inclusive day boundaries in UTC
- **WHEN** a `period` like `"2026-04"` is supplied
- **THEN** entries created from `2026-04-01T00:00:00Z` through `2026-04-30T23:59:59Z` are included; clients receive a `period` echo in the response naming the resolved start and end timestamps

### Requirement: Tool — plan vs actual

The server SHALL expose `billbird_plan_vs_actual(period?, status?, repo?, client?)` returning a list of issues with their planned minutes, logged minutes, variance, and status (`no_plan`, `under`, `on_target`, `over`). Values SHALL come from Billbird's plan-vs-actual endpoint per issue.

#### Scenario: Find over-budget issues this month
- **WHEN** the tool is invoked with `period="2026-05"` and `status="over"`
- **THEN** the response contains only issues whose logged minutes exceed planned minutes by more than 5 percent within the period

#### Scenario: No plan filter returns full landscape
- **WHEN** the tool is invoked with `period="last-30d"` and no status filter
- **THEN** the response includes all four status categories, ordered by absolute variance descending

### Requirement: Tool — cycle time

The server SHALL expose `billbird_cycle_time(period?, repo?)` returning cycle-time records: per-issue start/end and aggregate medians for the scope.

#### Scenario: Cycle time for a repository
- **WHEN** the tool is invoked with `repo="org/repo"` and `period="last-30d"`
- **THEN** the response returns the per-issue records plus aggregate `median_hours`, `p95_hours`, and `count` for closed-with-end-timestamp records

### Requirement: Tool — recent activity

The server SHALL expose `billbird_recent_activity(since, limit?)` returning the most recent log entries and plan entries (combined, type-tagged) created since the given timestamp.

#### Scenario: Quick check on yesterday's activity
- **WHEN** the tool is invoked with `since="2026-05-17T00:00:00Z"`
- **THEN** the response lists at most `limit` (default 50) entries created at or after that timestamp, ordered newest-first, each tagged `type="log"` or `type="plan"`

### Requirement: Tool — Gitsweeper PR analyses are exposed verbatim

The server SHALL expose the existing analyses from `pr-throughput-analysis`, `pr-classification`, and the `patterns` capability as MCP tools named `gitsweeper_pr_throughput`, `gitsweeper_first_response`, `gitsweeper_classify`, and `gitsweeper_patterns`. These tools SHALL NOT recompute or reformat results; they SHALL invoke the existing capability functions and return their results converted to JSON-serialisable form.

#### Scenario: PR throughput tool routes to the capability
- **WHEN** `gitsweeper_pr_throughput(repo="org/repo", since="2026-01-01")` is invoked
- **THEN** the response values are identical to those produced by `gitsweeper throughput org/repo --since 2026-01-01 --json` on the same cache state

#### Scenario: First-response tool inherits cache discipline
- **WHEN** `gitsweeper_first_response(repo="org/repo")` is invoked and the cache lacks first-response data for some PRs
- **THEN** the tool errors with a structured message asking the operator to run `gitsweeper fetch` and `gitsweeper first-response` first, mirroring the CLI's behaviour — the MCP server SHALL NOT silently issue many GitHub API calls

### Requirement: Tool — composite team status report

The server SHALL expose `team_status_report(period, scope)` returning a structured payload with two top-level keys: `data` (the inputs from every constituent tool, plus a resolved period block) and `markdown` (the same content rendered through the `report-rendering` capability with an added Billbird section). The tool SHALL accept a `scope` object with optional `repo`, `client`, and `author` fields.

#### Scenario: Weekly status for one repository
- **WHEN** the tool is invoked with `period="last-7d"` and `scope={"repo": "org/repo"}`
- **THEN** the `data` block contains hours summary, plan-vs-actual, PR throughput, first-response, classification, and patterns for that scope; `markdown` contains the same as a single document with section headings

#### Scenario: Missing Billbird config short-circuits before any work
- **WHEN** the tool is invoked while `BILLBIRD_API_URL` is unset
- **THEN** the tool returns a structured error naming the missing variable; no Gitsweeper analyses run, so the manager sees one error rather than a partial report

### Requirement: Lazy, named configuration errors

Billbird-touching tools SHALL validate `BILLBIRD_API_URL` and `BILLBIRD_API_TOKEN` at invocation time. When either is missing or empty, the tool SHALL return a structured error of the shape `{"error": "billbird_not_configured", "missing": ["BILLBIRD_API_TOKEN"], "docs": "docs/mcp.md"}`. The server SHALL NOT refuse to start in their absence; Gitsweeper-only tools SHALL remain callable.

#### Scenario: Missing token, Gitsweeper-only tool still works
- **WHEN** `BILLBIRD_API_TOKEN` is unset and `gitsweeper_pr_throughput(repo="org/repo")` is invoked
- **THEN** the call succeeds against the local cache and returns analysis results

#### Scenario: Missing token, Billbird tool fails clearly
- **WHEN** `BILLBIRD_API_TOKEN` is unset and `billbird_hours_summary(...)` is invoked
- **THEN** the tool returns the structured error naming `BILLBIRD_API_TOKEN` and citing `docs/mcp.md`

### Requirement: Surface Billbird auth and HTTP failures faithfully

When the Billbird API returns 401, 403, or any 4xx/5xx, the tool SHALL return a structured error that includes the status code, the upstream `error` body (verbatim where Billbird provided one), and a hint indicating likely cause (`auth`, `not_found`, `server`). The tool SHALL NOT retry on 4xx. The tool MAY retry once on 5xx with a 1-second delay and SHALL NOT retry further.

#### Scenario: Revoked token produces a clear 401
- **WHEN** a tool calls Billbird with a revoked token
- **THEN** Billbird returns 401 and the MCP tool returns `{"error": "billbird_http_error", "status": 401, "hint": "auth", ...}`

#### Scenario: Billbird is briefly unreachable
- **WHEN** the first Billbird HTTP call returns 502 and the retry succeeds
- **THEN** the tool returns the successful result; only the second call's body appears in the response

### Requirement: Schemas declare units and scope

Every tool's input and output schema SHALL declare the units of any numeric values (`minutes`, `hours`, `count`, `days`) and SHALL include the resolved period and scope in the response payload. No tool SHALL return a bare "total" without naming what scoped it.

#### Scenario: Hours summary echoes the resolved scope
- **WHEN** any `billbird_hours_summary` response is returned
- **THEN** it includes a `period` block (`{from, until}` ISO 8601 UTC), a `scope` block, and a `unit: "minutes"` declaration

#### Scenario: PR throughput echoes its scope
- **WHEN** `gitsweeper_pr_throughput` returns percentile data
- **THEN** the response includes the repo, `--since`, and `--author` values that were used, plus `unit: "days"`

### Requirement: Tool registry is fixed and inspectable

The set of tools advertised by the server SHALL be defined in a single registry module and SHALL be enumerable without invoking any of them. Adding or removing a tool SHALL require a code change in that module — not an env var, not a config file.

#### Scenario: Registry round-trip
- **WHEN** a developer imports the registry and lists tool names
- **THEN** the list contains exactly the nine tools defined by this capability, in a deterministic order

### Requirement: Documentation accompanying the server

The repository SHALL include a `docs/mcp.md` page describing: required env vars, an example Claude Desktop config snippet that spawns `gitsweeper mcp`, a list of the available tools with one-line descriptions, and a brief note on the read-only contract. The README SHALL link to the new page from a "Manager MCP" subsection near the existing CLI overview.

#### Scenario: New operator follows the docs
- **WHEN** a new operator reads `docs/mcp.md`
- **THEN** they can configure Claude Desktop with the snippet, set the two env vars, attach, and successfully invoke at least the `gitsweeper_pr_throughput` tool against an existing cache without consulting the source
