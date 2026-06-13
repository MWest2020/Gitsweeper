## ADDED Requirements

### Requirement: Acquire pull requests through the forge-access capability

The system SHALL obtain pull/merge requests through the
`forge-access` capability rather than calling any forge's API
directly, so that throughput analysis is identical regardless of
which forge backs the repository.

#### Scenario: Throughput analysis is forge-agnostic

- **GIVEN** a repository whose pull requests have been fetched via
  `forge-access`
- **WHEN** the user runs throughput analysis
- **THEN** the percentile, `--since`, `--author`, first-response, and
  temporal-pattern requirements operate on the normalized records
- **AND** the analysis code contains no reference to a specific
  forge's API, headers, pagination, or rate-limit handling

## REMOVED Requirements

### Requirement: Fetch all pull requests for a repository

**Reason**: Data acquisition is no longer GitHub-specific. The
requirement (with its pagination, primary/secondary rate-limit,
authenticated-fetch, and unauthenticated-degraded scenarios) moves to
the new `forge-access` capability, generalised across forges.

**Migration**: The same behaviour is provided by `forge-access` →
"Fetch all pull requests for a repository", "Follow each provider's
pagination to completion", "Honour each provider's rate-limit
signals", and "Authenticate per provider via a documented token".
No CLI change for GitHub users.

### Requirement: Fetch multiple repositories in one invocation

**Reason**: Multi-repo acquisition is a forge-access concern, not a
throughput concern, now that acquisition is centralised behind the
provider seam.

**Migration**: Provided verbatim by `forge-access` → "Fetch multiple
repositories in one invocation". The `gitsweeper fetch a/b c/d`
command and its per-repo-failure behaviour are unchanged.

### Requirement: Fetch every repository in a GitHub organisation

**Reason**: Organisation expansion belongs with the provider that
knows how to enumerate an org (or, for other forges, a group). It
moves to `forge-access` and loses its GitHub-specific framing.

**Migration**: Provided by `forge-access` → "Fetch every repository
in an organisation". `gitsweeper fetch --org <name>` is unchanged for
GitHub; group enumeration for other forges arrives with their
provider follow-on changes.
