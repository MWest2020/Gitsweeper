## Why

The current toolset answers descriptive questions about a single
repository at a single point in time (Reporting). It does not answer
the questions that drive steering:

- **Regression watch**: is this week's median first-response moving
  away from the trailing baseline?
- **Effort allocation**: is the team spread across the repos that
  should get attention, or is the activity concentrated somewhere
  unintended?
- **Strategic conversations**: how does this quarter compare to
  last? where are the trends?

All three need data shaped as **time-bucketed KPIs across a portfolio
of repos**, not a single-repo snapshot. The cache already supports
multiple repositories — `repositories` carries one row per
`(owner, name, owner_namespace)` — but the fetch command and the
analysis layer are still single-repo. This change closes that gap.

## What Changes

- **Modified**: `pr-throughput-analysis` — `fetch` accepts multiple
  `owner/repo` arguments in one invocation, and accepts `--org <name>`
  to ingest every repository in a GitHub organisation. No new
  fetch logic per repo; the existing pagination, rate-limit, and
  persistence behaviour stays. Only the orchestration around it is
  new.
- **New**: `kpi-timeseries` — produces a long-format time-series of
  selected KPIs (median time-to-merge, median first-response,
  response-rate, PR volume) bucketed by ISO week (default), scoped by
  repo and/or author, optionally filtered by `--since`. The result is
  rendered through the existing renderer interface (table / JSON /
  markdown) so downstream regression and effort-allocation work can
  consume the same structured output.

No breaking changes; existing single-repo flows are unaffected.

## Capabilities

### New Capabilities

- `kpi-timeseries`: time-bucketed KPI series across one or more
  repositories. The single foundation that future regression
  monitoring, effort allocation, and dashboards consume.

### Modified Capabilities

- `pr-throughput-analysis`: extends fetch to accept a list of
  `owner/repo` arguments and an `--org` flag, so the cache can hold a
  portfolio of repos in one invocation.

## Impact

- **Code**: extension to `lib/github_client.py` (`list_org_repos`),
  to `cli.py` (variadic `fetch` argument plus `--org`), and to
  `capabilities/pr_throughput.py` (the orchestrator function for
  multi-repo fetch). New `capabilities/kpi_timeseries.py`.
- **Schema**: no changes — `repositories`, `pull_requests`,
  `pr_first_responses`, `pr_close_actors` already cover the data the
  time-series needs.
- **CLI**: `fetch` now also accepts multiple repos and `--org`. New
  `timeseries` command.
- **API budget**: `--org` adds one repo-list call per page (1 call per
  100 repos) plus the per-repo fetch cost we already pay.
- **Out of scope for this change**: regression alerts, effort pivots,
  static-site dashboard. They land in follow-up changes once the
  time-series spine is in.
