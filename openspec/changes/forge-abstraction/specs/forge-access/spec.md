## ADDED Requirements

### Requirement: Provide a forge-agnostic provider interface

The system SHALL expose a `ForgeProvider` interface that analysis
capabilities use to acquire repository data — pull/merge requests,
their comments, commits, and the repositories owned by an
organisation or group — without depending on which concrete forge
(GitHub, Forgejo, GitLab) backs it. Each operation SHALL return the
normalized data model, not a forge's raw response shape.

#### Scenario: A capability acquires PRs without naming a forge

- **GIVEN** an analysis capability needs the pull requests for a
  repository
- **WHEN** it obtains a provider from `forge-access` and calls the
  list-pull-requests operation
- **THEN** it receives normalized pull-request records
- **AND** the capability contains no reference to a specific forge's
  API, headers, or pagination scheme

#### Scenario: The shipped provider set in this change

- **GIVEN** the forge-provider seam exists
- **WHEN** a capability requests a provider
- **THEN** the only concrete provider available is GitHub
- **AND** additional providers (Forgejo, GitLab) can be registered
  later without changing the interface or its consumers

### Requirement: Select the forge provider by override or host detection

The system SHALL determine which provider serves a given repository
reference by an explicit `--forge` selection when present, otherwise
by detecting the forge from the host of a fully-qualified reference,
otherwise defaulting to GitHub for a bare `owner/repo`.

#### Scenario: Bare owner/repo defaults to GitHub

- **GIVEN** the user passes a bare reference such as
  `ConductionNL/openregister` with no `--forge`
- **WHEN** the provider is resolved
- **THEN** the GitHub provider is selected
- **AND** behaviour is identical to the pre-abstraction GitHub client

#### Scenario: --forge overrides detection

- **GIVEN** the user passes `--forge github`
- **WHEN** the provider is resolved
- **THEN** the GitHub provider is selected regardless of any host in
  the reference

#### Scenario: An unsupported forge is rejected, not guessed

- **GIVEN** the user passes `--forge gitlab` (a provider not shipped
  in this change) or a reference whose host maps to no registered
  provider
- **WHEN** the provider is resolved
- **THEN** the system exits with a non-zero status and an error that
  names the requested forge and lists the providers that are
  available
- **AND** does not silently fall back to GitHub

### Requirement: Authenticate per provider via a documented token

The system SHALL authenticate to each forge using that provider's
documented token, and SHALL proceed unauthenticated where the forge
permits it, warning the user once that the unauthenticated rate-limit
budget is small.

#### Scenario: Authenticated GitHub fetch via GITHUB_TOKEN

- **GIVEN** the environment variable `GITHUB_TOKEN` is set
- **WHEN** the GitHub provider issues requests
- **THEN** every request carries the token in an `Authorization`
  header
- **AND** the higher authenticated rate-limit budget applies

#### Scenario: Unauthenticated degraded mode

- **GIVEN** the selected provider's token is not set and the forge
  allows anonymous reads
- **WHEN** the user requests a fetch
- **THEN** the system proceeds without an `Authorization` header
- **AND** warns once that the unauthenticated budget is small and the
  fetch may be slow or incomplete for large repositories

### Requirement: Follow each provider's pagination to completion

Each provider SHALL follow its own forge's pagination mechanism until
no further pages remain, so that every record in scope is captured.

#### Scenario: GitHub pagination via Link header

- **GIVEN** the repository has more records than fit on a single
  GitHub REST page
- **WHEN** the GitHub provider fetches them
- **THEN** it follows the `rel="next"` URL from each response's
  `Link` header until no `next` link remains
- **AND** every record from every page is captured

### Requirement: Honour each provider's rate-limit signals

Each provider SHALL detect and respect its own forge's rate-limit
signals so a long, polite wait is never mistaken for a hang and a
limit is never blown through.

#### Scenario: GitHub primary rate limit reached

- **GIVEN** the GitHub primary rate limit
  (`X-RateLimit-Remaining: 0`) has been hit during a fetch
