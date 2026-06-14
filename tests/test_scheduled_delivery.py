from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from gitsweeper import cli
from gitsweeper.capabilities import scheduled_delivery
from gitsweeper.capabilities.dora_metrics import DoraReport, Metric
from gitsweeper.capabilities.retro_signals import RetroReport
from gitsweeper.lib import storage
from gitsweeper.lib.forge.base import ForgeComment, ForgePullRequest

AUTHOR_LOGIN = "alice"


# --- report fixtures --------------------------------------------------------


def _dora(*, empty: bool = False) -> DoraReport:
    if empty:
        return DoraReport(
            repo="octocat/hello",
            period="month",
            since=None,
            merged_total=0,
            deploy_frequency=Metric(value=None, band=None, sample_size=0),
            deploy_buckets=[],
            lead_time={"median": None, "p75": None, "p90": None},
            lead_time_band=None,
            change_failure_rate=Metric(value=None, band=None, sample_size=0),
            time_to_restore=Metric(value=None, band=None, sample_size=0),
        )
    return DoraReport(
        repo="octocat/hello",
        period="month",
        since=None,
        merged_total=10,
        deploy_frequency=Metric(value=0.5, band="High", sample_size=10),
        deploy_buckets=[("2026-06", 10)],
        lead_time={"median": 2.0, "p75": 4.0, "p90": 6.0},
        lead_time_band="High",
        change_failure_rate=Metric(value=0.2, band="High", sample_size=10),
        time_to_restore=Metric(value=0.5, band="High", sample_size=2),
    )


def _retro(*, empty: bool = False) -> RetroReport:
    if empty:
        return RetroReport(
            repo="octocat/hello",
            since=None,
            stale_days=14,
            prs_considered=0,
            stale_open=[],
            long_threads=[],
            friction=[],
            tech_debt=[],
            tech_debt_total=0,
            smooth=[],
        )
    return RetroReport(
        repo="octocat/hello",
        since=None,
        stale_days=14,
        prs_considered=20,
        stale_open=[3, 7],
        long_threads=[(5, 12)],
        friction=[(8, 2)],
        tech_debt=[(9, 4)],
        tech_debt_total=4,
        smooth=[1, 2],
    )


def _meta() -> dict:
    return {
        "repo": "octocat/hello",
        "window": "all time",
        "generated_at": "2026-06-14T00:00:00Z",
    }


# --- Block Kit structure ----------------------------------------------------


def test_blockkit_has_expected_block_types() -> None:
    payload = scheduled_delivery.build_blockkit(_dora(), _retro(), _meta())
    types = [b["type"] for b in payload["blocks"]]
    assert types == ["header", "section", "section", "divider", "context"]
    assert payload["blocks"][0]["text"]["text"] == "DORA + retro — octocat/hello"


def test_blockkit_is_json_serializable() -> None:
    payload = scheduled_delivery.build_blockkit(_dora(), _retro(), _meta())
    # Round-trips with no error and preserves structure.
    assert json.loads(json.dumps(payload)) == payload


def test_blockkit_references_prs_as_plain_numbers() -> None:
    payload = scheduled_delivery.build_blockkit(_dora(), _retro(), _meta())
    blob = json.dumps(payload)
    assert "#3" in blob and "#5" in blob and "#8" in blob


# --- markdown ---------------------------------------------------------------


def test_markdown_present_and_sane() -> None:
    md = scheduled_delivery.build_markdown(_dora(), _retro(), _meta())
    assert "# DORA + retro — octocat/hello" in md
    assert "## DORA" in md
    assert "## Retro signals" in md
    assert "Deployment frequency" in md
    assert "#3" in md


# --- team-level: no author leaks --------------------------------------------


