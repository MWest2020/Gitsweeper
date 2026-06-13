## Context

Gitsweeper acquires data through a single concrete client,
`lib/github_client.py`: a synchronous `httpx` wrapper around the
GitHub REST API that handles Link-header pagination, primary and
secondary rate limits, and `GITHUB_TOKEN` auth. The acquisition
*requirements* live inside `pr-throughput-analysis` and
`commit-time-reconcile`, and every capability constructs
`GitHubClient` directly. `project.md` names non-GitHub sources an
explicit v1 non-goal.

The strategic goal is a forge-agnostic delivery-analytics tool — the
same engine over GitHub, Forgejo/Codeberg, and GitLab — that will
absorb the DORA / retro-signal / scheduled-Slack logic currently
prototyped as a GitHub Actions workflow in `Road_to_el_DORA-do`. That
goal needs a forge seam. This change builds only the seam and proves
it by moving the existing GitHub client behind it with no behaviour
change. Concrete non-GitHub providers and the DORA capabilities are
separate follow-on changes.

## Goals / Non-Goals

**Goals:**
- Introduce a `ForgeProvider` interface and a normalized data model
  that analysis capabilities consume instead of `GitHubClient`.
- Re-home the existing GitHub client behind the interface with its
  behaviour preserved verbatim — same pagination, rate-limit, and
  auth semantics, same default for bare `owner/repo`.
- Relocate the acquisition requirements into a `forge-access`
  capability so the abstraction owns its own spec.
- Add forge selection (`--forge` + host detection) that is a no-op
  for every current GitHub invocation.
- Define the provider *contract* (a shared test suite) so Forgejo and
  GitLab can be added later without re-opening the seam.

**Non-Goals:**
- Implementing any non-GitHub provider. GitHub is the only concrete
  provider in this change.
- DORA metrics, retro signals, scheduled runs, Slack delivery — all
  follow-on capabilities.
- Async / concurrent fetching. The sync model stays; revisit only if
  a real provider needs it.
- Changing the storage schema. Normalized records map onto the
  existing `repositories` / `pull_requests` tables; the
  `raw_payload TEXT` column already preserves the forge's raw
  response.
- A registry/plugin-discovery mechanism. Providers are registered in
  code; a bare `dict` of `{forge_name: provider_factory}` is enough
  until there is a third-party provider.

## Decisions

### A `Protocol`, not an ABC, for `ForgeProvider`

**Choice:** Define `ForgeProvider` as a `typing.Protocol` in
`lib/forge/base.py`, with the GitHub provider as a plain class that
structurally satisfies it.

**Rationale:** Boring and auditable — no inheritance ceremony, no
base-class import coupling, and the contract test suite
(`test_forge_contract.py`) is what actually enforces conformance, not
the type system. A `Protocol` keeps providers independent of each
other.

**Alternatives considered:** An `abc.ABC` base class — more familiar
to some, but forces an import dependency from every provider onto the
base and tempts shared implementation in the base class, which is
exactly the coupling the seam exists to avoid.

### Normalized model — deferred to the first non-GitHub provider

**Choice:** The `ForgeProvider` protocol returns GitHub's native JSON
dict shape (an `Iterator[dict]`), which the capabilities already
consume. The normalized cross-forge model — frozen dataclasses
(`ForgePullRequest`, `ForgeComment`, `ForgeCommit`, `ForgeRepo`) with
the fields the analyses use (`number`, `state`, `created_at`,
`merged_at`, `closed_at`, `author`, `raw`) and uniform merge
semantics — is **not** built in this change. It lands with the
`forge-provider-forgejo` change.

**Rationale:** A normalization layer exists to reconcile *differing*
forge shapes. With one forge there is nothing to reconcile, so
building the dataclasses now would be speculative — exactly the
"no abstraction without a second concrete use case" trap. Returning
the existing dict shape also keeps this change behaviour-preserving:
no capability's field access changes. When Forgejo arrives, its
genuinely different shape forces the model to be designed against two
realities, and the storage layer's existing `raw_payload` column is
ready to hold the retained raw response.

