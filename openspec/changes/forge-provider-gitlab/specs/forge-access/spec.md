## MODIFIED Requirements

### Requirement: Select the forge provider by override or host detection

The system SHALL determine which provider serves a given repository
reference by an explicit `--forge` selection when present, otherwise
by detecting the forge from the host of a fully-qualified reference,
otherwise defaulting to GitHub for a bare `owner/repo`. Registered
providers are GitHub, Forgejo, and GitLab.

#### Scenario: Bare owner/repo defaults to GitHub

- **GIVEN** the user passes a bare reference such as
  `ConductionNL/openregister` with no `--forge`
- **WHEN** the provider is resolved
- **THEN** the GitHub provider is selected
- **AND** behaviour is identical to the pre-abstraction GitHub client

#### Scenario: --forge overrides detection

- **GIVEN** the user passes `--forge github`, `--forge forgejo`, or
  `--forge gitlab`
- **WHEN** the provider is resolved
- **THEN** the named provider is selected regardless of any host in
  the reference

#### Scenario: A Codeberg host is detected as Forgejo

- **GIVEN** the user passes a fully-qualified reference whose host is
  `codeberg.org` (or a configured self-hosted Forgejo host) and no
  `--forge`
- **WHEN** the provider is resolved
- **THEN** the Forgejo provider is selected

#### Scenario: Self-hosted Forgejo base URL is honoured

- **GIVEN** `--forge forgejo` and a self-hosted base URL configured via
  the documented environment variable
- **WHEN** the Forgejo provider issues requests
- **THEN** requests target that base URL's `/api/v1` rather than
  Codeberg's

#### Scenario: A GitLab host is detected as GitLab

- **GIVEN** the user passes a fully-qualified reference whose host is
  `gitlab.com` (or a configured self-hosted GitLab host) and no
  `--forge`
- **WHEN** the provider is resolved
- **THEN** the GitLab provider is selected

#### Scenario: Self-hosted GitLab base URL is honoured

- **GIVEN** `--forge gitlab` and a self-hosted base URL configured via
  the documented environment variable
- **WHEN** the GitLab provider issues requests
- **THEN** requests target that base URL's `/api/v4` rather than
  gitlab.com's

#### Scenario: An unsupported forge is rejected, not guessed

- **GIVEN** the user passes `--forge bitbucket` (no registered
  provider) or a reference whose host maps to no registered provider
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

#### Scenario: Authenticated Forgejo fetch via its token

- **GIVEN** the Forgejo token environment variable is set
- **WHEN** the Forgejo provider issues requests
- **THEN** every request carries the token in the Gitea-style
  `Authorization: token <value>` header

#### Scenario: Authenticated GitLab fetch via its token

- **GIVEN** the `GITLAB_TOKEN` environment variable is set
- **WHEN** the GitLab provider issues requests
- **THEN** every request carries the token in the `PRIVATE-TOKEN`
  header

#### Scenario: Unauthenticated degraded mode

- **GIVEN** the selected provider's token is not set and the forge
  allows anonymous reads
- **WHEN** the user requests a fetch
- **THEN** the system proceeds without an `Authorization` header
- **AND** warns once that the unauthenticated budget is small and the
  fetch may be slow or incomplete for large repositories

### Requirement: Normalize each forge's model to a common shape

The system SHALL map each forge's pull/merge request, commit, and
repository representations onto a single normalized model so that
analysis capabilities reason about merge state, timestamps, author,
and identifiers uniformly, regardless of the source forge's
vocabulary. Each normalized record SHALL retain the provider's
original raw response.

#### Scenario: Merge semantics are uniform across forges

- **GIVEN** a change request the forge considers merged — GitHub's
  `merged_at`, or Forgejo's `merged` flag with its `merged_at`
- **WHEN** it is normalized
- **THEN** the normalized record carries a non-null `merged_at`
  timestamp
- **AND** a closed-without-merge change request carries a null
  `merged_at` and a non-null `closed_at`, identically across forges

#### Scenario: GitLab's distinct vocabulary is normalized away

- **GIVEN** a GitLab merge request with a per-project `iid`, a `state`
  of `opened`, `closed`, or `merged`, and an `author.username`
- **WHEN** it is normalized
- **THEN** `number` is the `iid` (not the global `id`)
- **AND** `state` is `open` for `opened` and `closed` for both
  `closed` and `merged`, with `merged_at` non-null only when the MR
  merged
- **AND** `author` is the `author.username`

#### Scenario: Raw payload is preserved for audit

- **WHEN** any record is normalized by any provider
- **THEN** the provider's original raw response for that record is
  retained on the normalized record, so a re-analysis or audit can
  inspect what the forge actually returned

#### Scenario: A new provider proves conformance via the contract suite

- **GIVEN** a provider implementation (GitHub, Forgejo, or GitLab)
- **WHEN** the shared provider contract-test suite runs against it
- **THEN** the suite asserts the merge-semantics, closed-without-merge,
  raw-retention, and pagination-to-completion invariants hold
- **AND** a future provider joins by passing the same suite, not by
  inventing its own
