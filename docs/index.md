---
status: draft
last_reviewed: 2026-07-13
---

# Gitsweeper docs

Gitsweeper mines and analyses GitHub (and Forgejo/GitLab) data to surface
pull-request process metrics — time-to-merge, first-response latency,
classification, DORA, and retro signals — plus a read-only Manager-MCP server.
For installation, commands, and the full overview, see the
[README](../README.md); this `docs/` tree holds the deeper reference material.

Status: active project.

## Sections

- [reference/](reference/) — feature reference:
  - [reference/mcp.md](reference/mcp.md) — the Manager-MCP server: configuration,
    tools, and the read-only contract.
  - [reference/reconcile.md](reference/reconcile.md) — `gitsweeper reconcile`:
    commit `Time:` footers versus Billbird `/log` entries.
