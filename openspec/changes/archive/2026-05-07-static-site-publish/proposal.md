## Why

Reports are markdown documents — fine for sharing in chat, but
unergonomic for *steering*. The user's three driving needs all
benefit from a glanceable surface: regression alerts at the top,
KPI charts in the middle, effort-allocation per author at the
bottom, and per-repo drill-down behind links. That is a static
HTML site, not a single document.

The data is already there: `kpi-timeseries`, `regression-monitoring`,
`effort-allocation`, and `pr-classification` all emit structured
results. This change is the rendering layer: a `publish` capability
that walks the cache, runs each analysis, and writes a small static
bundle (HTML + SVG charts + JSON data files) into a directory.

## What Changes

- **New**: `static-site-publish` capability. Given a populated cache
  and an output directory, write:
  - `index.html` — portfolio overview (one row per repo with
    headline KPIs, regression alerts called out, effort-allocation
    summary).
  - `repo/<owner>-<repo>.html` — per-repo drill-down with KPI
    time-series SVG charts and an alerts section.
  - `data/<scope>.json` — the underlying long-format series and
    the alert list, so a downstream consumer (or a future
    interactive overlay) can ingest the same bytes the page
    rendered from.
  - `assets/style.css` — minimal, embedded style for offline use.
- **Modified**: `report-rendering` adds a small SVG-chart helper
  for line plots from a long-format series. (The renderer
  registry stays unchanged — chart rendering is plumbing that the
  publish capability uses, not a renderer the user selects via
  `--json`.)
- **Dependency**: `matplotlib` (added to `[project] dependencies`).
  Boring choice; produces SVG with no JS.

No breaking changes; the existing CLI surface keeps working.

## Capabilities

### New Capabilities

- `static-site-publish`: produces a deployable HTML+SVG bundle
  from the local cache, suitable for `python -m http.server` or
  GitHub Pages.

### Modified Capabilities

- `report-rendering`: gains an SVG-chart helper used by the
  publish capability to render KPI series as line plots. The
  Renderer protocol and registry are untouched.

## Impact

- **Code**: new `capabilities/dashboard.py` (the publish
  orchestrator) and an SVG-chart helper in `lib/rendering.py`.
- **Dependency**: `matplotlib` added (and locked).
- **CLI**: new `gitsweeper publish [--out PATH] [--repos ...]
  [--since] [--baseline] [--threshold]` command.
- **Out of scope**: interactive charts, JS, real-time refresh,
  authentication. The bundle is static and intended to be
  inspected via a local web server or hosted on GitHub Pages.