**Alternatives considered:** Build the dataclasses now and adapt
GitHub to them — speculative, and a wide behaviour-touching diff
across every capability's field access for zero present benefit.
When the model does land: frozen dataclasses over `pydantic`
(no new runtime dependency for data we already trust) or `polars`
rows (premature at this layer).

### Provider selection: explicit override, else host, else GitHub

**Choice:** `get_forge_provider(repo_ref, *, forge=None)` resolves in
order: explicit `forge` argument (from `--forge`) → host parsed from
a fully-qualified `repo_ref` → GitHub default for a bare
`owner/repo`. Unknown forge → a named error listing available
providers.

**Rationale:** The default-to-GitHub rule is what makes this change
behaviour-preserving: every existing bare-`owner/repo` invocation
resolves exactly as before. Failing loudly on an unsupported forge
(rather than guessing) matches gitsweeper's fail-loud-and-named
convention.

**Alternatives considered:** Always require `--forge` — needless
friction for the 100%-GitHub present and a breaking change. Infer
purely from host — breaks bare `owner/repo`, which is the common
case.

### Token lookup is per-provider, GITHUB_TOKEN unchanged

**Choice:** Each provider declares the env var it reads. GitHub keeps
`GITHUB_TOKEN`. The selection layer asks the resolved provider for
its token; it does not centralise a single `FORGE_TOKEN`.

**Rationale:** A single shared token var would be wrong the moment a
user analyses two forges at once. Per-provider vars are explicit and
auditable, and leave `GITHUB_TOKEN` working untouched.

### The GitHub client moves, it is not rewritten

**Choice:** `lib/github_client.py` → `lib/forge/github.py`, wrapped to
satisfy `ForgeProvider` and to emit normalized records. Its
pagination, rate-limit, and auth internals are copied verbatim.

**Rationale:** The riskiest part of any abstraction is regressing the
one implementation that works. Moving rather than rewriting, and
keeping `test_forge_github.py` as a renamed copy of
`test_github_client.py`, makes the diff reviewable as "same
behaviour, new home".

## Risks / Trade-offs

- **Risk: a wide, mechanical call-site diff across capabilities reads
  as risky.** → Keep the data-acquisition logic byte-identical; the
  only change at call sites is `GitHubClient(...)` →
  `get_forge_provider(ref, forge=...)`. The existing capability tests
  are the regression guard; they must stay green with only
  import/construction edits.
- **Risk: the normalized model is shaped to GitHub and won't fit
  GitLab/Forgejo.** → The contract test suite encodes the model's
  intent (esp. uniform merge semantics) so the GitLab/Forgejo
  follow-ons surface mismatches as failing contract tests, not as
  silent divergence. The model deliberately stays minimal — only
  fields the analyses use today.
- **Risk: scope creep into "just add GitLab while we're here".** →
  Explicitly out of scope; the spec defines the contract but ships
  only GitHub. GitLab/Forgejo are named follow-on changes.

## Migration Plan

1. Land `lib/forge/` (base + github + selection) with the contract
   test suite; GitHub provider passes it.
2. Switch capability call sites to `get_forge_provider`; run the full
   `pytest` + `ruff` suite — must be green with no behavioural test
   changes.
3. Remove `lib/github_client.py`; rename its test module.
4. Update `project.md` (lift the non-GitHub non-goal; rename the
   library reference), `README.md`, and `CHANGELOG.md`.
5. Live smoke: run an existing GitHub analysis end-to-end against a
   real repo and confirm identical output to pre-change.

Rollback is a single revert: no schema migration, no data change, no
new persisted state.

## Open Questions

- **Identity of the merged tool.** As the engine stops being
  GitHub-specific, "Gitsweeper" (a Minesweeper pun on *git*) may stop
  fitting. Not blocking — the repo and package name stay this change;
  flagged as a product decision for when the DORA capabilities land.
- **First concrete forge after the seam.** Recommendation: Forgejo /
  Codeberg first (self-hosted sovereignty, aligns with the `wanderer`
  thema), GitLab second. To be confirmed when scheduling the
  follow-on changes.
