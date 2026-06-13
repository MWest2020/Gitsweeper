## ADDED Requirements

### Requirement: Acquire commits through the forge-access capability

The system SHALL obtain the commits it reconciles through the
`forge-access` capability rather than calling any forge's API
directly, so reconcile works against any supported forge.

#### Scenario: Reconcile sources commits via forge-access

- **GIVEN** a repository whose commits are needed for reconciliation
- **WHEN** `gitsweeper reconcile` runs
- **THEN** commits are fetched via `forge-access` with its `since`
  and branch bounds
- **AND** the footer-extraction and Billbird-matching requirements
  operate on those commits unchanged

## REMOVED Requirements

### Requirement: Fetch commits from a repo

**Reason**: Commit acquisition is a forge-access concern now that all
forge access is centralised behind the provider seam. The reconcile
capability keeps its footer-extraction and matching logic.

**Migration**: Provided by `forge-access` → "Fetch commits for a
repository", which carries the same `since`-bounded, branch-scoped,
paginated behaviour. No CLI change.
