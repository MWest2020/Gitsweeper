## Why

GitLab is the third forge and the most divergent from GitHub's vocabulary,
which makes it the real stress test of the normalized model that
`forge-provider-forgejo` introduced. Forgejo's Gitea API is GitHub-shaped;
GitLab is not — it has Merge Requests with per-project `iid` numbers, a
three-value state (`opened`/`closed`/`merged`), `PRIVATE-TOKEN` auth, and
groups instead of orgs. If the same analyses run unchanged over GitLab too,
the forge-agnostic engine is proven across the three forges that matter,
and the DORA capabilities that follow can target any of them.

## What Changes

- **New `lib/forge/gitlab.py`** — a `ForgeProvider` against the GitLab REST
  API v4 (`/api/v4`): merge requests, their notes, state events (for close
  actors), commits, and group projects, mapped onto the existing normalized
  model.
- **Normalization absorbs GitLab's vocabulary** in the mapping layer (no new
  model fields): `iid` → `number`; `state` `opened` → `open` and
  `merged`/`closed` → `closed` (with `merged_at` non-null iff the MR merged);
  `author.username` → `author`; commit `author_name`/`authored_date` →
  the commit fields. The `raw` payload retains GitLab's original object.
- **Selection learns GitLab:** `--forge gitlab` selects it; `gitlab.com` and
  a configured self-hosted host are detected; self-hosted base URL comes from
  an env var. Bare `owner/repo` still defaults to GitHub.
- **Token config:** `GITLAB_TOKEN` sent as the `PRIVATE-TOKEN` header
  (GitLab's PAT convention), per-provider as established.
- **The contract suite gains GitLab** as a third parameterised provider; it
  passes the same invariants as GitHub and Forgejo.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `forge-access`: the selection and authentication requirements gain GitLab
  scenarios; the normalize requirement gains a scenario for GitLab's distinct
  merge-state vocabulary (`opened`/`merged`/`closed` → `open`/`closed` +
  `merged_at`) and `iid`-as-number. The provider-interface and pagination /
  rate-limit requirements are already provider-generic and need no change.

## Impact

- **Code (Python):** new `lib/forge/gitlab.py` (mirrors the Forgejo provider
  structure — `from_env`, context manager, paginated `list_*`); a thin
  GitLab→model mapping; `selection.py` registers `gitlab` (host detection +
  `--forge gitlab` + `GITSWEEPER_GITLAB_URL`); `cli.py` `--forge` accepts
  `gitlab`. No capability or storage change — they already consume the
  normalized dataclasses.
- **Tests:** `tests/test_forge_gitlab.py` (provider unit tests over a fake
  httpx transport with real GitLab-shaped payloads); `test_forge_contract.py`
  adds GitLab as a third parameterised provider; `test_forge_selection.py`
  gains GitLab cases.
- **CLI:** `--forge gitlab` + the self-hosted base-URL env. GitHub default
  and behaviour unchanged.
- **Config:** `GITLAB_TOKEN` (sent as `PRIVATE-TOKEN`) and
  `GITSWEEPER_GITLAB_URL` documented.
- **Docs / CHANGELOG:** README "Forges" note (GitLab supported);
  `project.md` provider list; dated CHANGELOG entry. Not a breaking change.

## Follow-on (not this change)

- `dora-metrics`, `retro-signals`, `scheduled-delivery` — the DORA/retro/Slack
  capabilities absorbed from `Road_to_el_DORA-do`, now able to run over any of
  the three supported forges.
