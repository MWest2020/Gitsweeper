## Context

Gitsweeper is a single-user Python CLI that mines GitHub PR data into a local SQLite cache and produces analyses (throughput, first-response, classification, patterns) plus a composite markdown report. Billbird is a separate Go service that records hours via `/log` and, after the in-flight `billbird-plan-command` change, will also record `/plan` entries and expose bearer-token-authenticated REST endpoints.

A manager who needs to answer questions that span both sources today does so by running CLIs in two shells and merging output mentally. The MCP protocol gives an AI client (Claude Desktop, Claude API integrations, IDE extensions) a structured way to invoke those analyses on the manager's behalf and synthesise across them. The smallest valuable artefact is a Gitsweeper-side MCP server that exposes the existing analyses plus a small, deliberate set of Billbird queries.

Cross-repo position is fixed: Billbird stays the system-of-record for hours and plans; Gitsweeper is the analytics + MCP front. The new code in this change lives entirely in Gitsweeper. The Billbird repo's contribution is the bearer-token capability already proposed in `billbird-plan-command`.

## Goals / Non-Goals

**Goals:**
- Surface manager-relevant questions across Gitsweeper and Billbird through one MCP endpoint.
- Reuse the existing Gitsweeper capabilities verbatim — no logic duplication.
- Talk to Billbird only through its REST API, never the underlying Postgres.
- Keep the tool set small and each tool's purpose self-evident from its schema.
- Fail loud and structured on configuration or auth errors so the AI client can relay them to the manager.

**Non-Goals:**
- Writes via MCP. Logging, planning, correcting, and revoking tokens stay on their canonical paths (GitHub slash commands, Billbird admin panel).
- A remote / HTTP MCP transport. stdio is sufficient for desktop AI clients today.
- Caching Billbird responses inside Gitsweeper. Hours data is small and changes daily; staleness would harm trust.
- Multi-Billbird routing. One Gitsweeper installation points at one Billbird URL.
- Cross-organisation aggregation. Each instance pair belongs to one organisation.
- Auto-installing or auto-configuring Claude Desktop. We document the config snippet; the operator copies it.

## Decisions

### Official `mcp` SDK, stdio transport

**Choice:** Use the official `mcp` Python package. Run the server over stdio. No HTTP server, no SSE.

**Rationale:** The official SDK is the boring choice — community-maintained, version-pinnable, idiomatic. stdio matches the way Claude Desktop and similar AI clients spawn MCP servers (one child process per session). HTTP transport adds an auth surface, a port binding, and a deployment concern; none of those are needed before there is a real remote consumer.

**Alternatives considered:**
- Hand-rolled MCP server: more control, but the protocol is non-trivial and the SDK already validates messages, batches notifications, and exposes the right typing primitives.
- HTTP / SSE transport: useful for hosted MCP, but no caller asks for it yet; can be added later behind the same tool registry.

### Tools return structured data, not formatted prose

**Choice:** Every tool returns a typed dictionary or list. No tool returns pre-rendered markdown except `team_status_report`, which is itself the composition product.

**Rationale:** The AI client renders the final answer for the manager. Returning prose pre-empts that and makes the tools brittle to client-side phrasing changes. Structured returns also keep the tools test-friendly — assertions compare data, not strings.

**Exception:** `team_status_report` returns a structured payload *plus* a markdown rendering of the same data, because the existing `pr-process-report` capability already produces a markdown artefact and managers value it as-is when shared into Slack or saved to disk.

### Billbird HTTP client is a shared library, not a capability

**Choice:** Put the HTTP client in `src/gitsweeper/lib/billbird_client.py` next to `lib/github_client.py`. Define typed errors (`BillbirdNotConfigured`, `BillbirdAuthError`, `BillbirdHTTPError`) and let tools translate them to MCP tool errors.

**Rationale:** Gitsweeper's project convention is *capabilities per use-case, not per layer*. "Talking to Billbird's HTTP API" is plumbing for use cases, not a use case itself. Mirroring the existing `github_client` shape keeps the library shelf coherent.

**Alternatives considered:**
- Embed HTTP code directly in each tool: copy-paste hazard, harder to test.
- Spin up a separate package: premature; one Billbird endpoint, a handful of routes.

### Configuration is lazy and tool-local

**Choice:** Validate `BILLBIRD_API_URL` and `BILLBIRD_API_TOKEN` only inside the Billbird-touching tools, never at server start. Tools that depend on them and find them missing return a structured error that names the missing variable.

**Rationale:** A manager pointing Claude Desktop at this server may legitimately want only the Gitsweeper-side tools (their own PR analyses) and never set Billbird env vars. Hard-failing at start would force every install to have Billbird credentials, which contradicts the additive intent of this change. Failing per-tool when invoked keeps both halves usable in isolation.

