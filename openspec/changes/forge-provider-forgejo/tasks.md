## 1. Normalized model + GitHub mapping (pure refactor, no Forgejo yet)

- [ ] 1.1 Add frozen dataclasses to `lib/forge/base.py`: `ForgePullRequest`, `ForgeComment`, `ForgeCommit`, `ForgeRepo` — fields the analyses use (`number`, `state`, `created_at`, `merged_at`, `closed_at`, `author`, …) + `raw: dict`
- [ ] 1.2 Update the `ForgeProvider` protocol return types from `Iterator[dict]` to iterators of the dataclasses
- [ ] 1.3 Map the GitHub provider's JSON onto the dataclasses (raw retained); keep its HTTP/pagination/rate-limit internals unchanged
- [ ] 1.4 Migrate consumers from dict subscription to attribute access: `pr_throughput`, `pr_classification`, `commit_time_reconcile`, `process_report`, and the `cli.py` `--org` repo-listing loop
- [ ] 1.5 Update capability test fakes to yield normalized records; full GitHub suite green with no behavioural change

## 2. Forgejo provider

- [ ] 2.1 `lib/forge/forgejo.py`: a `ForgeProvider` against the Gitea v1 API (`/api/v1`) — list_pull_requests, list_issue_comments, list_issue_events (timeline), list_org_repos, list_commits — mapping onto the normalized model
- [ ] 2.2 Pagination per Forgejo (`page`/`limit`; `Link` header where present, else advance until empty) — **verify the exact scheme against the target instance's swagger**
- [ ] 2.3 Token auth: read the Forgejo token env var, send `Authorization: token <value>`; unauthenticated degraded mode with warn-once
- [ ] 2.4 Generic rate-limit backoff (`429` / `Retry-After`); no GitHub `X-RateLimit-*` assumptions
- [ ] 2.5 `tests/test_forge_forgejo.py`: provider unit tests against a fake httpx transport with canned Gitea-shaped payloads

## 3. Selection registers Forgejo

- [ ] 3.1 Register `forgejo` in `selection.py`: `--forge forgejo`; `codeberg.org` (and a configured self-hosted host) detected from a fully-qualified ref; bare `owner/repo` still GitHub
- [ ] 3.2 Self-hosted base URL from a documented env var (e.g. `GITSWEEPER_FORGEJO_URL`); Codeberg default when unset
- [ ] 3.3 Add `forgejo` to the CLI `--forge` accepted set and its validator
- [ ] 3.4 Extend `tests/test_forge_selection.py`: `--forge forgejo`, codeberg.org detection, self-hosted base URL, unknown forge still rejected by name

## 4. Provider contract suite (the deferred suite)

- [ ] 4.1 `tests/test_forge_contract.py`: parameterised across GitHub and Forgejo via per-forge fake transports
- [ ] 4.2 Assert the invariants: merged ⇒ non-null `merged_at`; closed-without-merge ⇒ null `merged_at` + non-null `closed_at`; `raw` retained; pagination to completion
- [ ] 4.3 Both providers pass; document how a future provider (GitLab) joins by adding a transport fixture

## 5. Docs

- [ ] 5.1 `README.md` "Forges": Forgejo/Codeberg now supported; `--forge forgejo`, the token env var, and the self-hosted base-URL env var
- [ ] 5.2 `openspec/project.md`: provider list now GitHub + Forgejo
- [ ] 5.3 `CHANGELOG.md`: dated `[Unreleased]` entry; note the internal record-type change (normalized model) is not a breaking CLI change

## 6. Verify

- [ ] 6.1 `uv run ruff check .` clean; `uv run pytest` green
- [ ] 6.2 Live smoke against a real **Codeberg** repository: `fetch` + `throughput` (+ `classify`) produce sensible output through the Forgejo provider
- [ ] 6.3 Re-run a GitHub repo end-to-end to confirm no regression from the normalized-model migration
