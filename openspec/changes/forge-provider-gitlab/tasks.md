## 1. GitLab provider

- [x] 1.1 `lib/forge/gitlab.py`: a `ForgeProvider` against the GitLab REST API v4 (`/api/v4`), mirroring the Forgejo provider's structure (`from_env`, context manager, paginated `list_*`). Project addressed by URL-encoded `owner%2Frepo`
- [x] 1.2 Map MR → `ForgePullRequest`: `iid` → `number`; `state` `opened` → `open`, `merged`/`closed` → `closed`; `merged_at` non-null iff merged; `author.username` → `author`; retain `raw`
- [x] 1.3 `list_issue_comments` → `/merge_requests/{iid}/notes` → `ForgeComment`; `list_commits` → `/repository/commits` (`id`→sha, `author_name`, `authored_date`) → `ForgeCommit`; `list_org_repos` → `/groups/{group}/projects` → `ForgeRepo`
- [x] 1.4 `list_issue_events` → `/merge_requests/{iid}/resource_state_events`, mapping `state:"closed"` → `ForgeIssueEvent(event="closed", actor=user.username)` — **verify the shape against gitlab.com**; degrade to no-close-actor if the endpoint is absent on old self-hosted GitLab
- [x] 1.5 Token auth: read `GITLAB_TOKEN`, send `PRIVATE-TOKEN: <value>`; unauthenticated degraded mode with warn-once
- [x] 1.6 Pagination: `Link` rel=next where present, else advance `page`/`per_page` until empty; generic `429`/`Retry-After` backoff
- [x] 1.7 `tests/test_forge_gitlab.py`: provider unit tests over a fake httpx transport with real GitLab-shaped payloads (incl. `iid`-as-number, `merged` state, namespaced project-path encoding)

## 2. Selection registers GitLab

- [x] 2.1 Register `gitlab` in `selection.py`: `--forge gitlab`; `gitlab.com` (and a configured self-hosted host) detected; bare `owner/repo` still GitHub
- [x] 2.2 Self-hosted base URL from `GITSWEEPER_GITLAB_URL` (default gitlab.com when unset)
- [x] 2.3 Add `gitlab` to the CLI `--forge` accepted set / validator
- [x] 2.4 Extend `tests/test_forge_selection.py`: `--forge gitlab`, gitlab.com detection, self-hosted base URL, unknown forge still rejected by name

## 3. Contract suite gains GitLab

- [x] 3.1 Add GitLab as a third parameterised provider in `tests/test_forge_contract.py` with a GitLab-shaped fake transport
- [x] 3.2 GitLab passes the same invariants (merge semantics, closed-without-merge, raw retained, pagination to completion, UTC-`Z` timestamps)

## 4. Docs

- [x] 4.1 `README.md` "Forges": GitLab supported; `--forge gitlab`, `GITLAB_TOKEN`, `GITSWEEPER_GITLAB_URL`
- [x] 4.2 `openspec/project.md`: provider list now GitHub + Forgejo + GitLab
- [x] 4.3 `CHANGELOG.md`: dated `[Unreleased]` entry; not a breaking CLI change

## 5. Verify

- [x] 5.1 `uv run ruff check .` clean; `uv run pytest` green
- [x] 5.2 Live smoke against gitlab.com: `fetch --forge gitlab gitlab-org/frontend/eslint-plugin` (a NESTED namespace) ingested 164 MRs and `throughput` rendered real percentiles (139 merged, median 0.71d, p95 47.3d). This surfaced + fixed a CLI gap: `_split_repo` rejected multi-slash refs, so GitLab nested namespaces (`group/sub/project`) were unreachable — relaxed it to split on the first slash only (GitHub/Forgejo single-slash refs unchanged; names there never contain a slash). Note: gitlab.com requires a `GITLAB_TOKEN` for MR sub-resources (notes/state-events), so `first-response`/`classify` need a token; `fetch`/`throughput` work anonymously on public projects.
- [x] 5.3 GitHub (`MWest2020/Gitsweeper`) and Forgejo (`forgejo/meta`) re-fetched end-to-end — no regression
