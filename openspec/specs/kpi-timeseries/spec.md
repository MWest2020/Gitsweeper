# kpi-timeseries Specification

## Purpose
TBD - created by archiving change portfolio-timeseries-foundation. Update Purpose after archive.
## Requirements
### Requirement: Compute time-bucketed KPI series across one or more repositories

The system SHALL produce a long-format `AnalysisResult` containing
one row per (period, scope, kpi) triple, where `period` is a
calendar bucket (ISO week by default), `scope` is one or more of
`repo`, `author`, or both combined, and `kpi` is one of the
recognised KPI names defined below.

#### Scenario: One row per period × scope × KPI

- **GIVEN** the cache contains pull requests across two ISO weeks
  for two repositories
- **WHEN** the user requests the KPI series with
  `--by repo --period iso-week --kpis median-time-to-merge,volume`
- **THEN** the result has rows for every combination of (week, repo,
  kpi) for which there is at least one pull request in scope
- **AND** the columns include `period`, `repo`, `kpi`, `value`, and
  `sample_size`, in that order

#### Scenario: Default period is ISO week

- **GIVEN** the user does not supply `--period`
- **WHEN** the KPI series is computed
- **THEN** ISO week (Monday-to-Sunday in UTC, formatted as
  `YYYY-Www`, e.g. `2026-W18`) is used to bucket pull requests

#### Scenario: KPI registry is closed and explicit

- **WHEN** the user supplies `--kpis` listing names that include any
  value not in `{median-time-to-merge, median-first-response,
  response-rate, volume}`
- **THEN** the command exits with a non-zero status and a clear
  error naming the unknown KPI(s) and listing the recognised set
- **AND** does not run the analysis

### Requirement: Honour the existing scope filters --since, --author, and per-repo selection

The KPI series SHALL respect the same scope filters as the existing
single-repo analyses: `--since YYYY-MM-DD` for a lower bound on
period start, `--author` for a case-insensitive author match, and
an explicit list of `owner/repo` values to restrict the population.

#### Scenario: --since drops periods that fall fully before the bound

- **GIVEN** the user supplies `--since 2026-01-01`
- **WHEN** the KPI series is computed
- **THEN** only pull requests with `created_at >= 2026-01-01T00:00:00Z`
  contribute to any period bucket
- **AND** periods that contain no qualifying pull requests are not
  emitted (rather than being emitted with sample size 0, since the
  long format already self-describes its sparsity)

#### Scenario: --author scopes the entire series

- **GIVEN** the user supplies `--author MWest2020`
- **WHEN** the KPI series is computed
- **THEN** every emitted row reflects only pull requests authored
  by that login, case-insensitively

#### Scenario: --repos restricts the portfolio scope

- **GIVEN** the cache contains five repositories but the user passes
  `--repos ConductionNL/openregister ConductionNL/opencatalogi`
- **WHEN** the KPI series is computed
- **THEN** only those two repositories' pull requests contribute
- **AND** the metadata records the selected scope so the result is
  interpretable in isolation

### Requirement: Empty buckets do not produce noisy NaN values

The KPI series SHALL only emit rows for buckets that contain at
least one qualifying pull request; KPIs that are mathematically
undefined on an empty bucket (medians, response-rate) are never
emitted as `NaN` or `0`.

#### Scenario: Median over an empty bucket is omitted, not NaN

- **GIVEN** in some week there are zero merged pull requests for a
  repository in scope
- **WHEN** the KPI series is computed for that repository
- **THEN** there is no row for that (week, repo, median-time-to-merge)
  combination
- **AND** the absence is interpretable from the long-format result
  itself (no row = no data) rather than masked by a sentinel value

#### Scenario: Volume is reported even when other KPIs are not

- **GIVEN** in some week the repository has open pull requests but
  no merged ones
- **WHEN** the KPI series includes both `volume` and
  `median-time-to-merge`
- **THEN** a `volume` row is emitted with the count
- **AND** the `median-time-to-merge` row is omitted (no merged
  population)

### Requirement: Render through the existing renderer interface

The KPI series SHALL be emitted as a structured `AnalysisResult`
suitable for the table, JSON, and markdown renderers from
`report-rendering`, never by formatting output inside the analysis
capability.

#### Scenario: --json produces a machine-readable series

- **GIVEN** the user runs `gitsweeper timeseries --json`
- **WHEN** the analysis completes
- **THEN** the output on standard output is valid JSON containing
  the same `(period, scope, kpi, value, sample_size)` long-format
  rows present in the underlying `AnalysisResult`
- **AND** it is suitable to pipe into a downstream regression or
  dashboard process without further parsing

