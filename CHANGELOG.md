# Changelog

All notable changes to Gitsweeper are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning will follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once there is working code worth tagging.

## [Unreleased]

### **BREAKING** — Billbird tools moved to `billbird-client`

- `2026-05-22` — Decoupled Gitsweeper from Billbird's REST shape. The
  five Billbird-only MCP tools (`billbird_hours_summary`,
  `billbird_plan_vs_actual`, `billbird_cycle_time`,
  `billbird_recent_activity`, `team_status_report`) have moved to the
  separate [`billbird-client`](https://github.com/MWest2020/billbird-client)
  package, where they belong. `team_status_report` is retired entirely;
  the building blocks live in `billbird-mcp` for the Billbird half and
  in this server's individual analytics tools for the PR half.
- The in-tree `lib/billbird_client.py`, `manager_mcp/periods.py`, and
  the corresponding fake-Billbird test suite are deleted.
- The reconcile tool (`gitsweeper reconcile` and
  `gitsweeper_reconcile` MCP) now imports `BillbirdClient` from the
  external `billbird-client` package as an optional dependency. If
  the package is not installed, the tool returns a structured
  `billbird_client_unavailable` error rather than crashing.
- `pyproject.toml` gains `[project.optional-dependencies] billbird = ["billbird-client>=0.1.0"]`.
- MCP registry shrinks from 10 to 5 tools (PR throughput, first
  response, classify, reconcile, patterns). `tests/test_manager_mcp.py`
  and `scripts/mcp_smoke.py` updated accordingly. 151 tests pass.
- **Migration:** operators who used the Billbird tools through
  `gitsweeper mcp` should add `billbird-mcp` (from `billbird-client`)
  to their MCP-client configuration. The two servers compose; neither
  requires the other.



### Added

- `2026-05-21` — Reconcile capability (`gitsweeper reconcile <repo>`,
  MCP tool `gitsweeper_reconcile`). Pulls commit `Time:` footers from
  GitHub, pulls matching Billbird `/log` entries via the existing
  bearer-token client, aggregates per (repo, author, issue), computes
  drift and classifies it (`aligned` / `commits_only` / `logs_only` /
  `over_committed` / `over_logged`). New shared lib
  `lib/commit_time.py` (pure parser, 26 unit tests). New `list_commits`
  method on the GitHub client. New `docs/reconcile.md`. Brings the
  manager-MCP registry from 9 to 10 tools; `tests/test_manager_mcp.py`
  and `scripts/mcp_smoke.py` updated accordingly. 19 new end-to-end
  tests for the capability against pytest-httpx-mocked GitHub +
  Billbird.

- `2026-05-18` — Manager-MCP capability (`gitsweeper mcp`). Stdio MCP
  server exposing nine read-only tools that combine Gitsweeper's PR
  analyses (`pr_throughput`, `first_response`, `classify`, `patterns`)
  with Billbird's manager-view (`hours_summary`, `plan_vs_actual`,
  `recent_activity`, `cycle_time` stub) plus a composite
  `team_status_report` that returns both structured data and a
  markdown rendering. New shared library `lib/billbird_client.py`
  (mirrors `lib/github_client.py` shape) is the only path to
  Billbird's REST API; tokens come from `BILLBIRD_API_TOKEN`.
  Config is lazy: the server starts without Billbird env vars and
  the Gitsweeper-only tools stay usable. New dependency: official
  `mcp` Python SDK. New docs: `docs/mcp.md`. 30 new unit tests.
- `2026-05-20` — `scripts/mcp_smoke.py`: human-runnable smoke that
  spawns `gitsweeper mcp` as a child process, completes the MCP
  handshake, lists tools, and invokes `billbird_plan_vs_actual` and
  `billbird_hours_summary` against the Billbird pointed at by
  `BILLBIRD_API_URL` / `BILLBIRD_API_TOKEN`. Exits non-zero on any
  tool error so it doubles as a deploy-time canary. Verified live
  against a local Billbird instance on the same date — round-trip
  returns `{planned: 480, logged: 0, variance: -480, status: under}`
  for the seeded plan.
- `2026-05-19` — End-to-end MCP tests against a stdlib HTTP server
  that mimics Billbird (`tests/test_mcp_against_fake_billbird.py`).
  Eight new tests exercise the wire-level contract:
  hours-summary round trip, plan-vs-actual aggregation and
  status filter, recent activity combining logs and plans,
  composite report skipping PR sections when no repo is in scope,
  401 surfacing as `billbird_http_error/hint=auth`, and the
  invalid-period structured error. Brings the total to 131 tests.
- `2026-05-05` — OpenSpec baseline initialised. Project structure now
  includes `openspec/` (created via `openspec init --tools claude`) with
  the project description, the v1 stack and conventions, and the
  baseline architecture decisions captured in `openspec/project.md`.
