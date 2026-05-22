# Manager-MCP

Gitsweeper ships an MCP (Model Context Protocol) server that exposes a small, deliberate set of read-only tools an AI client (Claude Desktop and similar) can use to answer a manager's questions across two sources:

- Billbird — recorded hours, plans, and plan-vs-actual variance (via its REST API).
- Gitsweeper — pull-request throughput, first-response latency, classification, temporal patterns (via the local SQLite cache).

The server runs over stdio. The AI client spawns it as a child process and tears it down when the session ends.

## Required environment

| Variable | Required when | Description |
|---|---|---|
| `BILLBIRD_API_URL` | Any `billbird_*` tool is called | Base URL of your Billbird instance, e.g. `https://billbird.example.com` |
| `BILLBIRD_API_TOKEN` | Any `billbird_*` tool is called | A bearer token issued from Billbird's admin panel ([API tokens docs](https://github.com/MWest2020/Billbird/blob/main/docs/api-tokens.md)) |
| `GITHUB_TOKEN` | Only the `fetch`/CLI ingest paths | Not used by the MCP server itself; the Gitsweeper tools are cache-only |

The server starts even without the Billbird env vars set. Tools that need Billbird return a structured `billbird_not_configured` error when called; Gitsweeper-only tools keep working.

## Configuring Claude Desktop

Add this to your Claude Desktop configuration file (usually `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, or `%APPDATA%/Claude/claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "gitsweeper": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/Gitsweeper", "gitsweeper", "mcp"],
      "env": {
        "BILLBIRD_API_URL": "https://billbird.example.com",
        "BILLBIRD_API_TOKEN": "bb_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

Restart Claude Desktop. The tools listed below appear under the server's name.

## Available tools

Five tools, registered in this fixed order:

| Tool | What it returns |
|---|---|
| `gitsweeper_pr_throughput` | Time-to-merge percentiles for a repo. |
| `gitsweeper_first_response` | Time-to-first-response percentiles. Cache-only — never fetches. |
| `gitsweeper_classify` | Self-pulled vs maintainer-closed for closed-unmerged PRs. Cache-only. |
| `gitsweeper_reconcile` | One row per `(repo, author, issue)` cross-checking commit `Time:` footers against Billbird `/log` entries. Returns drift and a status (`aligned` / `commits_only` / `logs_only` / `over_committed` / `over_logged`). See [reconcile.md](reconcile.md). Requires the `billbird-client` optional dependency. |
| `gitsweeper_patterns` | Day-of-week and hour-of-day patterns for submissions and responses. |

Every numeric field in a response carries an explicit `unit` (`minutes`, `hours`, `days`, `count`). Tools never return a bare "total" without naming the scope.

## Billbird tools live elsewhere

If you want to query Billbird's hours / plans / cycle time directly, install [`billbird-client`](https://github.com/MWest2020/billbird-client) and point your MCP client at its `billbird-mcp` server. Gitsweeper used to host those tools, but they belong with the Billbird-only read surface — Gitsweeper is a generic analytics workbench and Billbird is one source among potentially many.

The two servers compose nicely: register both in your Claude Desktop config and you get analytics + Billbird reads under one roof, without either repo carrying a hard dependency on the other.

## Read-only contract

No tool in this capability writes. Logging time, planning, correcting, deleting, and revoking tokens all stay on their existing paths (GitHub slash commands and the Billbird admin panel). The AI surface is intentionally narrow.

When Billbird returns 401/403/404/5xx, the offending tool surfaces the upstream error as a structured response (`{"error": "billbird_http_error", "status": 401, "hint": "auth", ...}`) instead of crashing. The AI client can relay the error to the manager and let them act.

## Cache discipline

The Gitsweeper-side tools read the local SQLite cache and refuse to silently fetch. If a tool sees missing rows (no PR cache for the repo, missing first-response rows, missing close-actor rows), it returns:

```json
{
  "error": "cache_missing",
  "repository": "org/repo",
  "next_steps": ["gitsweeper fetch", "gitsweeper first-response"]
}
```

The manager (or their AI client) should run the listed CLI commands first.

## Security

The Billbird bearer token grants the same read/write access the issuing user has through the admin panel. Treat the value of `BILLBIRD_API_TOKEN` like a password:

- Store it outside the repository; do not commit it.
- Revoke it from the Billbird admin panel when it is no longer needed.
- Avoid pasting it into chat. If you do, revoke immediately afterwards.

## Smoke testing the round-trip

`scripts/mcp_smoke.py` spawns the MCP server, completes the initialise handshake, lists tools, and invokes `billbird_plan_vs_actual` and `billbird_hours_summary` against whatever Billbird the env vars point at. Useful as a smoke before a deploy or after a config change:

```bash
BILLBIRD_API_URL=http://127.0.0.1:8080 \
BILLBIRD_API_TOKEN=bb_xxxxxxxxxxxxx \
    uv run python scripts/mcp_smoke.py
```

The script exits non-zero on any tool error so it doubles as a CI-safe canary.

## What this server intentionally does not do

- **Writes.** Plan creation, log correction, and token management are all on their canonical paths.
- **HTTP transport.** stdio is enough for desktop AI clients today.
- **Caching of Billbird responses.** Hours data changes daily and is small; staleness would harm trust.
- **Multi-Billbird routing.** One Gitsweeper installation points at one Billbird instance.
- **Auto-installing or configuring Claude Desktop.** The snippet above is the only setup; copy it.
