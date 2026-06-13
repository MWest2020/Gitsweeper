# manager-mcp Specification

## Purpose
TBD - created by archiving change gitsweeper-billbird-mcp. Update Purpose after archive.
## Requirements
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

### Requirement: Tool — Gitsweeper PR analyses are exposed verbatim

The server SHALL expose the existing analyses from `pr-throughput-analysis`, `pr-classification`, and the `patterns` capability as MCP tools named `gitsweeper_pr_throughput`, `gitsweeper_first_response`, `gitsweeper_classify`, and `gitsweeper_patterns`. These tools SHALL NOT recompute or reformat results; they SHALL invoke the existing capability functions and return their results converted to JSON-serialisable form.

#### Scenario: PR throughput tool routes to the capability
- **WHEN** `gitsweeper_pr_throughput(repo="org/repo", since="2026-01-01")` is invoked
- **THEN** the response values are identical to those produced by `gitsweeper throughput org/repo --since 2026-01-01 --json` on the same cache state

#### Scenario: First-response tool inherits cache discipline
- **WHEN** `gitsweeper_first_response(repo="org/repo")` is invoked and the cache lacks first-response data for some PRs
- **THEN** the tool errors with a structured message asking the operator to run `gitsweeper fetch` and `gitsweeper first-response` first, mirroring the CLI's behaviour — the MCP server SHALL NOT silently issue many GitHub API calls

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
- **THEN** the list contains exactly the five tools defined by this capability (PR throughput, first-response, classify, patterns, reconcile), in a deterministic order

### Requirement: Documentation accompanying the server

The repository SHALL include a `docs/mcp.md` page describing: an example Claude Desktop config snippet that spawns `gitsweeper mcp`, a list of the available tools with one-line descriptions, and a brief note on the read-only contract. The page SHALL include a "Billbird tools live elsewhere" pointer at the [`billbird-client`](https://github.com/MWest2020/billbird-client) package, so an operator looking for Billbird-only reads is not confused into thinking Gitsweeper should provide them.

#### Scenario: New operator follows the docs
- **WHEN** a new operator reads `docs/mcp.md`
- **THEN** they can configure Claude Desktop with the snippet, attach, and successfully invoke at least the `gitsweeper_pr_throughput` tool against an existing cache; and they are pointed at `billbird-client` for any Billbird-only read needs

