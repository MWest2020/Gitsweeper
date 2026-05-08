from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from gitsweeper.capabilities import dashboard, pr_throughput
from gitsweeper.lib import storage


class FakeFetchClient:
    def __init__(self, prs: list[dict]) -> None:
        self._prs = prs

    def list_pull_requests(self, owner: str, repo: str, state: str = "all") -> Iterator[dict]:
        yield from self._prs


def _pr(
    number: int,
    *,
    author: str = "alice",
    created: str = "2026-01-05T08:00:00Z",
    merged: str | None = None,
    closed: str | None = None,
) -> dict:
    return {
        "number": number,
        "state": "closed" if (merged or closed) else "open",
        "created_at": created,
        "merged_at": merged,
        "closed_at": merged or closed,
        "user": {"login": author},
    }


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = storage.connect(tmp_path / "gs.sqlite")
    storage.init_schema(c)
    return c


def _seed(conn: sqlite3.Connection, owner: str, name: str, prs: list[dict]) -> int:
    return pr_throughput.fetch_and_persist(
        conn, FakeFetchClient(prs=prs), owner, name
    ).repo_id


def test_empty_cache_raises_cache_empty(conn: sqlite3.Connection, tmp_path: Path) -> None:
    out = tmp_path / "bundle"
    with pytest.raises(dashboard.CacheEmpty):
        dashboard.publish(conn, out)
    # No partial bundle left behind
    assert not out.exists() or not any(out.iterdir())


def test_publish_writes_full_bundle_layout(conn: sqlite3.Connection, tmp_path: Path) -> None:
    _seed(conn, "ConductionNL", "openregister", [
        _pr(1, created="2026-01-05T08:00:00Z", merged="2026-01-06T08:00:00Z"),
        _pr(2, created="2026-01-12T08:00:00Z", merged="2026-01-13T08:00:00Z"),
    ])
    out = tmp_path / "bundle"
    summary = dashboard.publish(conn, out)
    assert (out / "index.html").is_file()
    assert (out / "repo" / "ConductionNL-openregister.html").is_file()
    assert (out / "data" / "timeseries.json").is_file()
    assert (out / "data" / "alerts.json").is_file()
    assert (out / "data" / "effort.json").is_file()
    assert (out / "data" / "classification.json").is_file()
    assert (out / "assets" / "style.css").is_file()
    assert "ConductionNL/openregister" in summary["repos"]


def test_index_lists_each_repo(conn: sqlite3.Connection, tmp_path: Path) -> None:
    _seed(conn, "ConductionNL", "openregister", [_pr(1, merged="2026-01-06T08:00:00Z")])
    _seed(conn, "ConductionNL", "opencatalogi", [_pr(1, merged="2026-01-06T08:00:00Z")])
    out = tmp_path / "bundle"
    dashboard.publish(conn, out)
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "ConductionNL/openregister" in index
    assert "ConductionNL/opencatalogi" in index
    assert "ConductionNL-openregister.html" in index
    assert "ConductionNL-opencatalogi.html" in index


def test_repos_filter_excludes_others(conn: sqlite3.Connection, tmp_path: Path) -> None:
    _seed(conn, "ConductionNL", "openregister", [_pr(1, merged="2026-01-06T08:00:00Z")])
    _seed(conn, "ConductionNL", "opencatalogi", [_pr(1, merged="2026-01-06T08:00:00Z")])
    out = tmp_path / "bundle"
    dashboard.publish(
        conn, out, repos=[("ConductionNL", "openregister")]
    )
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "ConductionNL/openregister" in index
    assert "ConductionNL/opencatalogi" not in index
    assert (out / "repo" / "ConductionNL-openregister.html").is_file()
    assert not (out / "repo" / "ConductionNL-opencatalogi.html").exists()


def test_no_remote_references_in_html(conn: sqlite3.Connection, tmp_path: Path) -> None:
    """No <script> tags and no remote URLs in remote-loading attributes
    (script src, link href, img src, iframe src). The SVG namespace
    URI (xmlns="http://www.w3.org/2000/svg") is fine — it is not a
    network request, just an XML namespace identifier."""
    import re
    _seed(conn, "o", "r", [_pr(1, merged="2026-01-06T08:00:00Z")])
    out = tmp_path / "bundle"
    dashboard.publish(conn, out)
    pattern = re.compile(
        r'<(?:script|link|img|iframe)[^>]*\s(?:src|href)\s*=\s*"(https?://[^"]+)"',
        re.IGNORECASE,
    )
    for path in out.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert "<script" not in text.lower(), f"{path} has a <script> tag"
        remote_refs = pattern.findall(text)
        assert not remote_refs, (
            f"{path} contains remote URLs in network-loading elements: {remote_refs}"
        )


def test_data_jsons_are_machine_readable(conn: sqlite3.Connection, tmp_path: Path) -> None:
    _seed(conn, "o", "r", [_pr(1, merged="2026-01-06T08:00:00Z")])
    out = tmp_path / "bundle"
    dashboard.publish(conn, out)
    series = json.loads((out / "data" / "timeseries.json").read_text())
    assert "rows" in series and isinstance(series["rows"], list)
    alerts = json.loads((out / "data" / "alerts.json").read_text())
    assert "rows" in alerts and isinstance(alerts["rows"], list)
    effort = json.loads((out / "data" / "effort.json").read_text())
    assert "rows" in effort and isinstance(effort["rows"], list)
    classification = json.loads((out / "data" / "classification.json").read_text())
    assert isinstance(classification, list)


def test_per_repo_page_contains_charts(conn: sqlite3.Connection, tmp_path: Path) -> None:
    _seed(conn, "o", "r", [
        _pr(1, created="2026-01-05T08:00:00Z", merged="2026-01-06T08:00:00Z"),
        _pr(2, created="2026-01-12T08:00:00Z", merged="2026-01-13T08:00:00Z"),
    ])
    out = tmp_path / "bundle"
    dashboard.publish(conn, out)
    page = (out / "repo" / "o-r.html").read_text(encoding="utf-8")
    # SVG inlined directly in the page
    assert "<svg" in page
    # All four KPIs surfaced
    for kpi in ("median-time-to-merge", "median-first-response", "response-rate", "volume"):
        assert kpi in page
