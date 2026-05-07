## Context

`pr-throughput-analysis` already owns single-repo fetch + analysis;
`pr-classification` adds close-actor enrichment; `pr-process-report`
composes a markdown snapshot. All current outputs are point-in-time
descriptive (Reporting in DAR terms). Steering — regression watch,
effort allocation, strategic comparisons — needs a different shape:
**time-bucketed KPIs across a portfolio**.

The cache schema already supports multi-repo (one row per
`(owner, name, owner_namespace)` in `repositories`, FK from every
other table). Extending the fetch path to enumerate an org and to
accept multiple positional arguments is plumbing. The new piece is
the time-series computation itself.

## Goals / Non-Goals

**Goals:**

- One ingest invocation that fills the cache for an entire
  GitHub organisation or any explicit list of repos.
- A long-format KPI series suitable for both quick CLI inspection
  and downstream consumption (regression alerts, effort pivots,
  dashboards).
- ISO week as the default period; the function-level seam exists so
  later changes can plug in calendar-month or quarter without
  re-architecting.

**Non-Goals:**

- Regression alerts or significance testing in this change. The
  output of the KPI series is what the future regression command
  consumes; emitting it raw is enough scope.
- Effort-allocation pivots. They will compose on top of the same
  series with a different KPI set (volume by author by repo by
  week).
- Static-site dashboards. They consume the JSON output; building
  the visualisation layer is its own change.
- Per-PR drill-down. The series is at aggregate granularity.
- Re-fetching when a repo is renamed or transferred. The user is
  expected to update their fetch list.
- Storing KPI series in the cache. Series are recomputed on demand
  from the underlying PR rows, which are already cached. The
  series is cheap to recompute and would otherwise need careful
  invalidation when underlying data changes.

## Decisions

### `--org` enumerates via `/orgs/{org}/repos`, not search

The org-repos endpoint is straightforward: paginated, predictable,
includes archived/forked information for filtering. Using GitHub
search would mean ranking concerns and a separate rate-limit pool.
We pay one repo-list call per page (1 per 100 repos) and then the
existing per-repo cost.

### Multi-repo fetch keeps each repo's fetch logic untouched

The orchestrator that handles `fetch repo1 repo2 ...` calls
`fetch_and_persist` once per repo. No batching at the API level
(GitHub does not support multi-repo PR list in REST), no
parallelisation (the rate-limit machinery is shared state and
async would complicate it for marginal gain on the v1 scale).
Sequential and boring.

### Long-format result, not pivoted

A long format is `(period, repo, author, kpi, value, sample_size)`.
A wide format would be one row per period with one column per
(repo, kpi). Long is the right default because:

- The number of (repo, kpi) combinations is variable (org-wide
  fetch could be 50+ repos × 4 KPIs = 200 columns) and would blow
  up the wide table.
- Downstream consumers (regression detection, dashboards) want to
  iterate over series; long is the natural shape for groupby.
- The renderer layer prints one row per record uniformly; wide
  formats would need bespoke renderer logic.

A pivot helper can be added later as a presentation choice
without changing the underlying capability.

### ISO week is the default period

ISO 8601 week (Monday start, year-week label like `2026-W18`) is
the only widely understood week definition and it survives
year-boundary correctly (week 1 of `2026-W01` may start in
December 2025, but the label is unambiguous). Calendar-month and
quarter are useful for billing or board-level reporting; the
function accepts a `period` parameter so they slot in later.

### Empty buckets are omitted, not zero-padded

Long format makes "no data" the absence of a row, not a sentinel.
Zero-padding would create rows where median-time-to-merge is `NaN`
or `0`, which is exactly the kind of misleading value the v1
percentile decision was meant to avoid. A consumer that wants
zero-padding can join the long result against a generated period
spine; the capability does not enforce that on every consumer.

### KPI registry is closed and explicit

`--kpis median-time-to-merge,response-rate,volume` is validated
against a fixed set. Unknown names error out with a clear list,
matching how `--since` rejects malformed dates. Adding a new KPI
is a code change, not a free-form parameter — the trade is that
typos are caught immediately and consumers can rely on a known
universe.

### Bucketing in polars, on UTC dates

Polars handles the date arithmetic and groupby far more cleanly
than a hand-rolled Python loop, and we already depend on it. UTC
because every `created_at` and `merged_at` value in the cache is
already an ISO 8601 UTC string. Mixing in local time would produce
buckets that flip pull requests across a week boundary depending on
the viewer's locale; UTC is the only honest choice.

### Result rendering goes through `report-rendering`

The series is just another `AnalysisResult` — table, JSON, and
markdown renderers all work without modification. JSON is the form
that downstream regression and dashboard work will consume; humans
will mostly read the table or markdown form. No new renderer
needed for this change.

## Risks / Trade-offs

- **Long format is verbose.** A 12-week, 5-repo, 4-KPI run is up
  to 240 rows. Acceptable for human reading via the table renderer
  (it's still scannable) and natural for JSON / markdown
  consumers. If portfolios grow much larger, we will likely add a
  pivot or aggregate-only flag.
- **Org-wide fetch can be expensive.** A ConductionNL-scale org
  with ~50 repos × ~1000 PRs each is 50,000 API calls. That fits
  inside the 5000/h authenticated budget over ~10 hours of
  elapsed time; it is *not* an interactive command. Document the
  cost, warn loudly the first time, and consider a follow-up
  change for resumable fetches if this becomes a real pain point.
- **The capability does not store the series.** Recomputing on
  every call is fast (cache rows + polars groupby), but if a
  consumer wants to detect changes between two specific snapshots
  they must persist the JSON output themselves. Storing the
  series would create cache-coherence problems we do not yet need
  to solve.
- **Bucketing assumes `created_at` represents intent at submission
  time.** PRs that are reopened or migrated may have a
  `created_at` that no longer matches their effective start. We
  accept this approximation; it matches how the existing TTM and
  FRT analyses behave.