def test_both_formats_have_no_author_leak() -> None:
    dora, retro, meta = _dora(), _retro(), _meta()
    blob = json.dumps(scheduled_delivery.build_blockkit(dora, retro, meta))
    md = scheduled_delivery.build_markdown(dora, retro, meta)
    for rendered in (blob, md):
        assert AUTHOR_LOGIN not in rendered
        assert "@" not in rendered
        assert "login" not in rendered.lower()


# --- empty window -----------------------------------------------------------


def test_empty_window_blockkit_valid() -> None:
    payload = scheduled_delivery.build_blockkit(
        _dora(empty=True), _retro(empty=True), _meta()
    )
    types = [b["type"] for b in payload["blocks"]]
    assert types == ["header", "section", "section", "divider", "context"]
    blob = json.dumps(payload)
    assert "No merged PRs" in blob
    assert "No retro signals" in blob


def test_empty_window_markdown_valid() -> None:
    md = scheduled_delivery.build_markdown(_dora(empty=True), _retro(empty=True), _meta())
    assert "No merged PRs" in md
    assert "No retro signals" in md


# --- post_to_webhook against a fake transport -------------------------------


def test_post_to_webhook_posts_payload() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(handler)
    payload = scheduled_delivery.build_blockkit(_dora(), _retro(), _meta())
    with httpx.Client(transport=transport) as client:
        scheduled_delivery.post_to_webhook(
            "https://hooks.slack.test/abc", payload, http_client=client
        )
    assert captured["url"] == "https://hooks.slack.test/abc"
    assert captured["body"] == payload


def test_post_to_webhook_raises_on_non_2xx() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(400, text="bad"))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(scheduled_delivery.DeliveryError):
            scheduled_delivery.post_to_webhook(
                "https://hooks.slack.test/abc", {"blocks": []}, http_client=client
            )


# --- CLI integration --------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class _FakeProvider:
    """Minimal ForgeProvider returning canned comments per PR number."""

    def __init__(self, comments_by_number: dict[int, list[ForgeComment]] | None = None):
        self._by_number = comments_by_number or {}

    def list_issue_comments(self, owner, repo, issue_number):
        return iter(self._by_number.get(issue_number, []))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


def _seed(db: Path) -> None:
    conn = storage.connect(db)
    storage.init_schema(conn)
    repo_id = storage.get_or_create_repository(conn, "octocat", "hello")
    storage.upsert_pull_requests(
        conn,
        repo_id,
        [
            ForgePullRequest(
                number=1,
                state="closed",
                created_at="2026-06-01T00:00:00Z",
                merged_at="2026-06-02T00:00:00Z",
                closed_at="2026-06-02T00:00:00Z",
                author=AUTHOR_LOGIN,
                raw={"number": 1, "title": "feat: thing", "user": {"login": AUTHOR_LOGIN}},
            ),
            ForgePullRequest(
                number=2,
                state="closed",
                created_at="2026-06-01T00:00:00Z",
                merged_at="2026-06-08T00:00:00Z",
                closed_at="2026-06-08T00:00:00Z",
                author=AUTHOR_LOGIN,
                raw={"number": 2, "title": "fix: bug", "user": {"login": AUTHOR_LOGIN}},
            ),
        ],
    )
    conn.close()


@pytest.fixture
def patched_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "get_forge_provider", lambda **kw: _FakeProvider())


def test_deliver_help_shows_flags_not_author(runner: CliRunner) -> None:
    result = runner.invoke(cli.app, ["deliver", "--help"])
    assert result.exit_code == 0
    out = result.stdout
    assert "--format" in out
    assert "--out" in out
    assert "--post" in out
    assert "--forge" in out
    assert "--stale-days" in out
    assert "--author" not in out


