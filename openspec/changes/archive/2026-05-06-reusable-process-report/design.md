## Context

The first real run of gitsweeper produced a process report on
`nextcloud/app-certificate-requests` using the v1 baseline plus a
handful of one-off Python scripts in chat. The CLI covers fetch,
throughput, and first-response. Everything else — by-author slicing,
self-pulled vs maintainer-closed classification, temporal patterns,
markdown report assembly — was handcrafted and is not reproducible
without rebuilding the scripts. This change makes the same workflow
runnable as one command.

The architecture in `openspec/project.md` says capabilities own
user-visible analyses and shared infrastructure stays in `lib/`. We
extend three existing pieces (`pr-throughput-analysis`,
`report-rendering`, `lib/storage`, `lib/github_client`) and add two
capabilities (`pr-classification`, `pr-process-report`).

## Goals / Non-Goals

**Goals:**

- Run the full report we wrote by hand as a single command, given a
  populated cache.
- Make per-author slicing first-class (it is the most common cut
  besides the repo-wide one).
- Make the self-pulled / maintainer-closed distinction first-class —
  without it, response-rate numbers are systematically misleading.
- Keep the existing `throughput` and `first-response` commands
  source-compatible.
- Stay inside the renderer contract: the markdown report is composed
  by passing structured `AnalysisResult` objects through a markdown
  renderer registered in `report-rendering`, not by string-templating
  inside the capability.

**Non-Goals:**

- Multi-repo aggregation in a single report.
- PDF / dashboard / web renderers (markdown is the new format; PDF
  comes later).
- Per-PR drill-down (the report stays at the aggregate-stats level;
  individual PR tables live in the cache for ad-hoc queries).
- Author detection for non-author commenters beyond the GitHub login
  (`bot[user]` accounts are not specially handled).
- Modelling formal PR reviews. We continue to use issue-comments as
  the first-response signal; the methodology caveat from the v1
  reports stays in the report template.

## Decisions

### Why ADDED, not MODIFIED, on `pr-throughput-analysis`

The `--author` filter and the temporal-patterns analysis are purely
additive. Existing scenarios for "Filter analysis by merge date"
and "Compute time-to-merge percentiles" do not need their behaviour
restated — they continue to work exactly as before when no author
is supplied. Using ADDED keeps the delta narrow and avoids the
common pitfall of MODIFIED accidentally narrowing existing
behaviour at archive time.

### Close-actor enrichment via the issue-events endpoint, not /pulls/{n}

The pulls endpoint omits `closed_by` for many pull requests in
`nextcloud/app-certificate-requests` (we verified this in the
session — every request returned `closed_by: null`). The
issue-events endpoint records every state-change with its actor
reliably. We pay the same one-call-per-PR cost either way, so we
use the endpoint that actually answers the question.

### A new SQLite table, not a column on `pull_requests`

`pr_close_actors` is sparse (only meaningful for closed-without-
merge PRs) and may be NULL even when populated (the rare "no
close event" case). A new table keeps `pull_requests` lean and
makes "have we tried to enrich this yet?" a simple
`LEFT JOIN ... IS NULL` check. The same pattern as
`pr_first_responses`.

### Report capability composes through the renderer, not by hand

It is tempting to build the report's markdown string directly inside
the report capability — it would be a few f-strings. But that
duplicates formatting logic and makes adding a future renderer (PDF,
dashboard JSON) require touching report code. By passing each
section's `AnalysisResult` through `report-rendering.markdown` we
honour the v1 architectural decision in `project.md` (renderers are
pure presentation; capabilities never decide format) and keep the
seam open for future formats.

### `report` does not auto-fetch

The data freshness question is separate from the rendering
question, and a user who runs `report` may legitimately want the
last snapshot rather than a re-fetch. We make that explicit with
`--refresh` rather than guessing. A repository with no cache yet is
an error with a clear message, not a silent multi-call API hit.

### Case-insensitive author matching

GitHub treats logins as case-insensitive when matching but stores
them with a canonical case. Users will type `mwest2020` and expect
`MWest2020`'s PRs. We normalise via `LOWER()` in SQL — portable
across SQLite and Postgres — rather than depending on a specific
collation.

## Risks / Trade-offs

- **API budget for `--refresh`**: classify adds one call per
  closed-without-merge PR. For
  `nextcloud/app-certificate-requests` that is 193 calls. Trivial
  with a PAT but blows the unauthenticated 60/h budget. The
  unauth-warning we already have in `github_client` covers the
  user-facing message; we accept that the unauth experience is
  degraded.
- **Markdown renderer fidelity**: a pure-presentation renderer can
  only show what is in the `AnalysisResult`. Any layout decisions
  that look "report-shaped" (footnotes, narrative text between
  sections) need to live as data on the result, not as ad-hoc
  template logic. The first iteration will probably feel sparser
  than the handwritten reports because we deliberately keep
  narrative out. That is the right trade for v1; richer report
  templates can come as a separate change.
- **Issue-events pagination**: a PR with hundreds of events
  (rare) needs paginated fetching. We accept the simple
  implementation — fetch first 100 events; warn if `Link` header
  shows more — rather than building full pagination here. We can
  revisit if a real repo trips it.
- **Author-filter at SQL level**: filtering authors in SQL keeps the
  data small and makes `--author` cheap regardless of repo size.
  The trade is one more `LOWER()` in queries, accepted.
