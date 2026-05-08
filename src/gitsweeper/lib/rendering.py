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


class MarkdownRenderer:
    def render(self, result: AnalysisResult, stream: TextIO | None = None) -> None:
        out = stream or sys.stdout
        out.write(f"## {result.title}\n\n")
        if result.columns and result.rows:
            header = "| " + " | ".join(result.columns) + " |"
            sep = "| " + " | ".join("---" for _ in result.columns) + " |"
            out.write(header + "\n")
            out.write(sep + "\n")
            for row in result.rows:
                cells = [_format_md_cell(v) for v in row]
                out.write("| " + " | ".join(cells) + " |\n")
        if result.metadata:
            out.write("\n")
            for key, value in result.metadata.items():
                out.write(f"- **{key}**: {_format_md_cell(value)}\n")
        out.write("\n")


_RENDERERS: dict[str, type[Renderer]] = {
    "table": CLITableRenderer,
    "json": JSONRenderer,
    "markdown": MarkdownRenderer,
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


def _format_md_cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.2f}"
    text = str(value)
    return text.replace("|", "\\|")


def render_line_svg(
    rows: list[dict],
    *,
    x: str,
    y: str,
    by: str | None = None,
    title: str = "",
    width: float = 8.0,
    height: float = 3.0,
) -> str:
    """Render a long-format list of dicts as a multi-line SVG chart.

    Args:
        rows: list of records, each with at least keys `x`, `y`, and
            (if `by` is given) `by`.
        x: dict key for the x-axis (string labels are kept as
            categorical, in input order).
        y: dict key for the y-axis (numeric values; rows where the
            value is None are skipped).
        by: optional dict key whose distinct values become individual
            lines. If None, a single line is plotted.
        title: chart title.
        width, height: figure size in inches.
    Returns:
        SVG markup as a string.
    """
    import io as _io

    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    if not rows:
        label = title or "empty chart"
        return (
            "<svg xmlns='http://www.w3.org/2000/svg' role='img' "
            f"aria-label='{label}'>"
            "<text x='10' y='20'>(no data)</text></svg>"
        )

    series: dict[str, list[tuple[str, float]]] = {}
    x_order: list[str] = []
    seen_x: set[str] = set()
    for r in rows:
        if r.get(y) is None:
            continue
        key = r[by] if by else "value"
        series.setdefault(key, []).append((str(r[x]), float(r[y])))
        if str(r[x]) not in seen_x:
            seen_x.add(str(r[x]))
            x_order.append(str(r[x]))

    if not series:
        label = title or "empty chart"
        return (
            "<svg xmlns='http://www.w3.org/2000/svg' role='img' "
            f"aria-label='{label}'>"
            "<text x='10' y='20'>(no data)</text></svg>"
        )

    fig, ax = plt.subplots(figsize=(width, height))
    x_indices = {label: i for i, label in enumerate(x_order)}
    for label, points in sorted(series.items()):
        points.sort(key=lambda pair: x_indices.get(pair[0], 1_000_000))
        xs = [x_indices[p[0]] for p in points]
        ys = [p[1] for p in points]
        ax.plot(xs, ys, marker="o", label=label)
    ax.set_xticks(range(len(x_order)))
    ax.set_xticklabels(x_order, rotation=45, ha="right", fontsize=8)
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.set_title(title)
    if by is not None:
        ax.legend(fontsize=8, loc="best")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    buffer = _io.StringIO()
    fig.savefig(buffer, format="svg", bbox_inches="tight")
    plt.close(fig)
    return buffer.getvalue()


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")