**Alternatives considered:**
- Fail-fast at startup: simpler operationally, but penalises the half-installed setup.
- Treat missing config as "tool unavailable, hide it": confusing — managers cannot diagnose why a tool they saw documented is missing.

### Bearer token only — no fallback auth paths

**Choice:** The Billbird client supports `Authorization: Bearer <token>` only. No session-cookie auth, no GitHub OAuth flow. If the token is invalid or revoked, surface the Billbird 401 verbatim.

**Rationale:** Bearer-token is the only auth path designed for non-browser callers. Adding a fallback would invite holding raw OAuth secrets in a CLI process. Reflecting Billbird's 401 lets the manager (via the AI client) understand whether the issue is token expiry vs missing org membership.

### Tool set is deliberately small

**Choice:** Nine tools, each tied to a specific manager question. No "list everything" or "get one by ID" tools, no admin tools.

**Rationale:** MCP tools advertised to a language model become surface area the model can choose from. A bloated registry leads to wrong-tool picks and noisier behaviour. Each tool here answers a question a manager actually asks (variance to plan, who logged where, how is PR flow). If a manager wants raw lists, the Billbird admin panel exists.

**Alternatives considered:**
- Wrap every Billbird `/api/v1/*` endpoint: bigger surface, more confusing for the model.
- Hand-pick three tools and ship: too restrictive — the composite report needs the building blocks.

### Composite tool returns both structured and rendered output

**Choice:** `team_status_report(period, scope)` returns a dict with two top-level keys: `data` (every input the report drew from) and `markdown` (the same content rendered through the existing `report-rendering` capability + a new Billbird section). The data block is the source of truth; the markdown is a convenience.

**Rationale:** Managers ask for "the weekly status" and expect a single artefact they can share. Returning data only forces the AI client to re-render, which it will do unevenly across vendors. Returning markdown only loses the ability for the AI to reason over the underlying numbers. Both together keep the tool useful to both audiences (AI and human).

### Read-only at the MCP boundary

**Choice:** No tool in this change writes. Plan creation, plan correction, log creation, and token revocation all stay on their existing paths (GitHub comments and Billbird admin panel).

**Rationale:** Writes through an AI surface increase blast radius and trip the audit-trail design (Billbird's audit assumes every plan/log entry ties to a GitHub comment). Adding writes later is a separate change with its own risk analysis.

## Risks / Trade-offs

**[An AI client misinterprets a tool's structured data]** → Mitigation: tool schemas explicitly name units (minutes vs hours), document what counts as `active`, and never return "total hours" without a denominator (period, scope) so the model cannot drop context.

**[The bearer token leaks via env var dumps or process listings]** → Mitigation: documentation states the token equals "user-level API access to Billbird"; recommend the `mcp` server be run as the manager's own user, not a shared account. Revocation is on the Billbird side and immediate.

**[Tool registry drift between Gitsweeper CLI and MCP tools]** → Mitigation: each MCP tool calls the existing capability function directly (no copy-paste of logic). If a CLI flag changes, the tool's wrapper changes with it and a single test verifies parity for that capability.

**[`team_status_report` is heavyweight and may time out from an AI client]** → Mitigation: the tool documents its work (`--refresh` semantics from `pr-process-report` are surfaced as a `refresh: bool` parameter, default false). With `refresh=false` the tool reads cache only and returns quickly.

**[Per-tool env-var validation can surprise users]** → Mitigation: every Billbird tool's error payload names the variable and links to `docs/mcp.md`. The composite report tool checks both env vars *before* doing any work and short-circuits.

**[The official `mcp` SDK churns]** → Mitigation: pin the version in `pyproject.toml` and update deliberately in a follow-up change. The tool registry uses only the high-level decorators / `ServerSession` API so version-skew impact is contained.

## Migration Plan

This is additive. No migration. Rollback is "remove the new files and the `mcp` dependency from `pyproject.toml`"; existing commands are untouched.

## Open Questions

1. Should `team_status_report` also write its markdown to `docs/examples/` automatically when called with an `--out`-like parameter, mirroring the CLI `report` command? Current decision: no — MCP clients are not file-system managers; let the AI client present the markdown and let humans save it.
2. How are organisation-private Billbird URLs (e.g. on a VPN-only network) handled when the manager's MCP client runs on their laptop? Out of scope for this change; documented as an operator concern.
3. Should we also surface a `billbird_open_entries` tool that lists log entries lacking a plan? Worth a follow-up if managers ask for it after using the current set for a sprint.
