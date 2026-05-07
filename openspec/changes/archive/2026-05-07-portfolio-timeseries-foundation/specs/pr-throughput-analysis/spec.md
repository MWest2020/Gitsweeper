## ADDED Requirements

### Requirement: Fetch multiple repositories in one invocation

The system SHALL accept multiple `owner/repo` arguments to the
`fetch` command and ingest each repository into the same local
cache, applying the existing pagination and rate-limit behaviour
once per repository in sequence.

#### Scenario: Multiple repos passed as positional arguments

- **GIVEN** the user runs
  `gitsweeper fetch ConductionNL/openregister ConductionNL/opencatalogi`
- **WHEN** the command runs
- **THEN** both repositories are fetched and persisted into the
  same `repositories` table within the same SQLite cache
- **AND** progress for each repository is reported in turn so a
  long total run is not mistaken for a hang

#### Scenario: Per-repo failures do not abort the whole batch

- **GIVEN** the second of three `owner/repo` arguments returns a
  permanent error from GitHub (for example a 404 because the repo
  was renamed)
- **WHEN** the fetch command processes that argument
- **THEN** the error is reported on stderr with the offending
  `owner/repo`
- **AND** the remaining repositories are still fetched
- **AND** the command exits with a non-zero status to signal partial
  failure, while preserving the data that did fetch

### Requirement: Fetch every repository in a GitHub organisation

The system SHALL accept `--org <name>` on the `fetch` command,
listing every repository owned by that organisation that the
authenticated user can read, and ingesting each one as if its
`owner/repo` had been passed positionally.

#### Scenario: --org expands to every repo in the org

- **GIVEN** the user runs `gitsweeper fetch --org ConductionNL`
- **WHEN** the org has more repositories than fit on a single REST
  page
- **THEN** the system follows the `Link rel=next` chain until every
  repository is enumerated
- **AND** each enumerated repository is fetched into the cache

#### Scenario: --org and positional repos can be combined

- **GIVEN** the user supplies both `--org ConductionNL` and the
  positional argument `nextcloud/app-certificate-requests`
- **WHEN** the command runs
- **THEN** every repo from the org plus the positional repo are
  fetched
- **AND** a repo that appears in both sources is fetched only once

#### Scenario: Empty or missing org reports clearly

- **GIVEN** `--org` names an organisation that returns zero
  repositories or does not exist
- **WHEN** the command runs
- **THEN** the system exits with a non-zero status and a message
  naming the offending org
- **AND** does not attempt to fetch any positional repositories
  unless those were also given (they are still attempted)
