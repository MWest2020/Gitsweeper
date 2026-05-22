# Reconcile commits vs Billbird /log

`gitsweeper reconcile` cross-checks two time-sources that should agree:

- **`Time:` footers in commit messages** — written by the optional [Billbird dev-time hook](https://github.com/MWest2020/Billbird/blob/main/docs/dev-time-hook.md) on each commit. Pulled from GitHub via the commits API.
- **`/log` entries on issues** — written explicitly via Billbird's slash command. Pulled from Billbird's `/api/v1/time-entries`.

The tool aggregates both sides per `(repository, author, issue)` group, computes drift in minutes, and classifies the gap. Use it for sprint-end audits, monthly reporting, or the "is everyone logging?" check at any time.

## Install the optional dependency

Reconcile reads Billbird's REST API through the standalone [`billbird-client`](https://github.com/MWest2020/billbird-client) package — an optional dependency:

```bash
uv add 'gitsweeper[billbird]'
# or, while billbird-client is unreleased on PyPI:
uv add 'billbird-client@git+https://github.com/MWest2020/billbird-client.git'
```

Without it, `gitsweeper reconcile` and the `gitsweeper_reconcile` MCP tool exit cleanly with a `billbird_client_unavailable` message.

## Run it

```bash
export GITHUB_TOKEN=$(gh auth token)
export BILLBIRD_API_URL=https://billbird.example.com
export BILLBIRD_API_TOKEN=bb_xxxxxxxxxxxxxx

uv run gitsweeper reconcile MWest2020/Billbird --since 2026-05-01
```

Add `--branch <name>` to read commits from a non-default branch, `--author <login>` to scope, `--json` to get the structured payload instead of a table.

## What a row says

| Column | Meaning |
|---|---|
| `repo` | `owner/name` of the repo being reconciled |
| `author` | GitHub login (or the commit's author name if no login is attached) |
| `issue` | Issue number a commit referenced via `#N` / `Closes #N` etc.; `None` when no reference |
| `commit_minutes` | Sum of `Time:` footers in commits matching this group |
| `log_minutes` | Sum of active `/log` entries in Billbird for this group |
| `drift_minutes` | `log_minutes - commit_minutes` |
| `status` | One of five categories — see below |

## The five categories

| Status | Drift condition | What it usually means |
|---|---|---|
| `aligned` | `|drift| ≤ max(15min, 10% of commit_minutes)` | Both sources agree within a reasonable buffer. No action. |
| `commits_only` | `commit > 0`, `log == 0` | Dev committed with a `Time:` footer but never `/log`-ed on the issue. Most common: forgotten log entry. |
| `logs_only` | `commit == 0`, `log > 0` | `/log` exists but no commit footer references the issue. Possible: work happened off-commit (reviews, discussions, hours not tied to code). |
| `over_committed` | `commit - log > tolerance` | Footers say more time than `/log`s do. Either over-estimated commit or under-logged. |
| `over_logged` | `log - commit > tolerance` | `/log`s say more time than footers do. Either under-estimated commit time or extra work outside the commit graph. |

## What it does not do

- **Does not write back.** Pure read: no commits get rewritten, no `/log`s get created, no Billbird state changes.
- **Does not police anyone.** Drift is information for the team to act on, not a hard error. Tolerances are deliberately generous (the 15-minute floor + 10% rule).
- **Does not solve cross-repo references.** A commit message that says `other/repo#5` is ignored — the tool only matches same-repo `#N`-style references.

## MCP

The same logic is exposed as the `gitsweeper_reconcile` MCP tool — see [docs/mcp.md](mcp.md). Managers can ask Claude Desktop "where are we drifting this sprint?" and the tool returns the same rows the CLI prints.
