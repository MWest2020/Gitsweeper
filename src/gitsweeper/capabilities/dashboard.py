"""Static-site dashboard publisher.

Walks the cache, runs the existing analyses (kpi-timeseries,
regression-monitoring, effort-allocation, pr-classification), and
writes a self-contained HTML+SVG bundle to disk:

```
<out>/
├── index.html
├── repo/<owner>-<name>.html
├── data/{timeseries,alerts,effort,classification}.json
└── assets/style.css
```

No JavaScript, no remote references. Charts are pre-rendered SVG.
"""

from __future__ import annotations

import html
import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from gitsweeper.capabilities import (
    effort_allocation,
    kpi_timeseries,
    pr_classification,
    regression_monitoring,
)
from gitsweeper.lib import storage
from gitsweeper.lib.rendering import render_line_svg

CSS = """
:root {
  --bg: #ffffff;
  --fg: #1f2328;
  --muted: #57606a;
  --border: #d0d7de;
  --green: #1a7f37;
  --orange: #bf8700;
  --red: #cf222e;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", sans-serif;
  color: var(--fg);
  background: var(--bg);
  margin: 0;
  padding: 2rem;
  max-width: 1100px;
  margin-left: auto;
  margin-right: auto;
}
h1 { font-size: 1.6rem; }
h2 { font-size: 1.25rem; margin-top: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 0.25rem; }
h3 { font-size: 1.05rem; margin-top: 1.5rem; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td {
  border: 1px solid var(--border);
  padding: 0.4rem 0.6rem;
  text-align: left;
  font-size: 0.9rem;
}
th { background: #f6f8fa; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.alert-up { background: #ffebe9; }
.alert-down { background: #fff8c5; }
.muted { color: var(--muted); font-size: 0.85rem; }
.pill {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 600;
}
.pill.ok { background: #dafbe1; color: var(--green); }
.pill.warn { background: #fff5e6; color: var(--orange); }
.pill.alert { background: #ffebe9; color: var(--red); }
.chart { margin: 1rem 0; }
.chart svg { max-width: 100%; height: auto; }
a { color: #0969da; text-decoration: none; }
a:hover { text-decoration: underline; }
nav { font-size: 0.9rem; margin-bottom: 1rem; }
""".strip()


class CacheEmpty(RuntimeError):
    pass


