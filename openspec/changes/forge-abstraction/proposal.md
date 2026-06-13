## Why

Gitsweeper's data acquisition is hardcoded to GitHub: `lib/github_client.py`, GitHub-only auth (`GITHUB_TOKEN`), GitHub Link-header pagination, and GitHub rate-limit handling — with the acquisition requirements themselves living inside `pr-throughput-analysis`. `project.md` lists non-GitHub sources as explicitly out of scope for v1.

That ceiling is now the thing worth lifting. The strategic arc is a **forge-agnostic delivery-analytics tool** — the same engine running against GitHub, Forgejo/Codeberg (self-hosted, sovereignty), and GitLab — that absorbs the DORA / retro-signal / scheduled-Slack logic currently stranded in the `Road_to_el_DORA-do` Actions prototype. Every existing tool (GitHub-only metrics) is single-forge; the unoccupied corner is the same DORA picture across forges including self-hosted ones.

This change is the **keystone**: the seam that everything else hangs off. It introduces the forge-provider abstraction and re-homes the existing GitHub client behind it **with zero behaviour change for current GitHub users**. Concrete Forgejo and GitLab providers, and the DORA/retro/delivery capabilities, are deliberately separate follow-on changes (see *Roadmap* below) so the seam is proven before anything is built on it.

## What Changes

- **New shared concern `forge-access`** owning everything about *talking to a forge*: a `ForgeProvider` protocol (list pull/merge requests, comments, commits, org/group repositories), per-provider authentication, per-provider pagination, per-provider rate-limit handling, a normalized cross-forge data model, and forge **selection** (auto-detect from the host of an `owner/repo` ref or URL, overridable with `--forge`).
- **GitHub re-homed, not rewritten.** `lib/github_client.py` moves to `lib/forge/github.py` and implements `ForgeProvider`. Its behaviour — Link-header pagination, primary/secondary rate-limit handling, `GITHUB_TOKEN` auth, unauthenticated degraded mode — is preserved verbatim and remains the **default** provider, so an unqualified `owner/repo` resolves to GitHub exactly as today.
- **Acquisition requirements relocate** out of `pr-throughput-analysis` and `commit-time-reconcile` into `forge-access`, generalised from "GitHub" to "the selected forge provider". The analysis capabilities keep their analysis requirements and now acquire data *through* `forge-access`.
- **No new forge ships in this change.** GitHub is the only concrete provider here. The `forge-access` spec defines the contract a provider must meet so Forgejo and GitLab slot in as follow-on changes without re-opening the seam.
- Token configuration generalises: `GITHUB_TOKEN` keeps working; the provider layer reads a per-forge token (the Forgejo/GitLab env vars arrive with their providers).

## Capabilities

### New Capabilities
- `forge-access`: the forge-provider abstraction — provider interface, forge selection/detection, per-provider auth, pagination, rate-limit handling, and the normalized PR/MR + commit + repo-listing model that analysis capabilities consume. Cross-cutting in the same sense as `report-rendering`: every analysis acquires from a forge.

### Modified Capabilities
- `pr-throughput-analysis`: its data-acquisition requirements (fetch all PRs, multi-repo fetch, `--org` expansion, pagination, rate limits, `GITHUB_TOKEN` auth, unauthenticated degraded mode) move to `forge-access`; the capability now acquires PRs *through* `forge-access` and keeps all analysis requirements (percentiles, `--since`, `--author`, temporal patterns, first-response, rendering) unchanged.
- `commit-time-reconcile`: its "fetch commits from a repo" requirement moves to `forge-access`, generalised across forges; reconcile keeps its footer-extraction and Billbird-matching logic and now obtains commits through `forge-access`.

## Impact

- **Code (Python)**: new `lib/forge/` package — `base.py` (the `ForgeProvider` protocol + normalized dataclasses), `github.py` (the re-homed client implementing the protocol), `selection.py` (host detection + `--forge` resolution + per-forge token lookup). `lib/github_client.py` is removed; its content moves under `lib/forge/`. Call sites in `capabilities/` switch from `GitHubClient(...)` / `GitHubClient.from_env()` to a `get_forge_provider(repo_ref, forge=...)` factory. Mechanical, behaviour-preserving.
- **Tests**: `tests/test_github_client.py` becomes `tests/test_forge_github.py` (same assertions, new import path); a new `tests/test_forge_selection.py` covers host-detection and the default-to-GitHub rule; a new `tests/test_forge_contract.py` defines provider-contract tests the GitHub provider passes today and future providers must pass. Existing capability tests adjust their import/construction only.
- **CLI**: a global `--forge {github}` option (only `github` accepted in this change) plus host auto-detection. Default and behaviour unchanged for every current invocation.
- **`project.md`**: the "Non-GitHub data sources" non-goal is lifted; the scale-of-ambition note updates to name the forge-provider seam. The `github-client` library reference in the layout becomes `forge/`.
- **Docs / CHANGELOG**: `README.md` gains a short "forges" note (GitHub today, Forgejo/GitLab on the roadmap); `CHANGELOG.md` gets a dated `[Unreleased]` entry. Not a breaking change — every existing GitHub command keeps working with no new flags required.

## Roadmap (follow-on changes, not this change)

1. `forge-provider-forgejo` — Codeberg / Gitea / self-hosted Forgejo provider (sovereignty USP; ties to the `wanderer` NL-soevereiniteit thema).
2. `forge-provider-gitlab` — GitLab provider, incl. merge-request merge semantics and group (vs org) expansion.
3. `dora-metrics` — lead time, deployment frequency, change-fail rate, recovery, rework as a capability (the core USP from `Road_to_el_DORA-do`), team-level only.
4. `retro-signals` — sprint-spillover, long threads, friction-language, tech-debt markers; deterministic keyword lists, no LLM black-box; "speel op de bal, niet op de mens" (no per-person metrics) as a spec-level constraint.
5. `scheduled-delivery` — scheduled run → Slack Block Kit delivery + artifact, superseding the `Road_to_el_DORA-do` Actions workflow.
