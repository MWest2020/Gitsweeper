"""Tests for the Billbird HTTP client.

Uses pytest-httpx to mock Billbird's REST API. The point is to verify
the client's translation of HTTP status codes into typed exceptions and
that env-var-driven construction fails loud rather than emitting silent
defaults.
"""

from __future__ import annotations

import httpx
import pytest

from gitsweeper.lib.billbird_client import (
    BillbirdClient,
    BillbirdHTTPError,
    BillbirdNotConfigured,
)

BASE = "https://billbird.test"


def _make_client(httpx_mock_or_none: httpx.Client | None = None) -> BillbirdClient:
    return BillbirdClient(BASE, "bb_test", http_client=httpx_mock_or_none)


def test_from_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("BILLBIRD_API_URL", raising=False)
    monkeypatch.delenv("BILLBIRD_API_TOKEN", raising=False)
    with pytest.raises(BillbirdNotConfigured) as info:
        BillbirdClient.from_env()
    assert set(info.value.missing) == {"BILLBIRD_API_URL", "BILLBIRD_API_TOKEN"}


def test_from_env_partial_missing_names_only_that_var(monkeypatch):
    monkeypatch.setenv("BILLBIRD_API_URL", BASE)
    monkeypatch.delenv("BILLBIRD_API_TOKEN", raising=False)
    with pytest.raises(BillbirdNotConfigured) as info:
        BillbirdClient.from_env()
    assert info.value.missing == ["BILLBIRD_API_TOKEN"]


def test_time_entries_happy_path(httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/time-entries",
        json=[{"ID": 1, "DurationMinutes": 60}],
    )
    with _make_client() as bb:
        entries = bb.time_entries()
    assert entries == [{"ID": 1, "DurationMinutes": 60}]


def test_time_entries_filters_clean_none_values(httpx_mock):
    httpx_mock.add_response(json=[])
    with _make_client() as bb:
        bb.time_entries(repository="org/repo", username=None, client_id=None)
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    query = requests[0].url.query.decode()
    assert "username=None" not in query
    assert "client_id=None" not in query
    assert "repo=org" in query


def test_http_error_classifies_auth(httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/plans",
        status_code=401,
        json={"error": "invalid token"},
    )
    with _make_client() as bb:
        with pytest.raises(BillbirdHTTPError) as info:
            bb.plans()
    assert info.value.status == 401
    assert info.value.hint == "auth"


def test_http_error_classifies_not_found(httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/issues/org/repo/9999/plan-vs-actual",
        status_code=404,
        json={"error": "not found"},
    )
    with _make_client() as bb:
        with pytest.raises(BillbirdHTTPError) as info:
            bb.plan_vs_actual("org", "repo", 9999)
    assert info.value.status == 404
    assert info.value.hint == "not_found"


def test_http_error_classifies_server(httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/plans",
        status_code=503,
        text="upstream timeout",
    )
    with _make_client() as bb:
        with pytest.raises(BillbirdHTTPError) as info:
            bb.plans()
    assert info.value.status == 503
    assert info.value.hint == "server"


def test_authorization_header_set(httpx_mock):
    httpx_mock.add_response(json=[])
    with BillbirdClient(BASE, "bb_xyz") as bb:
        bb.clients()
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer bb_xyz"