- `2026-05-05` — Initial capability specs:
  - `pr-throughput-analysis` — fetch + persist GitHub pull requests,
    compute time-to-merge percentiles (median, p25, p75, p95, max)
    over merged PRs, support `--since` filtering, and provide an
    opt-in time-to-first-response analysis. Validated in strict mode.
  - `report-rendering` — pluggable renderer interface; CLI table
    (default) and JSON renderers shipped in v1; renderers contain no
    analysis logic. Validated in strict mode.
- `2026-05-05` — Claude Code integration via `.claude/skills/` and
  `.claude/commands/opsx/` (committed) so OpenSpec slash commands work
  in this project. `.claude/settings.local.json` is local-only and
  excluded via `.gitignore`.
- `2026-05-05` — `CHANGELOG.md` and `.gitignore` added.
- `2026-05-05` — `pyproject.toml` (uv-managed, Python 3.11+, EUPL-1.2),
  `src/gitsweeper/` package skeleton, locked dependencies committed.
- `2026-05-06` — v1 implementation landed:
  - `lib/storage.py` — SQLite via stdlib `sqlite3`, portable SQL, schema
    matches the project.md sketch (repositories / pull_requests /
    pr_first_responses) including the nullable `owner_namespace` seam.
  - `lib/github_client.py` — synchronous httpx REST client. Pagination
    via `Link rel=next`. `GITHUB_TOKEN` from env (warns once when
    absent). Primary rate-limit sleeps until `X-RateLimit-Reset`;
    secondary 429/Retry-After retried up to 5 times.
  - `lib/rendering.py` — `AnalysisResult` dataclass, `Renderer`
    Protocol, `CLITableRenderer` (default), `JSONRenderer` (`--json`).
    Renderers contain no analysis logic.
  - `capabilities/pr_throughput.py` — fetch + persist orchestration,
    time-to-merge percentiles (median / p25 / p75 / p95 / max in days)
    over merged PRs only, `--since YYYY-MM-DD` validation,
    `compute_first_response` (opt-in, caches per-PR comment lookups).
  - `cli.py` — typer app with three commands: `fetch`, `throughput`,
    `first-response`. Default cache at
    `$XDG_STATE_HOME/gitsweeper/gitsweeper.sqlite`.
  - `tests/` — 34 unit tests (storage, github_client with httpx mock
    transport, rendering, pr_throughput math, CLI). `ruff` clean.
- `2026-05-06` — Smoke run against `nextcloud/app-certificate-requests`
  (unauthenticated, 1000 PRs cached). Time-to-merge over full history:
  median 1.65 days, p95 16.80 days, max 111.93 days (count = 780
  merged). With `--since 2025-01-01`: median 2.08 days, p95 17.11 days
  (count = 184). The right-skewed tail confirms the design choice for
  percentiles over the mean.
- `2026-05-06` — Authenticated rerun (via `gh auth token`) added the
  `first-response` analysis: repo-wide median 1.08 days, p95 14.52
  days, max 273.90 days; 787 / 1000 got a non-author comment.
- `2026-05-06` — Conduction-specific report written to
  `docs/examples/nextcloud-csr-report-2026-05-06.md`. Used the cache
  plus a one-off enrichment (close-actor via the issue-events API) to
  separate self-pulled PRs from maintainer-closed ones. Result:
  Conduction's 80% effective response rate matches the repo norm of
  87% (within noise on N=15); the real gap is first-response latency
  (3.59 days median for Conduction vs 1.08 repo-wide), consistent with
  a batched-pickup pattern.
- `2026-05-06` — Dutch translation of the same report at
  `docs/examples/nextcloud-csr-rapport-2026-05-06.md`. Added a one-line
  TL;DR phrasing of the conclusion: voor Conduction's slice geldt dat
  er niet vaak genoeg gekeken wordt, maar zodra er gekeken wordt gaat
  het vrijwel direct goed en wordt het snel opgepikt. Repo-breed is de
  pickup juist snel (~1d); de "niet vaak genoeg gekeken"-uitspraak
  slaat alleen op onze slice, niet op het proces als geheel.
- `2026-05-06` — Day-of-week / hour-of-day appendix added to both
  reports. Repo-wide pattern: Friday submissions wait 4× longer than
  Mon–Thu (median 2.95d vs 0.71d) — the weekend-trap; activity is
  concentrated 08:00–16:00 UTC (EU work hours). Conduction-side: 41%
  of submissions are Fri/Sat, 32% are 19–20 UTC. Decomposed the 3.3×
  first-response gap: weekend-trap ~0.9d, off-hours ~0.3d, residual
  ~1.5d (batch-pickup effect). The residual is what a `@mention`
  pickup signal would close.
- `2026-05-06` — Output reports moved out of version control:
  `docs/examples/` is now in `.gitignore`. The reports remain on
  disk locally; their session-time content lives in commits 0d06c18,
  66de3d2, and df541f0 for audit.
