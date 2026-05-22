## Why

Billbird's `/log` is the explicit time-source: developers type `/log 2h` in an issue comment. The companion `dev-time hook` (documented in Billbird's repo) is the implicit one: a Claude Code pre-commit hook suggests a `Time: 1h30m` footer on every commit, the dev confirms or edits, the line lands in git history.

Two sources means we can cross-check. A reconciliation tool pulls both, groups them per `(repository, author, issue)`, computes drift, and surfaces every gap that needs attention — forgotten `/log`s, over-logged sessions, work that never made it to commit.

This is the missing piece that closes the loop on the time-tracking story. Without it, the hook is just a footer in `git log` that nobody reads.

## What Changes

- New capability `commit-time-reconcile`:
  - Fetches commits from a repo via the GitHub REST API (`GET /repos/{owner}/{repo}/commits`), optionally scoped to a branch and a since-date
  - Parses `Time: <duration>` footers out of each commit message (regex, multi-line tolerant)
  - Parses issue references (`#42`, `Closes #42`, `Fixes #42`) so commits can be associated with the issue they touched
  - Pulls Billbird's `/api/v1/time-entries` for the same period via the existing `lib/billbird_client.py`
  - Aggregates both sides per `(repo, author, issue)` and per `(repo, author)`
  - Emits an `AnalysisResult` with rows: scope label, minutes-from-commits, minutes-from-logs, drift, status (`aligned` / `commits_only` / `logs_only` / `over_committed` / `over_logged`)
- New CLI command `gitsweeper reconcile <repo> [--since YYYY-MM-DD] [--branch main] [--author X] [--json]`
- New MCP tool `gitsweeper_reconcile(repository, since?, branch?, author?)` returning the same structured payload
- Shared library bits:
  - `lib/commit_time.py` — pure regex + parser, no I/O. Extracts `Time:` footer and issue references from a commit message.
  - `lib/github_client.py` gains a `list_commits(owner, name, since=, sha=)` method, mirroring the existing PR fetcher
- Documentation: a "Reconciliation" section in `docs/mcp.md` and a new `docs/reconcile.md` covering the model, the drift categories, and example output

## Capabilities

### New Capabilities
- `commit-time-reconcile`: extract `Time:` footers from commits, fetch matching Billbird `/log` entries, aggregate and classify per `(repo, author, issue)`. Pure read-only; never writes back to git, GitHub, or Billbird.

### Modified Capabilities
<!-- none -->

## Impact

- **Code (Python)**: one new lib module (`commit_time.py`), one new capability (`commit_time_reconcile.py`), one new typer CLI command, one new MCP tool entry in the registry, one new GitHub-client method.
- **Dependencies**: none added. Re-uses `httpx`, `polars` is optional (small grouping; pure Python is sufficient), and the existing `billbird_client.py`.
- **GitHub API budget**: one paginated call per `reconcile` run. Cached in the existing SQLite cache after the first run, so subsequent runs cost zero unless `--refresh` is supplied.
- **Backwards compatibility**: additive. All existing commands and MCP tools unchanged.
