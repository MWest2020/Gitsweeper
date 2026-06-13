## 1. Normalized model + GitHub mapping (pure refactor, no Forgejo yet)

- [x] 1.1 Add frozen dataclasses to `lib/forge/base.py`: `ForgePullRequest`, `ForgeComment`, `ForgeCommit`, `ForgeRepo` — fields the analyses use (`number`, `state`, `created_at`, `merged_at`, `closed_at`, `author`, …) + `raw: dict`
- [x] 1.2 Update the `ForgeProvider` protocol return types from `Iterator[dict]` to iterators of the dataclasses
- [x] 1.3 Map the GitHub provider's JSON onto the dataclasses (raw retained); keep its HTTP/pagination/rate-limit internals unchanged
- [x] 1.4 Migrate consumers from dict subscription to attribute access: `pr_throughput`, `pr_classification`, `commit_time_reconcile`, `process_report`, and the `cli.py` `--org` repo-listing loop
- [x] 1.5 Update capability test fakes to yield normalized records; full GitHub suite green with no behavioural change

## 2. Forgejo provider

- [x] 2.1 `lib/forge/forgejo.py`: a `ForgeProvider` against the Gitea v1 API (`/api/v1`) — list_pull_requests, list_issue_comments, list_issue_events (timeline), list_org_repos, list_commits — mapping onto the normalized model
- [x] 2.2 Pagination per Forgejo (`page`/`limit`; `Link` header where present, else advance until empty) — **verify the exact scheme against the target instance's swagger**
- [x] 2.3 Token auth: read the Forgejo token env var, send `Authorization: token <value>`; unauthenticated degraded mode with warn-once
- [x] 2.4 Generic rate-limit backoff (`429` / `Retry-After`); no GitHub `X-RateLimit-*` assumptions
- [x] 2.5 `tests/test_forge_forgejo.py`: provider unit tests against a fake httpx transport with canned Gitea-shaped payloads

## 3. Selection registers Forgejo

- [x] 3.1 Register `forgejo` in `selection.py`: `--forge forgejo`; `codeberg.org` (and a configured self-hosted host) detected from a fully-qualified ref; bare `owner/repo` still GitHub
- [x] 3.2 Self-hosted base URL from a documented env var (e.g. `GITSWEEPER_FORGEJO_URL`); Codeberg default when unset
- [x] 3.3 Add `forgejo` to the CLI `--forge` accepted set and its validator
- [x] 3.4 Extend `tests/test_forge_selection.py`: `--forge forgejo`, codeberg.org detection, self-hosted base URL, unknown forge still rejected by name

## 4. Provider contract suite (the deferred suite)

- [x] 4.1 `tests/test_forge_contract.py`: parameterised across GitHub and Forgejo via per-forge fake transports
- [x] 4.2 Assert the invariants: merged ⇒ non-null `merged_at`; closed-without-merge ⇒ null `merged_at` + non-null `closed_at`; `raw` retained; pagination to completion
- [x] 4.3 Both providers pass; document how a future provider (GitLab) joins by adding a transport fixture

## 5. Docs

- [x] 5.1 `README.md` "Forges": Forgejo/Codeberg now supported; `--forge forgejo`, the token env var, and the self-hosted base-URL env var
- [x] 5.2 `openspec/project.md`: provider list now GitHub + Forgejo
- [x] 5.3 `CHANGELOG.md`: dated `[Unreleased]` entry; note the internal record-type change (normalized model) is not a breaking CLI change

## 6. Verify

- [x] 6.1 `uv run ruff check .` clean; `uv run pytest` green
- [x] 6.2 Live smoke against a real **Codeberg** repository: `gitsweeper fetch --forge forgejo forgejo/meta` ingested 39 PRs and `throughput` rendered real percentiles (34 merged, median 0.17d, p95 25.6d). Fixed two issues this surfaced: dropped the `sort=oldest` PR param (Gitea 504s on the full ordered scan at slow instances; order is irrelevant to the analyses) and raised the Forgejo read timeout to 60s (Codeberg is slower per request than GitHub)
- [x] 6.3 Re-run a GitHub repo end-to-end to confirm no regression from the normalized-model migration
