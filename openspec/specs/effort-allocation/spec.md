# effort-allocation Specification

## Purpose
TBD - created by archiving change effort-allocation. Update Purpose after archive.
## Requirements
### Requirement: Produce a per-author-per-repo effort-allocation pivot

The system SHALL produce an `AnalysisResult` whose rows describe,
for each `(repo, author[, period])` combination present in the
cache, the volume of pull requests submitted and the outcome
breakdown — submissions, merged, merged-rate, self-pulled,
closed-by-maintainer, closed-unenriched, still-open.

#### Scenario: One row per author × repo by default

- **GIVEN** a cache containing pull requests by multiple authors
  across multiple repositories
- **WHEN** the user runs `gitsweeper effort` without `--by-period`
- **THEN** the result has one row per `(repo, author)` combination
- **AND** the columns include `repo`, `author`, `submissions`,
  `merged`, `merged_rate`, `self_pulled`, `closed_by_maintainer`,
  `closed_unenriched`, `still_open`

#### Scenario: --by-period adds a period column

- **GIVEN** the user passes `--by-period`
- **WHEN** the analysis runs
- **THEN** every row also carries a `period` column (ISO week by
  default), and the rows are now `(period, repo, author)` tuples

#### Scenario: --since restricts the window

- **GIVEN** the user passes `--since 2026-01-01`
- **WHEN** the analysis runs
- **THEN** only pull requests whose `created_at` is on or after
  that date contribute to any row

#### Scenario: --repos restricts the portfolio

- **GIVEN** the user passes `--repos owner/a owner/b`
- **WHEN** the analysis runs
- **THEN** only those repositories contribute, regardless of what
  else is in the cache

### Requirement: Distinguish enriched from un-enriched closures

The system SHALL classify each closed-without-merge PR into
exactly one of three buckets: `self_pulled` if the cached close-
actor login matches the PR author case-insensitively,
`closed_by_maintainer` if the cached close-actor login differs,
and `closed_unenriched` if no close-actor row has been persisted
yet — so the operator can see when the data is incomplete and
run `gitsweeper classify`.

#### Scenario: Self-pulled count uses close-actor data

- **GIVEN** a closed-without-merge PR whose close-actor login
  matches the PR author (case-insensitively)
- **WHEN** the effort analysis runs
- **THEN** the PR contributes to `self_pulled`, not to
  `closed_by_maintainer` or `closed_unenriched`

#### Scenario: Maintainer-closed count uses close-actor data

- **GIVEN** a closed-without-merge PR whose close-actor login
  differs from the PR author
- **WHEN** the effort analysis runs
- **THEN** the PR contributes to `closed_by_maintainer`

#### Scenario: Closed-unenriched is reported, not folded into others

- **GIVEN** a closed-without-merge PR that has no row in
  `pr_close_actors` yet
- **WHEN** the effort analysis runs
- **THEN** the PR contributes to `closed_unenriched` rather than
  being silently bucketed into `closed_by_maintainer`
- **AND** the metadata records the count of closed-unenriched
  rows so the operator knows whether to run classify first

### Requirement: Merged rate is computed against effective denominator

The `merged_rate` value SHALL be computed as
`merged / (merged + closed_by_maintainer)` — i.e. the fraction of
PRs that *the maintainers acted on* which actually merged. Self-
pulled PRs are excluded from the denominator (they did not need
maintainer action), as are still-open PRs (the outcome is not yet
known).

#### Scenario: Self-pulled PRs do not deflate merged_rate

- **GIVEN** an author with 5 merged, 0 maintainer-closed, and 3
  self-pulled PRs
- **WHEN** the effort analysis runs
- **THEN** `merged_rate` is reported as 1.0 (5 / 5)
- **AND** `self_pulled` is reported as 3 separately

#### Scenario: Empty effective denominator yields a null merged_rate

- **GIVEN** an author whose only entries are still-open or self-
  pulled PRs
- **WHEN** the effort analysis runs
- **THEN** `merged_rate` is `None` rather than `NaN` or `0`
- **AND** the renderer formats `None` as the standard placeholder

