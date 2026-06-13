## ADDED Requirements

### Requirement: Compute the four DORA metrics from the cached pull requests

The system SHALL compute deployment frequency, lead time for changes, change
failure rate, and time to restore service for a repository from its locally
cached pull requests, without issuing forge API calls, scoped by an optional
`--since` lower bound and bucketed by a `--period` of `week` or `month`.

#### Scenario: Metrics computed from cache only

- **GIVEN** a repository whose pull requests are already in the local cache
- **WHEN** the user runs `gitsweeper dora <repo>`
- **THEN** the four DORA metrics are computed from the cached pull requests
- **AND** zero forge API requests are issued

#### Scenario: Works identically across forges

- **GIVEN** cached pull requests originally fetched from GitHub, Forgejo, or
  GitLab
- **WHEN** DORA metrics are computed
- **THEN** the computation path is the same regardless of source forge,
  reading only the normalized fields and the `title` from the stored payload

### Requirement: Deployment frequency as merges per period

The system SHALL report deployment frequency as the count of merged pull
requests per `--period` bucket (a merge is treated as a deployment), plus a
headline rate, over the scoped window.

#### Scenario: Merges bucketed by period

- **GIVEN** merged pull requests spread across several weeks
- **WHEN** the user runs `dora --period week`
- **THEN** the result contains, per week bucket in the window, the count of
  pull requests whose `merged_at` falls in that bucket
- **AND** a headline deployment-frequency figure derived from those buckets

### Requirement: Lead time for changes as merged-PR cycle time

The system SHALL report lead time for changes as the median, p75, and p90 of
the duration from `created_at` to `merged_at` over merged pull requests in
scope.

#### Scenario: Only merged PRs contribute

- **GIVEN** the cache holds open, closed-unmerged, and merged pull requests
- **WHEN** lead time is computed
- **THEN** only pull requests with a non-null `merged_at` contribute
- **AND** the percentiles are reported in a consistent time unit

### Requirement: Change failure rate from a deterministic corrective-PR heuristic

The system SHALL classify a merged pull request as corrective when its title
matches a documented, deterministic keyword set (a leading `revert`,
`hotfix`, or `rollback`, or a conventional-commit `fix:` / `fix(...):`
prefix), case-insensitively, and SHALL report change failure rate as the
fraction of merged pull requests that are corrective. No LLM or external
service is used.

#### Scenario: Corrective share is the rate

- **GIVEN** a set of merged pull requests of which some titles match the
  corrective keyword set
- **WHEN** change failure rate is computed
- **THEN** the rate is (corrective merged PRs) ÷ (all merged PRs)
- **AND** the classification is reproducible from the titles alone, with no
  network call

#### Scenario: The keyword set is documented and inspectable

- **WHEN** a maintainer reviews the capability
- **THEN** the corrective keyword set is a single documented constant, not
  scattered literals, so it can be audited and adjusted

### Requirement: Time to restore service from corrective-PR cycle time

The system SHALL report time to restore service as the median duration from
`created_at` to `merged_at` over the corrective (fix/revert/hotfix) merged
pull requests in scope.

#### Scenario: Restore time over corrective PRs

- **GIVEN** the corrective merged pull requests identified by the heuristic
- **WHEN** time to restore is computed
- **THEN** it is the median of their `created_at` → `merged_at` durations

### Requirement: Metrics are team-level only

The system SHALL report DORA metrics at team level only. The `dora` command
SHALL NOT accept an author filter, and its result SHALL NOT contain author
logins, names, `@`-mentions, or any per-person breakdown.

#### Scenario: No per-person data in the output

- **WHEN** the user runs `dora` in any mode (table or JSON)
- **THEN** the output contains no author login, name, or per-author figure
- **AND** the command exposes no `--author` option

### Requirement: Annotate each metric with its DORA performance band

The system SHALL annotate each of the four metrics with a DORA performance
band (Elite, High, Medium, or Low) using documented threshold constants, and
SHALL report the underlying count alongside each metric so a band based on a
small sample is visible as such.

#### Scenario: Band accompanies each metric

- **WHEN** the metrics are reported
- **THEN** each carries its Elite/High/Medium/Low band and the sample count it
  was computed from

### Requirement: Render via the report-rendering capability

The system SHALL emit the DORA report through the `report-rendering`
capability — a CLI table by default and JSON via `--json` — rather than
printing directly.

#### Scenario: Empty population is reported explicitly

- **GIVEN** the scoped window contains zero merged pull requests
- **WHEN** the user runs `dora`
- **THEN** the system reports an empty result explicitly (no `NaN`, no
  division-by-zero, no crash), naming the empty window
