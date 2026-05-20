"""MCP server wiring.

Builds an ``mcp.Server`` from the fixed registry and runs it over stdio.
The transport is intentionally stdio-only: AI clients (Claude Desktop
and similar) spawn the server as a child process and communicate over
the pipe. Adding HTTP transport later is a follow-up change; nothing in
this module assumes stdio elsewhere.
"""

from __future__ import annotations

import json
from typing import Any

from gitsweeper.capabilities.manager_mcp.registry import TOOLS, find


def build_server():
    """Construct the underlying MCP Server with every tool registered.

    Imported lazily so the rest of the module (and the test suite) can
    work without the optional ``mcp`` dependency installed.
    """
    from mcp.server import Server
    from mcp.types import TextContent, Tool

    server: Server = Server("gitsweeper-mcp")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=spec.name,
                description=spec.description,
                inputSchema=spec.input_schema,
            )
            for spec in TOOLS
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        spec = find(name)
        if spec is None:
            payload = {"error": "unknown_tool", "name": name}
        else:
            try:
                payload = spec.handler(**(arguments or {}))
            except TypeError as exc:
                payload = {"error": "invalid_argument", "hint": str(exc)}
            except Exception as exc:  # pragma: no cover - defensive
                payload = {"error": "internal_error", "hint": repr(exc)}
        return [TextContent(type="text", text=json.dumps(payload, default=str))]

    return server


def run_stdio() -> None:
    """Run the MCP server over stdio until stdin closes.

    Blocking call. Used as the body of the ``gitsweeper mcp`` CLI
    command.
    """
    import asyncio

    from mcp.server.stdio import stdio_server

    async def _main() -> None:
        server = build_server()
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_main())