def test_deliver_stale_days_passes_through(
    runner: CliRunner, tmp_path: Path, patched_provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `deliver` must forward --stale-days into the retro computation so it
    # agrees with the `retro` command rather than hardcoding the default.
    db = tmp_path / "gs.sqlite"
    _seed(db)
    seen: dict = {}
    real_build = cli.retro_signals.build_report

    def spy(*args, **kwargs):
        if "stale_days" in kwargs:
            seen["stale_days"] = kwargs["stale_days"]
        return real_build(*args, **kwargs)

    monkeypatch.setattr(cli.retro_signals, "build_report", spy)
    result = runner.invoke(
        cli.app,
        ["deliver", "octocat/hello", "--stale-days", "30", "--db-path", str(db)],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert seen["stale_days"] == 30


def test_deliver_slack_stdout(runner: CliRunner, tmp_path: Path, patched_provider) -> None:
    db = tmp_path / "gs.sqlite"
    _seed(db)
    result = runner.invoke(cli.app, ["deliver", "octocat/hello", "--db-path", str(db)])
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    types = [b["type"] for b in payload["blocks"]]
    assert types == ["header", "section", "section", "divider", "context"]


def test_deliver_markdown_stdout(
    runner: CliRunner, tmp_path: Path, patched_provider
) -> None:
    db = tmp_path / "gs.sqlite"
    _seed(db)
    result = runner.invoke(
        cli.app,
        ["deliver", "octocat/hello", "--format", "markdown", "--db-path", str(db)],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "# DORA + retro — octocat/hello" in result.stdout


def test_deliver_team_level_no_author_in_output(
    runner: CliRunner, tmp_path: Path, patched_provider
) -> None:
    db = tmp_path / "gs.sqlite"
    _seed(db)
    for fmt in ("slack", "markdown"):
        result = runner.invoke(
            cli.app,
            ["deliver", "octocat/hello", "--format", fmt, "--db-path", str(db)],
        )
        assert result.exit_code == 0, result.stdout + result.stderr
        assert AUTHOR_LOGIN not in result.stdout


def test_deliver_out_writes_file_no_webhook(
    runner: CliRunner, tmp_path: Path, patched_provider
) -> None:
    db = tmp_path / "gs.sqlite"
    _seed(db)
    out_file = tmp_path / "msg.json"
    result = runner.invoke(
        cli.app,
        ["deliver", "octocat/hello", "--out", str(out_file), "--db-path", str(db)],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    content = out_file.read_text(encoding="utf-8")
    json.loads(content)  # valid JSON
    assert "hooks.slack" not in content


def test_deliver_post_without_webhook_errors_no_call(
    runner: CliRunner, tmp_path: Path, patched_provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "gs.sqlite"
    _seed(db)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)

    called: list = []
    monkeypatch.setattr(
        scheduled_delivery, "post_to_webhook", lambda *a, **k: called.append(a)
    )
    result = runner.invoke(
        cli.app, ["deliver", "octocat/hello", "--post", "--db-path", str(db)]
    )
    assert result.exit_code != 0
    assert "SLACK_WEBHOOK_URL" in (result.stdout + result.stderr)
    assert called == []


def test_deliver_post_uses_fake_transport(
    runner: CliRunner, tmp_path: Path, patched_provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "gs.sqlite"
    _seed(db)
    webhook = "https://hooks.slack.test/T000/B000/xyz"
    monkeypatch.setenv("SLACK_WEBHOOK_URL", webhook)

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(handler)

    # Route the CLI's webhook POST through a fake transport — proves the POST
    # happens and that no real network is touched.
    real_post = scheduled_delivery.post_to_webhook

    def routed(url, payload, *, http_client=None):
        with httpx.Client(transport=transport) as client:
            return real_post(url, payload, http_client=client)

    monkeypatch.setattr(scheduled_delivery, "post_to_webhook", routed)

    result = runner.invoke(
        cli.app, ["deliver", "octocat/hello", "--post", "--db-path", str(db)]
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert captured["url"] == webhook
    assert [b["type"] for b in captured["body"]["blocks"]] == [
        "header",
        "section",
        "section",
        "divider",
        "context",
    ]
    # Webhook URL never leaks into the rendered stdout payload.
    assert webhook not in result.stdout
