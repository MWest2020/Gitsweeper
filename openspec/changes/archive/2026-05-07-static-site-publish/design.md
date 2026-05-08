## Context

`kpi-timeseries`, `regression-monitoring`, `effort-allocation`,
`pr-classification`, and `pr-process-report` already produce
structured data and markdown. None of them produce a glanceable
visual surface — which is what *steering* asks for. This change
adds the publishing layer on top of them.

The audience is small and known: the user, the Conduction team,
and external stakeholders such as Fabrice in the Nextcloud
conversation. A static HTML bundle hits the spot — sharable,
auditable, offline-viewable, and trivially hostable on
`python -m http.server` or GitHub Pages.

## Goals / Non-Goals

**Goals:**

- One command (`gitsweeper publish`) produces a deployable bundle
  from the cache.
- Pre-rendered SVG charts; no JS, no remote dependencies.
- The same JSON the page rendered from is also written to disk,
  so downstream consumers (a future bot, an analytics pipeline,
  a curious operator with `jq`) ingest the same bytes.
- Reproducible from cache alone; the publish command never makes
  GitHub API calls.

**Non-Goals:**

- Interactivity. No filters, no zoom, no live refresh. If the
  operator wants different scope they re-run the command.
- Authentication / hosting. The bundle is files in a directory;
  hosting is out of scope.
- A theming system. One CSS file, embedded styling decisions.
- Per-PR drill-down. Aggregate granularity, like the rest of the
  toolchain.
- Daemon mode. v1 is a one-shot publish; cron-driven re-publish
  is the operator's call.

## Decisions

### Matplotlib for SVG, not Plotly / Vega / Chart.js

Matplotlib is the boring choice: ubiquitous, stable, ships SVG
output natively, and runs entirely server-side with no JS bundle
to wrangle. The trade-off is that the resulting charts are static
PNG-style — fine for our purpose. Plotly / Vega-Lite would mean
shipping JS bundles or relying on CDNs, both of which violate the
"no remote references" goal.

### Long-format JSON file alongside the page

Every page that shows a chart also has a JSON data file behind
it. Two reasons:

1. The same bytes that drove the chart are auditable: a
   stakeholder can `cat data/timeseries.json | jq` and reproduce
   any number on the page.
2. A future interactive overlay (an `htmx` snippet, a small JS
   chart on an internal page, a downstream CI check) can consume
   the JSON without re-running the analysis.

The JSON is the same shape `gitsweeper timeseries --json` and
`gitsweeper regressions --json` already produce. No new schema.

### Bundle layout

```
docs/examples/dashboard/
├── index.html
├── repo/
│   └── ConductionNL-openregister.html
├── data/
│   ├── timeseries.json
│   ├── alerts.json
│   ├── effort.json
│   └── classification.json
└── assets/
    └── style.css
```

Repo file names use `<owner>-<repo>` rather than `<owner>/<repo>`
to avoid shipping nested directories that need separate index
handling on GitHub Pages.

### One CSS file; minimal, no framework

A handful of selectors covers what we need: tables, alert pills
(red/orange/green), section headings, monospace for codes. No
Tailwind, no Bootstrap, no design system. The file lives in
`assets/style.css` so a future tweak does not require touching
HTML templates.

### Empty-cache error, not auto-publish-empty

`publish` against an empty cache exits non-zero with a clear
message ("run `fetch` first"). The same convention as
`pr-process-report` so the surprise surface is consistent.

### Reproducibility caveat

The page header includes a `Generated <UTC>` timestamp. That is
the only field that drifts between runs of the same cache. We
deliberately do not strip the timestamp because audit trails
benefit from knowing when a bundle was produced.

## Risks / Trade-offs

- **Matplotlib is a heavy dep.** Adds ~50MB to the venv. Trade
  is acceptable — the user ships in their own venv, not as a
  binary, and we already have polars (~50MB) and httpx as core
  deps. If we ever ship a slim variant, the publish capability
  is the cleanest place to gate behind an extra (`pip install
  gitsweeper[publish]`).
- **SVG can grow large with many points.** A 12-week chart at one
  point per week is tiny; a 1000-week chart could be a few hundred
  KB of SVG. Acceptable for our scale; a future change could
  rasterise to PNG above a threshold.
- **The bundle is regenerated wholesale on each run.** Incremental
  updates would require change detection that is not worth the
  complexity at this scale. We accept that publish is O(scope) on
  every run.
- **Charts do not cover every KPI in v1.** We render the four
  KPIs we already support (median-time-to-merge,
  median-first-response, response-rate, volume). Any future KPI
  is a one-line addition to the chart-orchestrator.
