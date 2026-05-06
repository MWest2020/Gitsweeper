"""Pluggable output rendering.

Renderers consume a structured `AnalysisResult` and turn it into bytes
on an output stream. They are pure presentation: no computation, no
filtering, no reordering that carries meaning.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any, Protocol, TextIO

from rich.console import Console
from rich.table import Table


@dataclass(frozen=True)
class AnalysisResult:
    title: str
    columns: list[str]
    rows: list[list[Any]]
    metadata: dict[str, Any] = field(default_factory=dict)


class Renderer(Protocol):
    def render(self, result: AnalysisResult, stream: TextIO | None = None) -> None: ...


class CLITableRenderer:
    def render(self, result: AnalysisResult, stream: TextIO | None = None) -> None:
        console = Console(file=stream or sys.stdout, soft_wrap=True)
        table = Table(title=result.title, show_lines=False)
        for col in result.columns:
            table.add_column(col)
        for row in result.rows:
            table.add_row(*[_format_cell(v) for v in row])
        console.print(table)
        if result.metadata:
            console.print()
            for key, value in result.metadata.items():
                console.print(f"[dim]{key}:[/dim] {value}")


class JSONRenderer:
    def render(self, result: AnalysisResult, stream: TextIO | None = None) -> None:
        out = stream or sys.stdout
        payload = {
            "title": result.title,
            "columns": result.columns,
            "rows": result.rows,
            "metadata": result.metadata,
        }
        json.dump(payload, out, default=_json_default, indent=2, sort_keys=False)
        out.write("\n")


_RENDERERS: dict[str, type[Renderer]] = {
    "table": CLITableRenderer,
    "json": JSONRenderer,
}


def get_renderer(name: str) -> Renderer:
    try:
        cls = _RENDERERS[name]
    except KeyError as exc:
        available = ", ".join(sorted(_RENDERERS))
        raise ValueError(f"unknown renderer {name!r}; available: {available}") from exc
    return cls()


def _format_cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")