- **WHEN** the next request would otherwise be sent
- **THEN** the provider waits until the timestamp in
  `X-RateLimit-Reset` before continuing
- **AND** the wait is reported to the user

#### Scenario: GitHub secondary (abuse) rate limit hit

- **GIVEN** GitHub returns `403` or `429` with a `Retry-After` header
- **WHEN** the provider observes that response
- **THEN** it sleeps for the `Retry-After` duration before retrying
  the same idempotent request

### Requirement: Normalize each forge's model to a common shape

The system SHALL map each forge's pull/merge request, commit, and
repository representations onto a single normalized model so that
analysis capabilities reason about merge state, timestamps, author,
and identifiers uniformly, regardless of the source forge's
vocabulary.

#### Scenario: Merge semantics are uniform across forges

- **GIVEN** a change request that the forge considers merged
  (GitHub's `merged_at`, or another forge's equivalent merge marker)
- **WHEN** it is normalized
- **THEN** the normalized record carries a non-null `merged_at`
  timestamp
- **AND** a closed-without-merge change request carries a null
  `merged_at` and a non-null `closed_at`, identically across forges

#### Scenario: Raw payload is preserved for audit

- **WHEN** any record is normalized
- **THEN** the provider's original raw response for that record is
  retained alongside the normalized fields, so a re-analysis or audit
  can inspect what the forge actually returned

### Requirement: Fetch all pull requests for a repository

The system SHALL fetch every pull/merge request belonging to a
specified repository through the selected provider, applying that
provider's pagination and rate-limit behaviour, and returning
normalized records.

#### Scenario: Every page is captured

- **GIVEN** a repository with more pull requests than a single page
- **WHEN** the user requests a fetch
- **THEN** the provider paginates to completion
- **AND** every pull request is captured as a normalized record

### Requirement: Fetch multiple repositories in one invocation

The system SHALL accept multiple repository references to the
`fetch` command and ingest each into the same local cache, applying
the provider's acquisition behaviour once per repository in sequence.

#### Scenario: Multiple repos passed as positional arguments

- **GIVEN** the user runs
  `gitsweeper fetch ConductionNL/openregister ConductionNL/opencatalogi`
- **WHEN** the command runs
- **THEN** both repositories are fetched and persisted into the same
  cache
- **AND** progress for each repository is reported in turn so a long
  total run is not mistaken for a hang

#### Scenario: Per-repo failures do not abort the whole batch

- **GIVEN** one of several references returns a permanent error from
  its forge (for example a 404 because the repo was renamed)
- **WHEN** the fetch command processes that reference
- **THEN** the error is reported on stderr with the offending
  reference
- **AND** the remaining repositories are still fetched
- **AND** the command exits with a non-zero status to signal partial
  failure while preserving the data that did fetch

### Requirement: Fetch every repository in an organisation

The system SHALL accept `--org <name>` on the `fetch` command,
listing every repository owned by that organisation that the
authenticated user can read through the selected provider, and
ingesting each as if its reference had been passed positionally.

#### Scenario: --org expands to every repo in the org

- **GIVEN** the user runs `gitsweeper fetch --org ConductionNL`
- **WHEN** the organisation has more repositories than fit on a
  single page
- **THEN** the provider paginates the repository listing to
  completion
- **AND** each enumerated repository is fetched into the cache

#### Scenario: --org and positional repos can be combined

- **GIVEN** the user supplies both `--org ConductionNL` and a
  positional reference
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

### Requirement: Fetch commits for a repository

The system SHALL fetch commits for a repository through the selected
provider, optionally bounded by a `since` timestamp and a branch,
applying the provider's pagination and rate-limit behaviour.

#### Scenario: Commits bounded by since and branch

- **GIVEN** a repository and an ISO 8601 `since` timestamp and a
  branch name
- **WHEN** the commits are fetched
- **THEN** only commits on that branch at or after `since` are
  returned, paginated to completion
- **AND** when the branch is omitted the repository's default branch
  is used
