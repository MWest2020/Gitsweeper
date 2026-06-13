## Scope note (recorded during apply)

This keystone ships the **provider seam only**, behaviour-preserving, with
GitHub as the single provider. Two pieces the original task list named are
**deferred to the first non-GitHub provider** (`forge-provider-forgejo`),
because you cannot validate them against one forge and building them now
would be speculative — against the "no abstraction without a second concrete
use case" principle:

- the **normalized cross-forge dataclasses** — the `ForgeProvider` protocol
  returns GitHub's native dict shape that the capabilities already consume;
- the **parameterised provider contract-test suite** — meaningful only with
  two implementations to run it against.

The `forge-access` spec still describes both as the eventual contract; they
land when the second forge does.

## 1. Forge package skeleton

- [x] 1.1 `lib/forge/__init__.py` exporting `ForgeProvider`, `get_forge_provider`, `GitHubClient`, `GitHubError`, `UnsupportedForgeError`, `SUPPORTED_FORGES`
- [x] 1.2 `lib/forge/base.py`: the `ForgeProvider` `Protocol` (list_pull_requests, list_issue_comments, list_issue_events, list_org_repos, list_commits, + context manager). Normalized dataclasses **deferred** (see scope note)
- [~] 1.3 Provider contract-test suite — **deferred** to the first non-GitHub provider (see scope note)

## 2. Re-home the GitHub client behind the protocol

- [x] 2.1 `git mv lib/github_client.py lib/forge/github.py` — pagination, rate-limit, `GITHUB_TOKEN` auth, unauth-warn-once preserved byte-identical
- [x] 2.2 GitHub provider satisfies `ForgeProvider` structurally (returns its native dicts; normalization deferred)
- [x] 2.3 `git mv tests/test_github_client.py tests/test_forge_github.py`; imports updated, every assertion kept
- [x] 2.4 `test_forge_github.py` green for the GitHub provider

## 3. Forge selection

- [x] 3.1 `lib/forge/selection.py`: `get_forge_provider(repo_ref, *, forge=None)` — explicit `--forge` → host detection → GitHub default for bare `owner/repo`
- [x] 3.2 GitHub reads `GITHUB_TOKEN` exactly as before; no central `FORGE_TOKEN`
- [x] 3.3 Unsupported forge raises `UnsupportedForgeError` naming available providers; CLI surfaces it as a `typer.BadParameter`
- [x] 3.4 `tests/test_forge_selection.py`: bare ref → github, `--forge github` override, github.com URL detected, unknown forge → named error

## 4. Wire capabilities through the seam

- [x] 4.1 `cli.py`, `pr_throughput.py`, `commit_time_reconcile.py`, `manager_mcp/tools.py` switched from `GitHubClient.from_env()` to `get_forge_provider(...)`; `pr_classification`/`process_report` were already protocol-typed (`_IssueEventClient`/`ReportClient`) so unchanged
- [x] 4.2 Global `--forge {github}` CLI option on `fetch`, `first-response`, `classify`, `report` with a validating callback; default unchanged
- [x] 4.3 Consumers acquire via `forge-access`; analysis logic untouched
- [x] 4.4 Existing capability tests green with import/construction edits only

## 5. Remove the old client

- [x] 5.1 `lib/github_client.py` removed (moved under `lib/forge/`)
- [x] 5.2 Tree grep: no `github_client` / `GitHubClient` imports remain outside `lib/forge/`

## 6. Docs, project.md, changelog

- [x] 6.1 `project.md`: non-GitHub non-goal lifted to "concrete non-GitHub providers"; layout `github_client/` → `forge/`; scale-of-ambition note
- [x] 6.2 `README.md`: "Forges" note — GitHub today, `--forge`, Forgejo/GitLab roadmap
- [x] 6.3 `CHANGELOG.md`: dated `[Unreleased]` Added entry; not breaking

## 7. Verify

- [x] 7.1 `uv run pytest`: 156 passed
- [x] 7.2 `uv run ruff check .`: clean
- [x] 7.3 Live smoke: real GitHub fetch+throughput via the seam — `MWest2020/Gitsweeper` fetched 4 PRs and rendered; `--forge gitlab` rejected with a named error
