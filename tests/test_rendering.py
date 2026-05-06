from __future__ import annotations

import io
import json

import pytest

from gitsweeper.lib.rendering import (
    AnalysisResult,
    CLITableRenderer,
    JSONRenderer,
    get_renderer,
)


@pytest.fixture
def sample_result() -> AnalysisResult:
    return AnalysisResult(
        title="time-to-merge (days)",
        columns=["metric", "value"],
        rows=[
            ["count", 4],
            ["median", 3.5],
            ["p95", 14.2],
            ["max", None],
        ],
        metadata={"repo": "octocat/hello-world", "since": None},
    )


def test_get_renderer_unknown_name_raises() -> None:
    with pytest.raises(ValueError):
        get_renderer("yaml")


def test_cli_table_renderer_includes_values(sample_result: AnalysisResult) -> None:
    out = io.StringIO()
    CLITableRenderer().render(sample_result, stream=out)
    rendered = out.getvalue()
    assert "time-to-merge (days)" in rendered
    assert "median" in rendered
    assert "3.50" in rendered          # float formatting
    assert "p95" in rendered
    assert "14.20" in rendered
    assert "—" in rendered              # None placeholder
    assert "octocat/hello-world" in rendered  # metadata footer


def test_json_renderer_emits_valid_json_only(sample_result: AnalysisResult) -> None:
    out = io.StringIO()
    JSONRenderer().render(sample_result, stream=out)
    text = out.getvalue()
    payload = json.loads(text)  # must be valid JSON, no banners
    assert payload["title"] == "time-to-merge (days)"
    assert payload["columns"] == ["metric", "value"]
    assert payload["rows"][1] == ["median", 3.5]
    assert payload["rows"][3] == ["max", None]
    assert payload["metadata"]["repo"] == "octocat/hello-world"


def test_json_and_table_render_same_semantic_content(sample_result: AnalysisResult) -> None:
    table_out = io.StringIO()
    CLITableRenderer().render(sample_result, stream=table_out)
    json_out = io.StringIO()
    JSONRenderer().render(sample_result, stream=json_out)
    payload = json.loads(json_out.getvalue())
    # Every cell value must surface in the table, in some form.
    for row in payload["rows"]:
        for cell in row:
            if cell is None:
                assert "—" in table_out.getvalue()
            elif isinstance(cell, float):
                assert f"{cell:.2f}" in table_out.getvalue()
            else:
                assert str(cell) in table_out.getvalue()


def test_get_renderer_returns_correct_implementations() -> None:
    assert isinstance(get_renderer("table"), CLITableRenderer)
    assert isinstance(get_renderer("json"), JSONRenderer)