def publish(
    conn: sqlite3.Connection,
    out_dir: Path,
    *,
    repos: Sequence[tuple[str, str]] | None = None,
    since: str | None = None,
    baseline_periods: int = 12,
    threshold_sigma: float = 2.0,
) -> dict:
    """Write the bundle. Returns a small summary dict for callers /
    tests."""
    available = conn.execute(
        "SELECT id, owner, name FROM repositories ORDER BY owner, name"
    ).fetchall()
    target = (
        {(o.lower(), n.lower()) for (o, n) in repos} if repos is not None else None
    )
    selected = []
    for r in available:
        if target is None or (r["owner"].lower(), r["name"].lower()) in target:
            selected.append(r)
    if not selected:
        raise CacheEmpty(
            "No repositories in cache match the requested scope. "
            "Run `gitsweeper fetch` (or check --repos) first."
        )
    pr_count = conn.execute(
        f"SELECT COUNT(*) FROM pull_requests WHERE repo_id IN ({','.join('?' * len(selected))})",
        [int(r["id"]) for r in selected],
    ).fetchone()[0]
    if pr_count == 0:
        raise CacheEmpty(
            "Cache contains no pull requests for the selected repositories. "
            "Run `gitsweeper fetch` first."
        )

    out_dir = Path(out_dir)
    (out_dir / "repo").mkdir(parents=True, exist_ok=True)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)
    (out_dir / "assets" / "style.css").write_text(CSS, encoding="utf-8")

    repo_pairs = [(r["owner"], r["name"]) for r in selected]
    series = kpi_timeseries.compute_kpi_timeseries(
        conn,
        kpis=("median-time-to-merge", "median-first-response", "response-rate", "volume"),
        period="iso-week",
        since=since,
        repos=repo_pairs,
    )
    alerts = regression_monitoring.compute_regression_alerts(
        conn,
        kpis=("median-time-to-merge", "median-first-response", "response-rate", "volume"),
        baseline_periods=baseline_periods,
        threshold_sigma=threshold_sigma,
        since=since,
        repos=repo_pairs,
    )
    effort = effort_allocation.compute_effort_allocation(
        conn, since=since, repos=repo_pairs
    )
    per_repo_classification: list[dict] = []
    for owner, name in repo_pairs:
        repo_id = storage.get_or_create_repository(conn, owner, name)
        result = pr_classification.compute_classification(
            conn, repo_id, owner, name
        )
        per_repo_classification.append({
            "repo": f"{owner}/{name}",
            "title": result.title,
            "rows": result.rows,
        })

    _write_json(out_dir / "data" / "timeseries.json", _result_to_payload(series))
    _write_json(out_dir / "data" / "alerts.json", _result_to_payload(alerts))
    _write_json(out_dir / "data" / "effort.json", _result_to_payload(effort))
    _write_json(out_dir / "data" / "classification.json", per_repo_classification)

    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_index(
        out_dir, repo_pairs, series, alerts, effort,
        since=since, baseline_periods=baseline_periods,
        threshold_sigma=threshold_sigma, generated_at=generated_at,
    )
    for owner, name in repo_pairs:
        _write_repo_page(
            out_dir, owner, name, series, alerts, effort,
            classification=next(
                (c for c in per_repo_classification if c["repo"] == f"{owner}/{name}"),
                None,
            ),
            generated_at=generated_at,
        )

    return {
        "out_dir": str(out_dir),
        "repos": [f"{o}/{n}" for o, n in repo_pairs],
        "series_rows": len(series.rows),
        "alerts_emitted": len(alerts.rows),
        "effort_rows": len(effort.rows),
        "generated_at": generated_at,
    }


def _result_to_payload(result) -> dict:
    return {
        "title": result.title,
        "columns": result.columns,
        "rows": result.rows,
        "metadata": result.metadata,
    }


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, indent=2, default=_json_default),
        encoding="utf-8",
    )


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")


def _repo_filename(owner: str, name: str) -> str:
    safe = f"{owner}-{name}".replace("/", "-")
    return f"{safe}.html"


