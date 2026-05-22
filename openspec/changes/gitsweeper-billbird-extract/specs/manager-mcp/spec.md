## REMOVED Requirements

### Requirement: Tool — Billbird hours summary
**Reason**: Billbird-only read tools no longer belong in Gitsweeper's MCP. The replacement lives in the `billbird-client` package's MCP server (`billbird-mcp`), which exposes `billbird_hours_summary` directly.

**Migration**: Operators who use this tool should add the `billbird-mcp` server to their MCP client configuration. See `billbird-client/docs/mcp.md`.

### Requirement: Tool — plan vs actual
**Reason**: As above — Billbird-only tool, now in `billbird-mcp`.

**Migration**: Point the MCP client at `billbird-mcp` for `billbird_plan_vs_actual`.

### Requirement: Tool — cycle time
**Reason**: As above — Billbird-only tool, now in `billbird-mcp` (still a stub there until Billbird exposes the endpoint).

**Migration**: Point the MCP client at `billbird-mcp` for `billbird_cycle_time`.

### Requirement: Tool — recent activity
**Reason**: As above — Billbird-only tool, now in `billbird-mcp`.

**Migration**: Point the MCP client at `billbird-mcp` for `billbird_recent_activity`.

### Requirement: Tool — composite team status report
**Reason**: The composite combined two halves — Billbird hours/plan-vs-actual and PR analyses. The Billbird half belongs in `billbird-mcp`; the PR-side analyses remain in Gitsweeper as individual tools. Synthesising the two through one tool was a convenience born from running both behind one server; with the architecture cleaned up, callers compose at the MCP-client layer instead.

**Migration**: Invoke the underlying tools separately and compose at the client end, or keep using a custom assistant prompt that calls multiple tools per turn.

### Requirement: Surface Billbird auth and HTTP failures faithfully
**Reason**: This requirement scoped Billbird HTTP error handling — moot here once Billbird-only tools leave. The same requirement now lives in `billbird-client`'s own MCP capability.

**Migration**: The contract is unchanged from a caller perspective; it just lives in `billbird-mcp` instead of `gitsweeper mcp`.

## MODIFIED Requirements

### Requirement: Tool registry is fixed and inspectable

The set of tools advertised by the server SHALL be defined in a single registry module and SHALL be enumerable without invoking any of them. Adding or removing a tool SHALL require a code change in that module — not an env var, not a config file.

#### Scenario: Registry round-trip
- **WHEN** a developer imports the registry and lists tool names
- **THEN** the list contains exactly the five tools defined by this capability (PR throughput, first-response, classify, patterns, reconcile), in a deterministic order

### Requirement: Documentation accompanying the server

The repository SHALL include a `docs/mcp.md` page describing: an example Claude Desktop config snippet that spawns `gitsweeper mcp`, a list of the available tools with one-line descriptions, and a brief note on the read-only contract. The page SHALL include a "Billbird tools live elsewhere" pointer at the [`billbird-client`](https://github.com/MWest2020/billbird-client) package, so an operator looking for Billbird-only reads is not confused into thinking Gitsweeper should provide them.

#### Scenario: New operator follows the docs
- **WHEN** a new operator reads `docs/mcp.md`
- **THEN** they can configure Claude Desktop with the snippet, attach, and successfully invoke at least the `gitsweeper_pr_throughput` tool against an existing cache; and they are pointed at `billbird-client` for any Billbird-only read needs

### Requirement: Lazy, named configuration errors

The reconcile tool — the only Billbird-touching tool remaining in this capability — SHALL validate `BILLBIRD_API_URL` and `BILLBIRD_API_TOKEN` at invocation time. When either is missing or empty, or when the `billbird-client` optional dependency is not installed, the tool SHALL return a structured error. The server SHALL NOT refuse to start in any of these cases; Gitsweeper-only tools SHALL remain callable.

#### Scenario: Missing token, Gitsweeper-only tool still works
- **WHEN** `BILLBIRD_API_TOKEN` is unset and `gitsweeper_pr_throughput(repository="org/repo")` is invoked
- **THEN** the call succeeds against the local cache and returns analysis results

#### Scenario: Missing token, reconcile tool fails clearly
- **WHEN** `BILLBIRD_API_TOKEN` is unset and `gitsweeper_reconcile(repository="org/repo")` is invoked
- **THEN** the tool returns the structured error naming `BILLBIRD_API_TOKEN`

#### Scenario: Optional dependency missing
- **WHEN** the `billbird-client` package is not installed and `gitsweeper_reconcile(repository="org/repo")` is invoked
- **THEN** the tool returns `{"error": "billbird_client_unavailable", ...}` with a hint to `pip install gitsweeper[billbird]` or equivalent
