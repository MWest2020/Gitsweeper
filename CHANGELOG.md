# Changelog

All notable changes to Gitsweeper are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning will follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once there is working code worth tagging.

## [Unreleased]

### Added

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
