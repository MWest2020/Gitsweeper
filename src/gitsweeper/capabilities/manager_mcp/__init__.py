"""Manager-facing MCP server.

Exposes a deliberately small set of read-only tools that combine
Gitsweeper's PR analytics with Billbird's hours / plan / cycle-time
data. The server runs over stdio so AI clients (Claude Desktop and
similar) can spawn it as a child process.

Public surface:

- :func:`run_stdio` — entry point used by the ``gitsweeper mcp`` CLI
  command. Blocks until the parent closes stdin.
- :data:`TOOLS` — the fixed registry list. Adding or removing a tool
  is a code change here, never a runtime config.
"""

from __future__ import annotations

from gitsweeper.capabilities.manager_mcp.registry import TOOLS, tool_names
from gitsweeper.capabilities.manager_mcp.server import build_server, run_stdio

__all__ = ["TOOLS", "tool_names", "build_server", "run_stdio"]
