## ADDED Requirements

### Requirement: Filter analysis by submitter with --author

The system SHALL accept an `--author <login>` option on the
throughput and first-response commands that restricts the analysis
to pull requests authored by the given GitHub login.

#### Scenario: --author narrows the population

- **GIVEN** the cache contains pull requests from many different
  authors
- **WHEN** the user runs throughput analysis with
  `--author MWest2020`
- **THEN** only pull requests whose author login equals "MWest2020"
  contribute to the result
- **AND** the resulting count and percentiles reflect that subset
  only

#### Scenario: --author combined with --since

- **GIVEN** the user supplies both `--since 2025-01-01` and
  `--author MWest2020`
- **WHEN** the analysis runs
- **THEN** only pull requests authored by "MWest2020" and merged on
  or after 2025-01-01 contribute to the result

#### Scenario: --author with no matching pull requests

- **GIVEN** the cache contains no pull requests by the requested
  login
- **WHEN** the user runs the analysis with that `--author`
- **THEN** the system reports an empty result with count 0 (rather
  than emitting `NaN`, zero, or an error)
- **AND** the metadata records the requested author so the empty
  result is interpretable

#### Scenario: --author treated as case-sensitive

- **GIVEN** GitHub treats login matching as case-insensitive but
  stores logins in their canonical case
- **WHEN** the user supplies `--author mwest2020` (different case
  from the canonical `MWest2020`)
- **THEN** the system performs a case-insensitive match against
  stored logins so the user is not silently fed an empty result by a
  case-mismatch

### Requirement: Compute temporal patterns of submissions and responses

The system SHALL provide a temporal-pattern analysis that reports
the distribution of pull-request submissions and of first-responses
across days of the week and hours of the day, scoped optionally by
`--since` and `--author`.

#### Scenario: Day-of-week distribution for submissions and responses

- **GIVEN** the cache contains pull requests with `created_at`
  timestamps and `pr_first_responses` with `first_response_at`
  timestamps
- **WHEN** the user requests the temporal-patterns analysis for a
  repository
- **THEN** the result contains, for each weekday Monday through
  Sunday in UTC, the count of submissions whose `created_at` fell on
  that weekday and the count of first-responses whose
  `first_response_at` fell on that weekday

#### Scenario: Hour-of-day distribution

- **WHEN** the user requests the temporal-patterns analysis
- **THEN** the result also contains, for each integer hour 0..23 UTC,
  the count of submissions and the count of first-responses landing
  in that hour

#### Scenario: Median first-response by submission day-of-week

- **WHEN** the user requests the temporal-patterns analysis
- **THEN** the result contains, for each weekday, the median
  time-to-first-response in days for pull requests submitted on that
  weekday
- **AND** weekdays with zero qualifying pull requests are reported
  with a sample size of 0 rather than omitted, so the absence is
  visible

#### Scenario: --author scopes the temporal analysis

- **GIVEN** the user supplies `--author MWest2020`
- **WHEN** the temporal-patterns analysis runs
- **THEN** all reported counts and medians cover only pull requests
  authored by that login
