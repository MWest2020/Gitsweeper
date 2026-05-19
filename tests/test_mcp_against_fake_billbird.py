"""End-to-end MCP-against-Billbird tests.

Spins up an in-process HTTP server that mimics Billbird's
``/api/v1/*`` routes, points ``BILLBIRD_API_URL`` at it, and exercises
the MCP tools that touch Billbird. Proves the entire wire-level
contract: schema parsing, scope echoing, the structured error path on
non-200 responses, and the composite ``team_status_report`` data
shape.

The fake Billbird is deliberately minimal — just enough surface to
make every Billbird-touching tool happy. It is not a re-implementation
of Billbird; it is a contract test for our client.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from gitsweeper.capabilities.manager_mcp.tools import (
    billbird_hours_summary,
    billbird_plan_vs_actual,
    billbird_recent_activity,
    team_status_report,
)


class _FakeBillbird(BaseHTTPRequestHandler):
    """Tiny stand-in for Billbird. Responds to the routes our client
    exercises, returns canned data, and refuses anything that doesn't
    look like an authenticated request."""

    # Populated per-test via the wrapper below.
    time_entries: list[dict] = []
    plans: list[dict] = []
    plan_vs_actual_rows: dict[tuple[str, int], dict] = {}
    clients: list[dict] = []
    expected_token: str = "bb_test_token"

    def log_message(self, *args, **kwargs):  # noqa: D401 - silence stdlib logging
        pass

    def do_GET(self):  # noqa: N802 - stdlib API
        auth = self.headers.get("Authorization", "")
        if auth != f"Bearer {self.expected_token}":
            self._send(401, {"error": "auth"})
            return

        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/v1/time-entries":
            self._send(200, self.time_entries)
            return
        if path == "/api/v1/plans":
            self._send(200, self.plans)
            return
        if path == "/api/v1/clients":
            self._send(200, self.clients)
            return
        if path.startswith("/api/v1/issues/"):
            # /api/v1/issues/{owner}/{repo}/{number}/plan-vs-actual
            # ['', 'api', 'v1', 'issues', '<owner>', '<repo>', '<num>', 'plan-vs-actual']
            parts = path.split("/")
            if len(parts) == 8 and parts[-1] == "plan-vs-actual":
                owner, repo, num = parts[4], parts[5], int(parts[6])
                key = (f"{owner}/{repo}", num)
                row = self.plan_vs_actual_rows.get(key, {
                    "repository": f"{owner}/{repo}",
                    "issue_number": num,
                    "planned_minutes": 0,
                    "logged_minutes": 0,
                    "variance_minutes": 0,
                    "status": "no_plan",
                })
                self._send(200, row)
                return
        # Anything we forgot looks like a 404
        _ = query
        self._send(404, {"error": "not_found", "path": path})

    def _send(self, status: int, body: Any) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def fake_billbird(monkeypatch):
    """Start the fake Billbird on an ephemeral port and configure the
    env vars that MCP tools read on each call."""
    server = HTTPServer(("127.0.0.1", 0), _FakeBillbird)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("BILLBIRD_API_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("BILLBIRD_API_TOKEN", _FakeBillbird.expected_token)
    try:
        yield _FakeBillbird
    finally:
        server.shutdown()
        thread.join(timeout=5)


# --- Tests ---------------------------------------------------------------


def test_hours_summary_round_trip(fake_billbird):
    fake_billbird.time_entries = [
        {"DurationMinutes": 60, "GitHubUsername": "alice", "Repository": "org/r1", "IssueNumber": 1},
        {"DurationMinutes": 90, "GitHubUsername": "alice", "Repository": "org/r1", "IssueNumber": 2},
        {"DurationMinutes": 30, "GitHubUsername": "bob", "Repository": "org/r1", "IssueNumber": 1},
    ]

    out = billbird_hours_summary(period="2026-04", group_by="user")
    assert "error" not in out, out
    assert out["unit"] == "minutes"
    assert out["total_minutes"] == 180
    assert out["entry_count"] == 3
    groups = {g["group"]: g["minutes"] for g in out["groups"]}
    assert groups == {"alice": 150, "bob": 30}
    assert out["period"]["label"] == "2026-04"
    assert out["scope"]["group_by"] == "user"


def test_hours_summary_group_by_repo(fake_billbird):
    fake_billbird.time_entries = [
        {"DurationMinutes": 60, "Repository": "org/r1", "GitHubUsername": "a"},
        {"DurationMinutes": 60, "Repository": "org/r2", "GitHubUsername": "a"},
    ]
    out = billbird_hours_summary(period="last-7d", group_by="repo")
    groups = {g["group"]: g["minutes"] for g in out["groups"]}
    assert groups == {"org/r1": 60, "org/r2": 60}


def test_plan_vs_actual_aggregates_per_issue(fake_billbird):
    fake_billbird.plans = [
        {"Repository": "org/r1", "IssueNumber": 1, "DurationMinutes": 480, "status": "active"},
        {"Repository": "org/r1", "IssueNumber": 2, "DurationMinutes": 240, "status": "active"},
    ]
    fake_billbird.plan_vs_actual_rows = {
        ("org/r1", 1): {
            "repository": "org/r1", "issue_number": 1,
            "planned_minutes": 480, "logged_minutes": 180,
            "variance_minutes": -300, "status": "under",
        },
        ("org/r1", 2): {
            "repository": "org/r1", "issue_number": 2,
            "planned_minutes": 240, "logged_minutes": 480,
            "variance_minutes": 240, "status": "over",
        },
    }
    out = billbird_plan_vs_actual(period="2026-04")
    assert "error" not in out, out
    assert out["count"] == 2
    # Highest absolute variance first.
    assert out["issues"][0]["issue_number"] == 1  # |-300| > |240|
    assert out["issues"][0]["status"] == "under"
    assert out["issues"][1]["status"] == "over"


def test_plan_vs_actual_filters_by_status(fake_billbird):
    fake_billbird.plans = [
        {"Repository": "org/r1", "IssueNumber": 1, "DurationMinutes": 480, "status": "active"},
        {"Repository": "org/r1", "IssueNumber": 2, "DurationMinutes": 240, "status": "active"},
    ]
    fake_billbird.plan_vs_actual_rows = {
        ("org/r1", 1): {
            "repository": "org/r1", "issue_number": 1,
            "planned_minutes": 480, "logged_minutes": 600,
            "variance_minutes": 120, "status": "over",
        },
        ("org/r1", 2): {
            "repository": "org/r1", "issue_number": 2,
            "planned_minutes": 240, "logged_minutes": 240,
            "variance_minutes": 0, "status": "on_target",
        },
    }
    out = billbird_plan_vs_actual(status="over")
    assert out["count"] == 1
    assert out["issues"][0]["status"] == "over"


def test_recent_activity_combines_logs_and_plans(fake_billbird):
    fake_billbird.time_entries = [
        {"ID": 1, "CreatedAt": "2026-05-18T09:00:00Z", "DurationMinutes": 60},
    ]
    fake_billbird.plans = [
        {"ID": 99, "CreatedAt": "2026-05-18T10:00:00Z", "DurationMinutes": 480},
    ]
    out = billbird_recent_activity(since="2026-05-18T00:00:00Z")
    assert out["count"] == 2
    types = [e["type"] for e in out["entries"]]
    # plan is newer, so it should come first
    assert types == ["plan", "log"]


def test_team_status_report_no_repo_skips_pr_sections(fake_billbird):
    fake_billbird.time_entries = []
    fake_billbird.plans = []
    out = team_status_report(period="2026-04", scope={"client": "ACME"})
    assert "data" in out
    assert "markdown" in out
    data = out["data"]
    assert data["pr_throughput"] == {"skipped": "no repository in scope"}
    assert data["first_response"] == {"skipped": "no repository in scope"}
    assert "# Team status report" in out["markdown"]


def test_bogus_token_surfaces_http_error(fake_billbird, monkeypatch):
    monkeypatch.setenv("BILLBIRD_API_TOKEN", "bb_wrong_token")
    fake_billbird.time_entries = []  # would otherwise be reachable
    out = billbird_hours_summary(period="2026-04", group_by="user")
    assert out["error"] == "billbird_http_error"
    assert out["status"] == 401
    assert out["hint"] == "auth"


def test_invalid_period_returns_invalid_argument(fake_billbird):
    out = billbird_hours_summary(period="bad", group_by="user")
    assert out["error"] == "invalid_argument"
    assert out["field"] == "period"
