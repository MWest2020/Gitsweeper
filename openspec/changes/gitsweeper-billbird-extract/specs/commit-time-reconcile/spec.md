## MODIFIED Requirements

### Requirement: Reconcile commit footers against Billbird logs

The system SHALL expose a reconciliation function that:

1. Fetches commits via `list_commits` for the given repo and range
2. Parses each commit message for `Time:` footers and `#N` issue references
3. Pulls Billbird time entries for the same period via `BillbirdClient` **imported from the external `billbird-client` package** (declared as an optional dependency under the `billbird` extra)
4. Groups both sides per `(repository, author, issue_number)` — falling back to `(repository, author, *)` for commits without an issue reference
5. Computes `drift_minutes = logged_minutes - commit_minutes` per group
6. Classifies each group:
   - `aligned` if `|drift| <= max(15min, 10% of commit_minutes)`
   - `commits_only` if commit_minutes > 0 and logged_minutes == 0
   - `logs_only` if logged_minutes > 0 and commit_minutes == 0
   - `over_committed` if commit_minutes - logged_minutes > tolerance
   - `over_logged` if logged_minutes - commit_minutes > tolerance

When the `billbird-client` package is not installed, the reconciliation function SHALL raise a clear error (or, at the MCP boundary, return a structured `billbird_client_unavailable` envelope) instead of failing with an import error. Reconcile is the **only** Billbird-touching capability that remains in Gitsweeper; everything else in the Billbird-data space lives in `billbird-client` directly.

#### Scenario: Aligned commit and log
- **WHEN** issue #5 has commits summing 2h and a `/log 2h05m` entry
- **THEN** the row classifies as `aligned` (5m drift within tolerance)

#### Scenario: Commit without log
- **WHEN** a commit footers 1h on issue #7 but no `/log` exists
- **THEN** the row classifies as `commits_only` with drift `-60` minutes

#### Scenario: Log without commit
- **WHEN** `/log 3h` exists on issue #9 but no commit referencing #9 has a `Time:` footer
- **THEN** the row classifies as `logs_only` with drift `+180` minutes

#### Scenario: Commits without an issue reference
- **WHEN** a commit footers 1h and references no issue
- **THEN** the reconcile groups it under `(repo, author, null)` — still classifiable, just not issue-attributable

#### Scenario: Missing optional dependency
- **WHEN** the `billbird-client` package is not installed and the reconcile capability is invoked
- **THEN** the CLI exits non-zero with a message naming the package and the install command; the MCP tool returns `{"error": "billbird_client_unavailable", ...}`
