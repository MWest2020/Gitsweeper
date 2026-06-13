## Why

The `forge-abstraction` keystone built the provider seam but shipped only
GitHub, and deliberately deferred two things until a second forge existed:
the normalized cross-forge model and the provider contract-test suite. This
change is that second forge.

Forgejo (and its upstream Gitea; Codeberg is the reference public instance)
is the highest-value next provider: self-hosted, EU-sovereign, and aligned
with the `wanderer` NL-soevereiniteit thema. It is also the moment the
abstraction stops being speculative — with GitHub and Forgejo side by side
there are two concrete record shapes to reconcile, so the normalized model
can be designed and validated against reality rather than guessed.

## What Changes

- **New `lib/forge/forgejo.py`** — a `ForgeProvider` implementation against
  the Forgejo/Gitea REST API v1: pull requests, comments, issue events (for
  close-actor classification), commits, and org repositories, with its own
  pagination and rate-limit handling and token auth.
- **The deferred normalized model lands.** `lib/forge/base.py` gains frozen
  dataclasses (`ForgePullRequest`, `ForgeComment`, `ForgeCommit`,
  `ForgeRepo`) carrying the fields the analyses use (`number`, `state`,
  `created_at`, `merged_at`, `closed_at`, `author`) plus the provider's raw
  response in `raw`. Both providers map their forge's JSON onto it, so merge
  state and timestamps are uniform regardless of source forge.
- **Capabilities consume normalized records** instead of GitHub dicts — a
  mechanical field-access migration (`pull["merged_at"]` → `pull.merged_at`)
  guarded by the existing capability tests.
- **The deferred contract-test suite lands.** `tests/test_forge_contract.py`
  is parameterised across both providers and asserts the normalization
  invariants (merged ⇒ non-null `merged_at`; closed-without-merge ⇒ null
  `merged_at` + non-null `closed_at`; raw retained; pagination to
  completion).
- **Selection learns Forgejo.** `--forge forgejo` selects it; `codeberg.org`
  and a configured self-hosted host are detected; self-hosted base URL comes
  from an env var. Bare `owner/repo` still defaults to GitHub.
- **Token config:** a Forgejo token env var (Gitea-style `token` auth),
  per-provider as established — no central token.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `forge-access`: the provider-interface requirement is strengthened to
  return the normalized model (no longer "native shape"); a
  "Normalize each forge's model to a common shape" requirement is added
  (the one deferred from `forge-abstraction`); the selection and
  authentication requirements gain Forgejo scenarios. The pagination and
  rate-limit requirements already read "each provider's own" and need no
  change; Forgejo's concrete behaviour is covered by its provider tests and
  the contract suite.

## Impact

- **Code (Python):** new `lib/forge/forgejo.py`; new dataclasses in
  `lib/forge/base.py`; `lib/forge/github.py` gains a thin mapping from
  GitHub JSON → the dataclasses; `lib/forge/selection.py` registers Forgejo
  (host detection + `--forge forgejo` + self-hosted base URL). Capability
  call sites switch from dict subscription to attribute access — mechanical,
  no logic change.
- **Tests:** `tests/test_forge_forgejo.py` (provider unit tests against a
  fake httpx transport); `tests/test_forge_contract.py` (parameterised
  contract suite both providers pass); `test_forge_github.py` adjusts to the
  dataclass return; capability tests adjust their fake clients to yield
  normalized records.
- **CLI:** `--forge` accepts `forgejo`; a self-hosted base-URL option/env.
  GitHub default and behaviour unchanged.
- **Config:** a documented Forgejo token env var and base-URL env var.
- **Docs / CHANGELOG:** README "Forges" note updated (Forgejo/Codeberg now
  supported); `project.md` provider list; dated CHANGELOG entry. Not a
  breaking change for GitHub users (their commands are unchanged; only the
  internal record type changed).
- **Storage:** unchanged — the `raw_payload` column already holds the
  retained raw response; the normalized fields map onto the existing
  columns.

## Follow-on (not this change)

- `forge-provider-gitlab` — GitLab provider (merge-request merge semantics,
  group vs org expansion).
- `dora-metrics`, `retro-signals`, `scheduled-delivery` — the DORA/retro/Slack
  capabilities absorbed from `Road_to_el_DORA-do`, now able to run over any
  supported forge.
