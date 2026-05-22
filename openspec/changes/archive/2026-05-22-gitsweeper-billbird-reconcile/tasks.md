## 1. Parser (`lib/commit_time.py`)

- [x] 1.1 `parse_time_footer(message: str) -> int | None` — minutes; last footer wins; case-insensitive on the prefix
- [x] 1.2 `parse_issue_refs(message: str) -> list[int]` — same-repo `#N`-style only; cross-repo `owner/repo#N` ignored; deduplicated
- [x] 1.3 Unit tests for both functions (≥10 cases including edge: trailing whitespace, multiple footers, cross-repo refs)

## 2. GitHub client extension

- [x] 2.1 `lib/github_client.py` gains `list_commits(owner, name, *, since=None, sha=None)` — paginated, mirrors `list_pull_requests` shape
- [x] 2.2 Returns iterator of dicts with at least `sha`, `commit.author.name`, `commit.author.email`, `commit.message`, `commit.author.date`
- [x] 2.3 Unit test with pytest-httpx mock covering pagination + since-filter

## 3. Capability (`capabilities/commit_time_reconcile.py`)

- [x] 3.1 `reconcile(conn, owner, name, *, since, branch, author, billbird, refresh) -> AnalysisResult`
- [x] 3.2 Aggregates per `(repo, author, issue)` and per `(repo, author, null)` for unreferenced
- [x] 3.3 Classifier with tolerance `max(15min, 10% of commit_minutes)` and the five status values
- [x] 3.4 No persistence of commit data needed for v1; we can re-fetch on each run (small repos). Caching as follow-up.

## 4. CLI

- [x] 4.1 New `gitsweeper reconcile <repo>` typer command with `--since`, `--branch`, `--author`, `--json`
- [x] 4.2 Pre-flight check: `BILLBIRD_API_URL` and `BILLBIRD_API_TOKEN` — fail loud with named missing var

## 5. MCP tool

- [x] 5.1 New tool `gitsweeper_reconcile` in `capabilities/manager_mcp/registry.py` and `tools.py`
- [x] 5.2 Same Billbird-not-configured envelope shape as the existing tools
- [x] 5.3 Updated tool-count assertion in `tests/test_manager_mcp.py` (10 instead of 9)

## 6. Tests

- [x] 6.1 Pure unit tests on `lib/commit_time.py` — done in §1.3
- [x] 6.2 Unit test for the classifier (drift / tolerance / status mapping) — pure function, easy
- [x] 6.3 End-to-end test with fake-Billbird HTTP server + pytest-httpx for GitHub: feed canned commits + canned log entries, assert the AnalysisResult rows match

## 7. Documentation

- [x] 7.1 New `docs/reconcile.md` — model, drift categories, example output, link to Billbird's `docs/dev-time-hook.md`
- [x] 7.2 `docs/mcp.md` gains the new tool in the list table and the smoke-test guidance

## 8. Live verification

- [x] 8.1 Create a `smoke-fixtures` branch on MWest2020/Billbird with 4-6 commits with `Time:` footers referencing real test issues
- [x] 8.2 Make matching `/log` entries via `gh issue comment` on the same issues — some aligned, some intentionally drifted
- [x] 8.3 Run `gitsweeper reconcile MWest2020/Billbird --branch smoke-fixtures --since 2026-05-21` and verify the table calls out the right drifts

## Notes

- No new dependencies. Standard library + httpx + the existing Gitsweeper lib shelf.
- The HTML "Reconciliation" card in `gitsweeper publish` is intentionally **not** part of this change. It comes later if it adds value beyond the CLI + MCP.
- No caching of commit data this round. Re-fetch every run — repos in scope have hundreds of commits, not millions. If we hit a scale wall, add a `commits` cache table the same way pull_requests works today.
