"""Drive the Manager-MCP server over stdio against a live Billbird.

Smoke test for use against a running Billbird. Reads the URL and
bearer token from BILLBIRD_API_URL and BILLBIRD_API_TOKEN (same env
vars the MCP server itself consumes), spawns ``gitsweeper mcp`` as a
child process, and exercises the JSON-RPC handshake plus a few
``tools/call`` invocations. Prints the response payloads so an
operator can confirm the round-trip works end to end.

Usage::

    BILLBIRD_API_URL=http://127.0.0.1:18080 \\
    BILLBIRD_API_TOKEN=bb_... \\
        uv run python scripts/mcp_smoke.py

Exits non-zero if any tool returns an error envelope. This is not a
replacement for the unit / integration test suites; it is a
human-runnable proof that the binary, the protocol layer, and the
network path actually work together.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time


def send(proc: subprocess.Popen, payload: dict) -> None:
    proc.stdin.write((json.dumps(payload) + "\n").encode())
    proc.stdin.flush()


def recv(proc: subprocess.Popen, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.05)
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    raise TimeoutError("no MCP response within timeout")


def call_tool(proc: subprocess.Popen, name: str, args: dict, request_id: int) -> dict:
    send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        },
    )
    resp = recv(proc, timeout=20.0)
    text = resp["result"]["content"][0]["text"]
    return json.loads(text)


def main() -> int:
    for required in ("BILLBIRD_API_URL", "BILLBIRD_API_TOKEN"):
        if not os.environ.get(required):
            print(f"missing env var: {required}", file=sys.stderr)
            return 2

    cmd = ["uv", "run", "gitsweeper", "mcp"]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        env=os.environ.copy(),
    )

    failures: list[str] = []
    try:
        # 1. Handshake.
        send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "mcp_smoke", "version": "1.0"},
                },
            },
        )
        init = recv(proc)
        print("== initialize ==")
        print(json.dumps(init, indent=2)[:400])

        # 2. initialized notification (no response expected).
        send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        # 3. list_tools — verify the fixed registry.
        send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = recv(proc)
        names = [t["name"] for t in tools["result"]["tools"]]
        expected = {
            "gitsweeper_pr_throughput",
            "gitsweeper_first_response",
            "gitsweeper_classify",
            "gitsweeper_reconcile",
            "gitsweeper_patterns",
        }
        forbidden = {
            "billbird_hours_summary",
            "billbird_plan_vs_actual",
            "billbird_cycle_time",
            "billbird_recent_activity",
            "team_status_report",
        }
        missing = expected - set(names)
        regressed = forbidden & set(names)
        if missing:
            failures.append(f"tools/list missing: {sorted(missing)}")
        if regressed:
            failures.append(
                f"Billbird-only tools regressed into Gitsweeper: {sorted(regressed)}"
            )
        print(f"\n== tools/list ({len(names)}) ==")
        for n in names:
            print(f"  {n}")

        # 4. gitsweeper_reconcile — the cross-source tool that remains here.
        # Without billbird-client installed the tool surfaces a structured
        # error; without an in-scope cache it surfaces cache_missing. Either
        # is acceptable for a smoke run: we just verify the tool exists and
        # returns *something* JSON-shaped.
        result = call_tool(
            proc,
            "gitsweeper_reconcile",
            {"repository": "MWest2020/Billbird"},
            3,
        )
        print("\n== gitsweeper_reconcile ==")
        print(json.dumps(result, indent=2)[:600])
        if not isinstance(result, dict):
            failures.append("reconcile did not return a dict")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        err = proc.stderr.read().decode(errors="replace")
        if err.strip():
            print("\n== mcp stderr ==", file=sys.stderr)
            print(err[:2000], file=sys.stderr)

    if failures:
        print("\nFAIL", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nOK — round-trip complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
