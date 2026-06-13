## 1. Forge package skeleton

- [ ] 1.1 Create `src/gitsweeper/lib/forge/__init__.py` exporting the public surface (`ForgeProvider`, the normalized dataclasses, `get_forge_provider`)
- [ ] 1.2 Add `lib/forge/base.py`: the `ForgeProvider` `Protocol` (list_pull_requests, list_issue_comments, list_commits, list_org_repos) and frozen dataclasses `ForgePullRequest`, `ForgeComment`, `ForgeCommit`, `ForgeRepo` (each with a `raw: dict` field)
- [ ] 1.3 Write `tests/test_forge_contract.py`: a provider-agnostic contract suite asserting uniform merge semantics (merged → non-null `merged_at`; closed-without-merge → null `merged_at`, non-null `closed_at`), raw-payload retention, and pagination-to-completion. Parameterise so future providers run the same suite

## 2. Re-home the GitHub client behind the protocol

- [ ] 2.1 Move `lib/github_client.py` → `lib/forge/github.py`; keep pagination, primary/secondary rate-limit, `GITHUB_TOKEN` auth, and unauth-warn-once logic byte-identical
- [ ] 2.2 Add a thin normalization layer in `github.py` mapping GitHub JSON → the `Forge*` dataclasses (raw dict retained), exposing the `ForgeProvider` operations
- [ ] 2.3 Rename `tests/test_github_client.py` → `tests/test_forge_github.py`; keep every existing assertion, adjust imports only
- [ ] 2.4 Run `tests/test_forge_github.py` and `tests/test_forge_contract.py` green for the GitHub provider

## 3. Forge selection

- [ ] 3.1 Add `lib/forge/selection.py`: `get_forge_provider(repo_ref, *, forge=None)` resolving explicit `--forge` → host detection → GitHub default for bare `owner/repo`
- [ ] 3.2 Per-provider token lookup: each provider declares its env var; GitHub reads `GITHUB_TOKEN` exactly as before (no central `FORGE_TOKEN`)
- [ ] 3.3 Unsupported/unknown forge raises a named error listing available providers; never silently falls back to GitHub
- [ ] 3.4 `tests/test_forge_selection.py`: bare ref → github, `--forge github` override, unknown forge → named error

## 4. Wire capabilities through the seam

- [ ] 4.1 Replace `GitHubClient(...)` / `GitHubClient.from_env()` construction in every capability call site with `get_forge_provider(ref, forge=...)` — mechanical, no logic change
- [ ] 4.2 Add a global `--forge {github}` CLI option (only `github` accepted this change) plus host auto-detection; default and behaviour unchanged for current invocations
- [ ] 4.3 Confirm `pr-throughput-analysis`, `commit-time-reconcile`, and any other consumers now acquire via `forge-access`; their analysis logic is untouched
- [ ] 4.4 Existing capability tests stay green with import/construction edits only — no behavioural test changes

## 5. Remove the old client

- [ ] 5.1 Delete `src/gitsweeper/lib/github_client.py` (content now lives under `lib/forge/`)
- [ ] 5.2 Grep the tree for `github_client` / `GitHubClient` imports; ensure none remain outside `lib/forge/`

## 6. Docs, project.md, changelog

- [ ] 6.1 `openspec/project.md`: lift the "Non-GitHub data sources" v1 non-goal; update the scale-of-ambition note and the layout reference (`github_client/` → `forge/`)
- [ ] 6.2 `README.md`: short "Forges" note — GitHub today, Forgejo/Codeberg + GitLab on the roadmap; document `--forge`
- [ ] 6.3 `CHANGELOG.md`: dated `[Unreleased]` entry — forge-provider seam added, GitHub re-homed, no behaviour change, not breaking

## 7. Verify

- [ ] 7.1 `uv run pytest`: all green
- [ ] 7.2 `uv run ruff check .`: clean
- [ ] 7.3 Live smoke: run one existing GitHub analysis end-to-end against a real repo and confirm output is identical to pre-change
