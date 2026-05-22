# commit-time-reconcile Specification

## Purpose
TBD - created by archiving change gitsweeper-billbird-reconcile. Update Purpose after archive.
## Requirements
### Requirement: Extract Time footers from commit messages

The system SHALL parse a `Time: <duration>` footer out of a commit message. The duration SHALL accept the same formats as Billbird's `/log` (hours `2h`, minutes `45m`, combined `1h30m`). The match SHALL be anchored to its own line (multiline `^…$`). At most one footer per commit; if multiple appear, the last one wins.

#### Scenario: Standard footer
- **WHEN** parsing the message `"fix the regression\n\nTime: 1h30m"`
- **THEN** the parser returns `90` minutes

#### Scenario: Minutes-only footer
- **WHEN** parsing the message `"small refactor\n\nTime: 45m"`
- **THEN** the parser returns `45` minutes

#### Scenario: No footer
- **WHEN** parsing a message with no `Time:` line
- **THEN** the parser returns `None`

#### Scenario: Multiple footers, last wins
- **WHEN** parsing `"feat\n\nTime: 1h\n\namended\n\nTime: 2h"`
- **THEN** the parser returns `120` (the last footer)

#### Scenario: Footer is case-insensitive on the prefix
- **WHEN** parsing `"work\n\ntime: 30m"`
- **THEN** the parser returns `30`

### Requirement: Extract issue references from commit messages

The system SHALL parse issue numbers from a commit message via `#N`-style references. `Closes #N`, `Fixes #N`, `Refs #N`, and bare `#N` SHALL all count. Cross-repo references (`owner/repo#N`) SHALL NOT be associated with the current repo; they SHALL be ignored.

#### Scenario: Closes reference
- **WHEN** parsing `"Closes #42: rewrite the parser"`
- **THEN** the parser returns issue numbers `[42]`

#### Scenario: Multiple references
- **WHEN** parsing `"fixes #5, related to #7"`
- **THEN** the parser returns issue numbers `[5, 7]` deduplicated

#### Scenario: Cross-repo reference ignored
- **WHEN** parsing `"see other/repo#10"`
- **THEN** the parser returns `[]`

### Requirement: Fetch commits from a repo

The system SHALL expose a `list_commits(owner, name, *, since, sha)` method on the GitHub client. It SHALL paginate over `GET /repos/{owner}/{name}/commits` using the existing `Link rel=next` machinery. The `since` parameter SHALL accept an ISO 8601 timestamp and SHALL be passed through verbatim to GitHub. The `sha` parameter SHALL accept a branch name (default: the repo's default branch).

#### Scenario: Recent commits on the default branch
- **WHEN** the client calls `list_commits("MWest2020", "Billbird", since="2026-05-01T00:00:00Z")`
- **THEN** the iterator yields every commit on the default branch from that timestamp forward, paginated transparently

#### Scenario: Commits on a non-default branch
- **WHEN** the client calls `list_commits("MWest2020", "Billbird", sha="smoke-fixtures")`
- **THEN** the iterator yields commits on the `smoke-fixtures` branch

### Requirement: Reconcile commit footers against Billbird logs

The system SHALL expose a reconciliation function that:

1. Fetches commits via `list_commits` for the given repo and range
2. Parses each commit message for `Time:` footers and `#N` issue references
3. Pulls Billbird time entries for the same period via `BillbirdClient.time_entries`
4. Groups both sides per `(repository, author, issue_number)` — falling back to `(repository, author, *)` for commits without an issue reference
5. Computes `drift_minutes = logged_minutes - commit_minutes` per group
6. Classifies each group:
   - `aligned` if `|drift| <= max(15min, 10% of commit_minutes)`
   - `commits_only` if commit_minutes > 0 and logged_minutes == 0
   - `logs_only` if logged_minutes > 0 and commit_minutes == 0
   - `over_committed` if commit_minutes - logged_minutes > tolerance
   - `over_logged` if logged_minutes - commit_minutes > tolerance

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

### Requirement: CLI command `gitsweeper reconcile`

The system SHALL register a typer command `gitsweeper reconcile <repo> [--since] [--branch] [--author] [--json]` that runs the reconciliation function against the local cache (refreshing commits from GitHub if absent) and emits the result through the existing rendering capability.

#### Scenario: Default invocation
- **WHEN** an operator runs `gitsweeper reconcile MWest2020/Billbird --since 2026-05-01`
- **THEN** the CLI prints a table with rows per `(repo, author, issue)` showing commit minutes, log minutes, drift, and status

#### Scenario: Missing Billbird config
- **WHEN** `BILLBIRD_API_URL` or `BILLBIRD_API_TOKEN` is unset
- **THEN** the command exits non-zero with a clear message naming the missing var

### Requirement: MCP tool `gitsweeper_reconcile`

The system SHALL register an MCP tool that wraps the reconciliation function. The input schema SHALL accept `repository` (owner/name), and optional `since` (ISO date), `branch`, `author`. The output SHALL include `unit: "minutes"`, the resolved `scope`, and a `rows` array with one entry per `(repo, author, issue)` group.

#### Scenario: MCP tool returns structured rows
- **WHEN** the tool is invoked with `{repository: "org/repo", since: "2026-05-01"}`
- **THEN** the response has `unit: "minutes"`, an echo of the scope, and a `rows` array

#### Scenario: Tool propagates Billbird configuration errors
- **WHEN** the tool is invoked while `BILLBIRD_API_TOKEN` is unset
- **THEN** the response is the structured `{"error": "billbird_not_configured", "missing": [...], "docs": "docs/mcp.md"}` envelope used by other Billbird-touching tools

