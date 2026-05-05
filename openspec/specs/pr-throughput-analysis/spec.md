# pr-throughput-analysis

## Purpose

Provide quantitative answers about how a GitHub repository handles
pull requests: how long they take to merge, how that latency is
distributed, and how quickly maintainers first engage. The capability
covers data acquisition from the GitHub REST API, local persistence
so re-analysis is free, and the analyses themselves. Output is
delegated to the `report-rendering` capability.

## Requirements

### Requirement: Fetch all pull requests for a repository

The system SHALL fetch every pull request belonging to a specified
GitHub `owner/repo` via the GitHub REST API, following pagination
until all pages have been retrieved.

#### Scenario: Pagination via Link header

- **GIVEN** the repository has more pull requests than fit on a
  single REST page
- **WHEN** the user requests a fetch
- **THEN** the system follows the `rel="next"` URL from each
  response's `Link` header until no `next` link remains
- **AND** every pull request from every page is captured

#### Scenario: Primary rate limit reached

- **GIVEN** the GitHub primary rate limit (`X-RateLimit-Remaining: 0`)
  has been hit during a fetch
- **WHEN** the next request would otherwise be sent
- **THEN** the system waits until the timestamp in
  `X-RateLimit-Reset` before continuing
- **AND** the wait is reported to the user so a long pause is not
  mistaken for a hang

#### Scenario: Secondary rate limit (abuse detection) hit

- **GIVEN** GitHub returns a `403` or `429` with a `Retry-After`
  header indicating a secondary rate limit
- **WHEN** the system observes that response
- **THEN** the system sleeps for the duration in `Retry-After`
  before retrying the same request
- **AND** the retry uses the same idempotent request, not a new one

#### Scenario: Authenticated fetch via GITHUB_TOKEN

- **GIVEN** the environment variable `GITHUB_TOKEN` is set to a
  Personal Access Token
- **WHEN** the system issues requests to the GitHub API
- **THEN** every request carries the token in an `Authorization`
  header
- **AND** the higher authenticated rate-limit budget applies

#### Scenario: Unauthenticated degraded mode

- **GIVEN** `GITHUB_TOKEN` is not set
- **WHEN** the user requests a fetch
- **THEN** the system proceeds without an `Authorization` header
- **AND** warns the user once that the unauthenticated rate-limit
  budget is small and the fetch may be slow or incomplete for large
  repositories

### Requirement: Persist fetched pull requests so re-analysis is free

The system SHALL store every fetched pull request in the local
storage layer such that subsequent analyses run from cache without
issuing GitHub API calls.

#### Scenario: First fetch populates cache

- **GIVEN** the local cache contains no pull requests for the target
  repository
- **WHEN** the user runs a fetch
- **THEN** the system writes one row per pull request, including the
  raw GitHub JSON payload, to the storage layer
- **AND** records the fetch time on each row

#### Scenario: Subsequent analysis does not call GitHub

- **GIVEN** a previous fetch has populated the local cache for the
  target repository
- **WHEN** the user runs an analysis command without explicitly
  requesting a refresh
- **THEN** the analysis reads from the local cache only
- **AND** issues zero GitHub API requests

### Requirement: Compute time-to-merge percentiles for merged PRs

The system SHALL compute median, p25, p75, p95, and max of
time-to-merge — the wall-clock duration in days from `created_at` to
`merged_at` — over all merged pull requests in scope.

#### Scenario: Mixed open / closed / merged population

- **GIVEN** the cache contains pull requests in `open`, `closed`, and
  merged states
- **WHEN** the user computes throughput
- **THEN** only pull requests with a non-null `merged_at` contribute
  to the statistics
- **AND** open and unmerged-closed pull requests are excluded

#### Scenario: Reporting on an empty population

- **GIVEN** the in-scope set contains zero merged pull requests
- **WHEN** the user computes throughput
- **THEN** the system reports an empty result set explicitly rather
  than emitting `NaN`, zero, or an error

### Requirement: Filter analysis by merge date with --since

The system SHALL accept a `--since YYYY-MM-DD` option that restricts
the analysis to pull requests merged on or after the given UTC date.

#### Scenario: --since narrows the window

- **GIVEN** the cache contains merged pull requests spanning several
  years
- **WHEN** the user runs throughput analysis with `--since 2025-01-01`
- **THEN** only pull requests whose `merged_at` is on or after
  2025-01-01 UTC contribute to the result

#### Scenario: --since omitted

- **WHEN** the user runs throughput analysis without `--since`
- **THEN** all merged pull requests in the cache contribute to the
  result, with no implicit lower bound

#### Scenario: --since with a malformed value

- **GIVEN** the user supplies `--since` with a value that is not a
  valid `YYYY-MM-DD` UTC date
- **WHEN** the command is invoked
- **THEN** the system exits with a non-zero status and a clear error
  message naming the offending value
- **AND** does not run the analysis

### Requirement: Compute time-to-first-response on an opt-in command

The system SHALL provide a separate command that computes
time-to-first-response — the wall-clock duration in days from a pull
request's `created_at` to the timestamp of the first comment authored
by anyone other than the pull request's author.

#### Scenario: Opt-in command is required

- **GIVEN** the user runs the default throughput command
- **WHEN** the analysis runs
- **THEN** time-to-first-response is not computed and no
  comment-list API calls are issued

#### Scenario: First non-author comment is the one that counts

- **GIVEN** a pull request whose first chronological comment is from
  the pull request author themselves, followed later by a comment
  from a different user
- **WHEN** time-to-first-response is computed for that pull request
- **THEN** the timestamp of the later, non-author comment is used
- **AND** the author's own comment is ignored

#### Scenario: Pull request with no non-author comments

- **GIVEN** a pull request that has either no comments at all, or
  only comments from its own author
- **WHEN** time-to-first-response is computed for that pull request
- **THEN** the pull request contributes no value to the percentile
  calculation
- **AND** is reported in a separate count of "no first response yet"
  so the omission is visible

#### Scenario: First-response data is cached

- **GIVEN** time-to-first-response has been computed once for the
  target repository
- **WHEN** the user runs the same command again without an explicit
  refresh
- **THEN** results are read from the local cache
- **AND** zero GitHub API requests are issued

### Requirement: Render output via the report-rendering capability

The system SHALL emit analysis output through the `report-rendering`
capability rather than printing directly, so that adding new output
formats does not require changes to this capability.

#### Scenario: Default CLI table output

- **WHEN** the user runs an analysis without specifying an output
  format
- **THEN** the system passes the structured result to the
  `report-rendering` CLI-table renderer
- **AND** the rendered table appears on standard output

#### Scenario: JSON output via --json

- **GIVEN** the user passes `--json` on the command line
- **WHEN** an analysis completes
- **THEN** the system passes the structured result to the
  `report-rendering` JSON renderer
- **AND** the rendered JSON is written to standard output with no
  decorative text mixed in
