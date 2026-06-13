## 1. GitLab provider

- [ ] 1.1 `lib/forge/gitlab.py`: a `ForgeProvider` against the GitLab REST API v4 (`/api/v4`), mirroring the Forgejo provider's structure (`from_env`, context manager, paginated `list_*`). Project addressed by URL-encoded `owner%2Frepo`
- [ ] 1.2 Map MR → `ForgePullRequest`: `iid` → `number`; `state` `opened` → `open`, `merged`/`closed` → `closed`; `merged_at` non-null iff merged; `author.username` → `author`; retain `raw`
- [ ] 1.3 `list_issue_comments` → `/merge_requests/{iid}/notes` → `ForgeComment`; `list_commits` → `/repository/commits` (`id`→sha, `author_name`, `authored_date`) → `ForgeCommit`; `list_org_repos` → `/groups/{group}/projects` → `ForgeRepo`
- [ ] 1.4 `list_issue_events` → `/merge_requests/{iid}/resource_state_events`, mapping `state:"closed"` → `ForgeIssueEvent(event="closed", actor=user.username)` — **verify the shape against gitlab.com**; degrade to no-close-actor if the endpoint is absent on old self-hosted GitLab
- [ ] 1.5 Token auth: read `GITLAB_TOKEN`, send `PRIVATE-TOKEN: <value>`; unauthenticated degraded mode with warn-once
- [ ] 1.6 Pagination: `Link` rel=next where present, else advance `page`/`per_page` until empty; generic `429`/`Retry-After` backoff
- [ ] 1.7 `tests/test_forge_gitlab.py`: provider unit tests over a fake httpx transport with real GitLab-shaped payloads (incl. `iid`-as-number, `merged` state, namespaced project-path encoding)

## 2. Selection registers GitLab

- [ ] 2.1 Register `gitlab` in `selection.py`: `--forge gitlab`; `gitlab.com` (and a configured self-hosted host) detected; bare `owner/repo` still GitHub
- [ ] 2.2 Self-hosted base URL from `GITSWEEPER_GITLAB_URL` (default gitlab.com when unset)
- [ ] 2.3 Add `gitlab` to the CLI `--forge` accepted set / validator
- [ ] 2.4 Extend `tests/test_forge_selection.py`: `--forge gitlab`, gitlab.com detection, self-hosted base URL, unknown forge still rejected by name

## 3. Contract suite gains GitLab

- [ ] 3.1 Add GitLab as a third parameterised provider in `tests/test_forge_contract.py` with a GitLab-shaped fake transport
- [ ] 3.2 GitLab passes the same invariants (merge semantics, closed-without-merge, raw retained, pagination to completion, UTC-`Z` timestamps)

## 4. Docs

- [ ] 4.1 `README.md` "Forges": GitLab supported; `--forge gitlab`, `GITLAB_TOKEN`, `GITSWEEPER_GITLAB_URL`
- [ ] 4.2 `openspec/project.md`: provider list now GitHub + Forgejo + GitLab
- [ ] 4.3 `CHANGELOG.md`: dated `[Unreleased]` entry; not a breaking CLI change

## 5. Verify

- [ ] 5.1 `uv run ruff check .` clean; `uv run pytest` green
- [ ] 5.2 Live smoke against a small **public gitlab.com** project: `fetch --forge gitlab <project>` + `throughput` produce sensible output
- [ ] 5.3 Re-run a GitHub and a Forgejo repo end-to-end to confirm no regression
