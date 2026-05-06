# pr-process-report Specification

## Purpose
TBD - created by archiving change reusable-process-report. Update Purpose after archive.
## Requirements
### Requirement: Generate a single shareable markdown report

The system SHALL provide a `report` command that runs the full
analysis suite (volume, time-to-merge, time-to-first-response,
classification, temporal patterns) for a given repository and emits
a single markdown document suitable for sharing with a process
owner outside the gitsweeper toolchain.

#### Scenario: Default report against the local cache

- **GIVEN** the repository has already been fetched (and optionally
  enriched and first-response-computed) so the cache is populated
- **WHEN** the user runs `gitsweeper report owner/repo`
- **THEN** the system emits a markdown document on standard output
- **AND** the document contains, in order, sections for volume,
  time-to-merge, time-to-first-response, classification, and
  temporal patterns

#### Scenario: Output written to a file with --out

- **GIVEN** the user runs the report command with
  `--out path/to/report.md`
- **WHEN** the command completes
- **THEN** the markdown document is written to that path
- **AND** standard output stays clean (no decorative banners) so the
  command is safe to script around

#### Scenario: Author scope

- **GIVEN** the user supplies `--author MWest2020`
- **WHEN** the report runs
- **THEN** every analysis section is computed against MWest2020's
  pull requests only
- **AND** the document explicitly states the author scope so the
  report is not later confused with a repo-wide one

### Requirement: Report sections use the rendering capability, not direct printing

The system SHALL produce each section of the report by passing a
structured `AnalysisResult` to the markdown renderer from the
`report-rendering` capability, never by formatting markdown
directly inside the report capability.

#### Scenario: No analysis logic in rendered text

- **GIVEN** a section of the report is produced
- **WHEN** the rendered markdown is inspected
- **THEN** the values that appear in it correspond to the values in
  the underlying `AnalysisResult` (with formatting only)
- **AND** computation, filtering, and ordering decisions are visible
  in the analysis layer, not in the rendering layer

### Requirement: Report fetches and enriches lazily but explicitly

The system SHALL run `report` against whatever data is present in
the local cache, and SHALL refuse to silently issue many GitHub API
calls without the user opting in.

#### Scenario: Missing data causes a clear error rather than auto-fetch

- **GIVEN** the cache contains no pull requests for the requested
  repository
- **WHEN** the user runs `gitsweeper report owner/repo`
- **THEN** the command exits with a non-zero status and a message
  telling the user to run `gitsweeper fetch owner/repo` first
- **AND** issues zero GitHub API requests

#### Scenario: --refresh runs fetch + first-response + classify before report

- **GIVEN** the user supplies `--refresh`
- **WHEN** the report command runs
- **THEN** the system fetches pull requests, computes
  first-responses for any uncached, and classifies any
  uncached-and-closed-without-merge pull requests, in that order,
  before composing the markdown
- **AND** any sleeps or notices from those phases are visible to the
  user (so a long pause is not mistaken for a hang)