def _write_index(
    out_dir: Path,
    repo_pairs: list[tuple[str, str]],
    series,
    alerts,
    effort,
    *,
    since: str | None,
    baseline_periods: int,
    threshold_sigma: float,
    generated_at: str,
) -> None:
    repo_summaries = []
    series_rows = series.rows
    series_idx = {col: i for i, col in enumerate(series.columns)}
    alerts_idx = {col: i for i, col in enumerate(alerts.columns)}

    for owner, name in repo_pairs:
        label = f"{owner}/{name}"
        repo_series = [r for r in series_rows if r[series_idx["repo"]] == label]
        latest_period = max((r[series_idx["period"]] for r in repo_series), default="—")
        ttm = _latest_kpi(repo_series, series_idx, "median-time-to-merge", latest_period)
        frt = _latest_kpi(repo_series, series_idx, "median-first-response", latest_period)
        rr = _latest_kpi(repo_series, series_idx, "response-rate", latest_period)
        vol = _latest_kpi(repo_series, series_idx, "volume", latest_period)
        n_alerts = sum(
            1 for r in alerts.rows if r[alerts_idx["repo"]] == label
        )
        repo_summaries.append({
            "label": label,
            "filename": _repo_filename(owner, name),
            "latest_period": latest_period,
            "ttm": ttm,
            "frt": frt,
            "rr": rr,
            "vol": vol,
            "n_alerts": n_alerts,
        })

    rows_html = []
    for s in repo_summaries:
        pill = (
            f'<span class="pill alert">{s["n_alerts"]}</span>'
            if s["n_alerts"]
            else '<span class="pill ok">none</span>'
        )
        rows_html.append(
            "<tr>"
            f'<td><a href="repo/{html.escape(s["filename"])}">{html.escape(s["label"])}</a></td>'
            f'<td>{html.escape(s["latest_period"])}</td>'
            f'<td class="num">{_fmt(s["ttm"])}</td>'
            f'<td class="num">{_fmt(s["frt"])}</td>'
            f'<td class="num">{_fmt(s["rr"])}</td>'
            f'<td class="num">{_fmt(s["vol"])}</td>'
            f'<td>{pill}</td>'
            "</tr>"
        )

    alert_rows_html = []
    for r in alerts.rows[:20]:
        cls = "alert-up" if r[alerts_idx["direction"]] == "up" else "alert-down"
        alert_rows_html.append(
            f'<tr class="{cls}">'
            f"<td>{html.escape(str(r[alerts_idx['repo']]))}</td>"
            f"<td>{html.escape(str(r[alerts_idx['kpi']]))}</td>"
            f"<td>{html.escape(str(r[alerts_idx['period']]))}</td>"
            f'<td class="num">{_fmt(r[alerts_idx["current_value"]])}</td>'
            f'<td class="num">{_fmt(r[alerts_idx["baseline_mean"]])}</td>'
            f'<td class="num">{_fmt(r[alerts_idx["z_score"]])}</td>'
            f"<td>{r[alerts_idx['direction']]}</td>"
            "</tr>"
        )
    if not alert_rows_html:
        alert_rows_html.append('<tr><td colspan="7" class="muted">No alerts at the configured threshold.</td></tr>')

    body = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>gitsweeper dashboard</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<h1>gitsweeper portfolio dashboard</h1>
<p class="muted">
Generated {html.escape(generated_at)} ·
since {html.escape(since or 'start of cache')} ·
baseline {baseline_periods} periods ·
threshold {threshold_sigma}σ
</p>

<h2>Repositories</h2>
<table>
<thead>
<tr><th>Repo</th><th>Latest period</th><th>median TTM (d)</th><th>median FRT (d)</th><th>response rate</th><th>volume</th><th>alerts</th></tr>
</thead>
<tbody>
{''.join(rows_html)}
</tbody>
</table>

<h2>Recent alerts</h2>
<table>
<thead>
<tr><th>Repo</th><th>KPI</th><th>Period</th><th>Current</th><th>Baseline mean</th><th>z-score</th><th>Direction</th></tr>
</thead>
<tbody>
{''.join(alert_rows_html)}
</tbody>
</table>