- `2026-05-07` — OpenSpec change `static-site-publish` proposed,
  implemented, and archived. Closes the D-side of DAR. New
  `gitsweeper publish [--out] [--repos] [--since] [--baseline]
  [--threshold]` command writes a self-contained HTML+SVG bundle
  (index page, per-repo drill-downs with KPI line-charts, alerts,
  effort-allocation, classification) plus the underlying JSON
  data files that backed each rendered view. No JavaScript, no
  remote references — auditable offline. New dependency:
  `matplotlib` for SVG chart rendering. Smoke output for
  `cache/conductionnl-openregister.sqlite` with `--since
  2026-01-01 --baseline 6` is 61 series rows / 0 alerts /
  ~180K HTML; written to `docs/examples/dashboard/` (gitignored
  by convention). 7 new tests; 93 total.
- `2026-05-07` — OpenSpec change `effort-allocation` proposed,
  implemented, and archived. Per-author × per-repo (optionally
  per-period) submission/outcome pivot. Three closure buckets
  (`self_pulled`, `closed_by_maintainer`, `closed_unenriched`) so
  the data is honest about classification gaps. `merged_rate` is
  `merged / (merged + closed_by_maintainer)` so self-pulled
  duplicates do not deflate the rate. New CLI: `gitsweeper effort
  [--since] [--repos] [--by-period] [--json]`. Smoke against the
  openregister cache for `--since 2026-01-01` shows 8 active
  authors, top contributor at 101 submissions / 72 merged
  (0.96 merged_rate); self-pull rate roughly 12–15% across active
  authors. 9 new tests; 86 total.
- `2026-05-07` — OpenSpec change `regression-monitoring` proposed,
  implemented, and archived. First A-side capability on top of the
  KPI series. `compute_regression_alerts` groups the time-series
  per `(repo, [author], kpi)`, takes the latest period as the
  current value, computes a trailing-baseline mean + stdev over
  the previous N periods (default 12), and emits one alert row
  per series whose z-score exceeds `threshold_sigma` (default 2.0).
  Stable series, insufficient baselines, and flat baselines are
  silently skipped and counted in metadata. New CLI:
  `gitsweeper regressions [--baseline] [--threshold] [--kpis]
  [--by-author] [--repos] [--json]`. Smoke run against the
  openregister cache: 3 series inspected with `--baseline 6`, 0
  alerts (the recent weeks sit within ±2σ of their trailing 6-week
  baseline). 6 new tests; 77 total.
- `2026-05-07` — OpenSpec change `portfolio-timeseries-foundation`
  proposed, implemented, and archived. Foundation for the A/D-side
  of DAR (analysis and dashboard, beyond the existing reporting
  layer):
  - `pr-throughput-analysis` (modified): `fetch` now accepts
    multiple `owner/repo` arguments and an `--org <name>` flag that
    enumerates a GitHub organisation's repositories. Per-repo errors
    are reported but do not abort the batch; the command exits
    non-zero on partial failure.
  - New capability `kpi-timeseries`: long-format
    `(period, repo, author, kpi, value, sample_size)` series across
    one or more cached repositories. Closed KPI registry covers
    `median-time-to-merge`, `median-first-response`,
    `response-rate`, `volume`. ISO week as the default period; the
    `period` parameter is the seam for later calendar-month /
    quarter additions. Empty buckets omitted (no `NaN`/`0`
    sentinels). New CLI: `gitsweeper timeseries`.
  - Tests grow from 62 to 71. Smoke run against the
    `ConductionNL/openregister` cache shows the expected weekly
    pattern: weeks vary from 1 PR to 54 PRs with response-rate
    swinging 0.00–0.93 — exactly the kind of variability that future
    regression-monitoring will quantify against a trailing baseline.
- `2026-05-06` — Output convention finalised: caches under `cache/`
  (matches `*.sqlite`), reports under `docs/examples/`. Both
  gitignored. Smoke runs no longer dump into `/tmp`. README and
  `.gitignore` updated to make this the documented convention.
- `2026-05-06` — OpenSpec change `reusable-process-report` proposed,
  implemented, and archived. The session's ad-hoc analysis pipeline
  is now first-class:
  - `--author <login>` flag added to `throughput` and
    `first-response` (case-insensitive match).
  - New CLI `gitsweeper patterns` for day-of-week / hour-of-day
    distributions; replaces the inline Python from the report
    appendices.
  - New capability `pr-classification`: enriches closed-without-merge
    PRs with the close-event actor (via the issue-events endpoint,
    which actually populates the data the `pulls` endpoint omits) and
    classifies each as self-pulled, maintainer-closed, or unknown.
    Persisted in the new `pr_close_actors` table; runs cached on
    re-invocation. New CLI `gitsweeper classify`.
  - New renderer `markdown` registered in `report-rendering`.
  - New capability `pr-process-report`: composes volume, throughput,
    first-response, classification, and temporal patterns into a
    single markdown document. New CLI `gitsweeper report
    <repo> [--author] [--since] [--refresh] [--out PATH]`. Refuses
    on empty cache unless `--refresh`.
  - Tests: 60 total (was 34), all green; ruff clean.
  - Archive merged the deltas into baseline specs; four capabilities
    now live under `openspec/specs/`.
