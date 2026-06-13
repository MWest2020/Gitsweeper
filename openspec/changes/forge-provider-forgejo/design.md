## Context

`forge-abstraction` introduced `ForgeProvider` and `get_forge_provider()`
with GitHub as the only provider, returning GitHub's native JSON dicts. It
explicitly deferred the normalized cross-forge model and the contract-test
suite to "the first non-GitHub provider", because neither can be designed
honestly against a single forge.

This change adds that provider — Forgejo — and so also lands the two deferred
pieces. Forgejo is a hard fork of Gitea; its REST API is the Gitea v1 API
(`/api/v1/...`). Codeberg.org is the reference public instance; self-hosted
Forgejo/Gitea instances expose the same API under their own base URL.

## Goals / Non-Goals

**Goals:**
- A `ForgeProvider` for Forgejo/Gitea/Codeberg good enough to run the
  existing analyses (throughput, first-response, classification, reconcile)
  over a Forgejo repository.
- Introduce the normalized model and migrate both providers and all
  consumers onto it, so analyses are genuinely forge-independent.
- A parameterised contract-test suite both providers pass, encoding the
  normalization invariants.
- Forge selection by `--forge forgejo`, by `codeberg.org` host detection,
  and by a configured self-hosted base URL — with bare `owner/repo` still
  defaulting to GitHub.

**Non-Goals:**
- GitLab (its own follow-on change).
- Forgejo *write* operations — we read only.
- Multiple Forgejo instances in one run. One base URL per invocation,
  matching the single-user model.
- Forgejo Actions / CI data. Out of scope until a DORA capability needs it.
- A plugin/registry mechanism for providers — still a plain in-code registry.

## Decisions

### Forgejo via the Gitea-compatible v1 API; Codeberg as the reference instance

**Choice:** Target the Gitea v1 REST API (`/api/v1`). The read endpoints we
need exist and are compatible: `/repos/{owner}/{repo}/pulls`,
`/repos/{owner}/{repo}/issues/{n}/comments`,
`/repos/{owner}/{repo}/issues/{n}/timeline` (for close actors),
`/repos/{owner}/{repo}/commits`, `/orgs/{org}/repos`. Develop and live-smoke
against a real Codeberg repository.

**Verify at apply** (do not assume): exact field names on the PR object
(`merged`, `merged_at`, `created_at`, `closed_at`, `user.login`), the
timeline/events shape for close-actor detection, and the pagination headers.
Confirm against the target instance's `/api/swagger` rather than from
memory.

### Normalized model as frozen dataclasses, raw retained (realising the deferral)

**Choice:** `lib/forge/base.py` gains frozen dataclasses — `ForgePullRequest`,
`ForgeComment`, `ForgeCommit`, `ForgeRepo` — with the fields the analyses
use and a `raw: dict` holding the provider's original response. Each provider
maps its JSON onto these. Capabilities migrate from dict subscription
(`pull["merged_at"]`) to attribute access (`pull.merged_at`).

**Rationale:** Two concrete forge shapes now exist to reconcile, so the model
is validated, not speculative. Frozen dataclasses are typed and boring; the
retained `raw` keeps the mapping non-lossy and leaves the storage
`raw_payload` column untouched. The consumer migration is mechanical and
fully guarded by the existing capability tests.

**Alternative considered:** normalize to a canonical *dict* shape (so GitHub
consumers barely change). Rejected: weakly typed, and it hides the
cross-forge contract that the dataclasses make explicit. The one-time
dict→attr churn is worth a typed seam the GitLab change can lean on.

### Selection: forge name, host detection, self-hosted base URL

**Choice:** `get_forge_provider` registers `forgejo`. Resolution: explicit
`--forge forgejo` wins; otherwise `codeberg.org` (and a configured
self-hosted host) is detected from a fully-qualified ref; otherwise the
GitHub default for a bare `owner/repo` is unchanged. A self-hosted instance's
base URL comes from an env var (e.g. `GITSWEEPER_FORGEJO_URL`); Codeberg is
the default base when none is set.

**Rationale:** Keeps the behaviour-preserving GitHub default while making
Forgejo reachable both for Codeberg (host-detected) and self-hosted (one env
var). One instance per run matches the single-user CLI.

### Token auth, per provider

**Choice:** Forgejo reads `FORGEJO_TOKEN` and sends Gitea-style
`Authorization: token <value>`. Unauthenticated access is allowed where the
instance permits it (Codeberg public repos), with the same warn-once as
GitHub. No central `FORGE_TOKEN`.

### Pagination and rate limits are per provider

**Choice:** The Forgejo provider follows that API's pagination
(`page`/`limit` with the `Link` header where present, otherwise advancing
`page` until an empty page) and honours generic `429` / `Retry-After`
backoff. It does **not** assume GitHub's `X-RateLimit-*` headers.

**Verify at apply:** whether the target instance returns a `Link` header or
only `X-Total-Count`, and what rate-limit signal (if any) it sends.

### Contract-test suite, parameterised across providers

**Choice:** `tests/test_forge_contract.py` runs the same assertions against
both providers via a fake httpx transport per forge: merged ⇒ non-null
`merged_at`; closed-without-merge ⇒ null `merged_at` + non-null `closed_at`;
`raw` retained; pagination to completion. New providers (GitLab) join by
adding a transport fixture.

## Risks / Trade-offs

- **Self-hosted Forgejo/Gitea version drift.** → Target the documented v1
  API; verify against the instance's swagger; fail with a clear, named error
  on an unexpected shape rather than silently mis-parsing.
- **Wide consumer migration (dict → attribute).** → Mechanical, done in one
  pass; the existing capability tests are the regression guard and must stay
  green with only access-style changes.
- **The normalized model might not fit GitLab later.** → It is now validated
  against two forges via the contract suite, not one; GitLab is a third data
  point in its own change. Keep the model minimal — only fields the analyses
  actually read.
- **Codeberg automated-access etiquette.** → Prefer an authenticated token;
  respect the instance's rate-limit signals; document the token env var.

## Migration Plan

1. Land the dataclasses in `base.py` + map the GitHub provider onto them;
   migrate consumers; keep all GitHub tests green (pure refactor, no Forgejo
   yet).
2. Add `lib/forge/forgejo.py` mapping the Gitea v1 API onto the same model.
3. Register Forgejo in selection (name + host + base-URL env).
4. Land the parameterised contract suite; both providers pass.
5. Docs (README/project.md/CHANGELOG).
6. Live smoke: run `fetch` + `throughput` (+ `classify`) against a real
   Codeberg repository and confirm sensible output; re-run a GitHub repo to
   confirm no regression.

Rollback is a revert: no schema migration, no persisted-state change.

## Open Questions

- **Live-smoke + default target:** Codeberg.org, or a self-hosted Forgejo
  instance Mark runs? This sets the default base URL and the smoke target.
- **Forge aliases:** `forgejo` is canonical. Accept `codeberg` / `gitea` as
  aliases, or keep the surface to `forgejo` + `codeberg.org` host detection
  only? (Recommend the smaller surface.)
