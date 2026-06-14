# retro-signals Specification

## Purpose
TBD - created by archiving change retro-signals. Update Purpose after archive.
## Requirements
### Requirement: Persist PR comment bodies in a local comments cache

The system SHALL fetch a repository's PR comments through the provider's
comment listing and persist each comment's author, creation time, and body in
a local `pr_comments` cache, so retro signals run from cache without
re-fetching, consistent with the existing PR cache.

#### Scenario: First retro run populates the comments cache

- **GIVEN** a repository whose comments are not yet cached
- **WHEN** the user runs `gitsweeper retro <repo>`
- **THEN** the system fetches comments via the provider and writes one row per
  comment (author, created_at, body) to `pr_comments`
- **AND** a subsequent run reads from the cache without re-fetching unless a
  refresh is requested

### Requirement: Detect stale open pull requests

The system SHALL report pull requests still in the open state whose
`created_at` is older than a configurable threshold (default 14 days), as the
PR-cache analogue of sprint spillover.

#### Scenario: Open PRs past the staleness threshold are listed

- **GIVEN** open PRs of varying age and merged/closed PRs
- **WHEN** the user runs `retro`
- **THEN** only open PRs older than the threshold are listed, by PR number
- **AND** merged or closed PRs never appear in the stale list

### Requirement: Detect long discussion threads

The system SHALL report pull requests whose comment count exceeds a
configurable threshold (default 10).

#### Scenario: Heavily-discussed PRs are surfaced

- **GIVEN** PRs with varying comment counts in the cache
- **WHEN** the user runs `retro`
- **THEN** PRs with more than the threshold number of comments are listed by
  number, highest first

### Requirement: Count friction language deterministically

The system SHALL count occurrences of a documented bilingual (Dutch + English)
friction-keyword set in comment bodies and PR titles, case-insensitively, and
report the PRs with the most matches. No LLM or external service is used.

#### Scenario: Friction keywords are matched and ranked

- **GIVEN** comments and titles containing phrases from the friction set
  (e.g. "loopt vast", "blocked", "waiting on")
- **WHEN** the user runs `retro`
- **THEN** the system reports the top PRs by friction-match count, with the
  count, by PR number
- **AND** the matching is reproducible from the text alone, with no network
  call

#### Scenario: The keyword sets are documented constants

- **WHEN** a maintainer reviews the capability
- **THEN** the friction and tech-debt keyword sets are documented module
  constants, not scattered literals

### Requirement: Count tech-debt markers deterministically

The system SHALL count occurrences of a documented tech-debt keyword set
(e.g. `hack`, `workaround`, `TODO`, `tijdelijk`) in comment bodies and PR
titles, case-insensitively, and report the total plus the PRs carrying them.

#### Scenario: Tech-debt markers are counted

- **GIVEN** comments/titles containing tech-debt keywords
- **WHEN** the user runs `retro`
- **THEN** the system reports the marker total and the PRs that carry them, by
  number

### Requirement: Surface smooth pull requests

The system SHALL report pull requests that merged quickly (within a
configurable window, default 3 days) with fewer than a small number of
comments, as a positive counterpart to the friction signals.

#### Scenario: Fast, low-friction merges are highlighted

- **GIVEN** merged PRs of varying speed and comment count
- **WHEN** the user runs `retro`
- **THEN** PRs merged within the window with few comments are listed by number

### Requirement: Retro signals are team-level only

The system SHALL report all retro signals at team level. The `retro` command
SHALL NOT accept an author filter, and its output SHALL reference pull requests
by number only — never author logins, names, or `@`-mentions — even though
comment authors are stored in the cache.

#### Scenario: No per-person data in the output

- **WHEN** the user runs `retro` in any mode (table or JSON)
- **THEN** the output contains no author login, name, or per-author figure
- **AND** the command exposes no `--author` option

### Requirement: Render via the report-rendering capability

The system SHALL emit retro signals through the `report-rendering` capability
(CLI table by default, JSON via `--json`).

#### Scenario: Empty signals are reported explicitly

- **GIVEN** a window with no stale PRs, long threads, friction, or tech-debt
  matches
- **WHEN** the user runs `retro`
- **THEN** the system reports each signal as empty explicitly rather than
  erroring or emitting nothing

