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

Nine tools, registered in this fixed order:

| Tool | What it returns |
|---|---|
| `team_status_report` | Composite report: hours + plan-vs-actual + PR analyses. Returns both `data` and a `markdown` rendering. |
| `billbird_hours_summary` | Aggregate active log minutes for a period, grouped by user / client / repo / issue. |
| `billbird_plan_vs_actual` | Per-issue variance between active plan and active logs. Ordered by absolute variance descending. |
| `billbird_cycle_time` | Stub. Returns `not_implemented` until Billbird exposes the cycle-time REST endpoint. |
| `billbird_recent_activity` | Recent log and plan entries combined, type-tagged, newest first. |
| `gitsweeper_pr_throughput` | Time-to-merge percentiles for a repo. |
| `gitsweeper_first_response` | Time-to-first-response percentiles. Cache-only — never fetches. |
| `gitsweeper_classify` | Self-pulled vs maintainer-closed for closed-unmerged PRs. Cache-only. |
| `gitsweeper_patterns` | Day-of-week and hour-of-day patterns for submissions and responses. |

Every numeric field in a response carries an explicit `unit` (`minutes`, `hours`, `days`, `count`), and Billbird-touching responses echo back the resolved `period` block. Tools never return a bare "total" without naming the scope.

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

## What this server intentionally does not do

- **Writes.** Plan creation, log correction, and token management are all on their canonical paths.
- **HTTP transport.** stdio is enough for desktop AI clients today.
- **Caching of Billbird responses.** Hours data changes daily and is small; staleness would harm trust.
- **Multi-Billbird routing.** One Gitsweeper installation points at one Billbird instance.
- **Auto-installing or configuring Claude Desktop.** The snippet above is the only setup; copy it.