<p class="muted">
Underlying data is also written to
<code>data/timeseries.json</code>, <code>data/alerts.json</code>,
<code>data/effort.json</code>, <code>data/classification.json</code>
in the same shape as the corresponding <code>--json</code>
commands produce.
</p>
</body>
</html>
""".strip()
    (out_dir / "index.html").write_text(body, encoding="utf-8")


def _write_repo_page(
    out_dir: Path,
    owner: str,
    name: str,
    series,
    alerts,
    effort,
    *,
    classification: dict | None,
    generated_at: str,
) -> None:
    label = f"{owner}/{name}"
    series_idx = {col: i for i, col in enumerate(series.columns)}
    alerts_idx = {col: i for i, col in enumerate(alerts.columns)}
    effort_idx = {col: i for i, col in enumerate(effort.columns)}

    repo_series = [r for r in series.rows if r[series_idx["repo"]] == label]
    repo_alerts = [r for r in alerts.rows if r[alerts_idx["repo"]] == label]
    repo_effort = [r for r in effort.rows if r[effort_idx["repo"]] == label]

    charts: list[str] = []
    for kpi in ("median-time-to-merge", "median-first-response", "response-rate", "volume"):
        rows_for_kpi = [
            {"period": r[series_idx["period"]], "value": r[series_idx["value"]], "kpi": kpi}
            for r in repo_series
            if r[series_idx["kpi"]] == kpi
        ]
        svg = render_line_svg(
            rows_for_kpi, x="period", y="value", title=f"{kpi} — {label}",
        )
        charts.append(f'<div class="chart"><h3>{html.escape(kpi)}</h3>{svg}</div>')

    alert_rows_html = []
    for r in repo_alerts:
        alert_rows_html.append(
            f"<tr><td>{html.escape(str(r[alerts_idx['kpi']]))}</td>"
            f"<td>{html.escape(str(r[alerts_idx['period']]))}</td>"
            f'<td class="num">{_fmt(r[alerts_idx["current_value"]])}</td>'
            f'<td class="num">{_fmt(r[alerts_idx["baseline_mean"]])}</td>'
            f'<td class="num">{_fmt(r[alerts_idx["z_score"]])}</td>'
            f"<td>{r[alerts_idx['direction']]}</td></tr>"
        )
    if not alert_rows_html:
        alert_rows_html.append('<tr><td colspan="6" class="muted">No alerts.</td></tr>')

    effort_rows_html = []
    for r in repo_effort:
        effort_rows_html.append(
            f"<tr><td>{html.escape(str(r[effort_idx['author']]))}</td>"
            f"<td class=\"num\">{r[effort_idx['submissions']]}</td>"
            f"<td class=\"num\">{r[effort_idx['merged']]}</td>"
            f'<td class="num">{_fmt(r[effort_idx["merged_rate"]])}</td>'
            f"<td class=\"num\">{r[effort_idx['self_pulled']]}</td>"
            f"<td class=\"num\">{r[effort_idx['closed_by_maintainer']]}</td>"
            f"<td class=\"num\">{r[effort_idx['still_open']]}</td></tr>"
        )

    classification_rows_html = []
    if classification:
        for r in classification["rows"]:
            classification_rows_html.append(
                f"<tr><td>{html.escape(str(r[0]))}</td>"
                f"<td class=\"num\">{r[1]}</td></tr>"
            )

    body = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(label)} — gitsweeper</title>
<link rel="stylesheet" href="../assets/style.css">
</head>
<body>
<nav><a href="../index.html">← portfolio</a></nav>
<h1>{html.escape(label)}</h1>
<p class="muted">Generated {html.escape(generated_at)}</p>

<h2>KPI time-series</h2>
{''.join(charts)}

<h2>Alerts</h2>
<table>
<thead>
<tr><th>KPI</th><th>Period</th><th>Current</th><th>Baseline mean</th><th>z-score</th><th>Direction</th></tr>
</thead>
<tbody>
{''.join(alert_rows_html)}
</tbody>
</table>

<h2>Effort allocation by author</h2>
<table>
<thead>
<tr><th>Author</th><th>Submissions</th><th>Merged</th><th>Merged rate</th><th>Self-pulled</th><th>Maint. closed</th><th>Open</th></tr>
</thead>
<tbody>
{''.join(effort_rows_html) or '<tr><td colspan="7" class="muted">No data.</td></tr>'}
</tbody>
</table>

<h2>Closed-without-merge classification</h2>
<table>
<thead><tr><th>Category</th><th>Count</th></tr></thead>
<tbody>
{''.join(classification_rows_html) or '<tr><td colspan="2" class="muted">No data.</td></tr>'}
</tbody>
</table>
</body>
</html>
""".strip()
    (out_dir / "repo" / _repo_filename(owner, name)).write_text(body, encoding="utf-8")


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _latest_kpi(rows, idx, kpi: str, period: str):
    for r in rows:
        if r[idx["period"]] == period and r[idx["kpi"]] == kpi:
            return r[idx["value"]]
    return None


__all__ = ["CacheEmpty", "publish"]
