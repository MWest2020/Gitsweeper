## Context

`forge-abstraction` built the seam; `forge-provider-forgejo` added the second
provider and the normalized model (frozen dataclasses, UTC-`Z` timestamps,
retained raw, a parameterised contract suite). Forgejo's Gitea API is
GitHub-shaped, so normalization barely stretched. GitLab is the divergent
case the model now has to absorb without new fields.

GitLab exposes a REST API v4 (`/api/v4`). A project is addressed by its
URL-encoded `namespace/project` path (`owner%2Frepo`) or numeric id. The
captured real shapes (gitlab.com): MR has `iid` (per-project number), `id`
(global — ignore), `state` ∈ {`opened`, `closed`, `merged`}, `created_at` /
`merged_at` / `closed_at` (UTC `Z` with milliseconds), `author.username`,
and `closed_by` / `merged_by`. Commits have `id` (sha), `message`,
`author_name`, `authored_date` — no forge login. Pagination returns `Link`
rel=next plus `X-Next-Page` / `X-Total`.

## Goals / Non-Goals

**Goals:**
- A `ForgeProvider` for GitLab good enough to run the existing analyses over
  a GitLab project.
- Absorb GitLab's vocabulary entirely in the mapping layer — no new
  normalized-model fields.
- GitLab as a third provider in the contract suite, passing the same
  invariants.
- Selection by `--forge gitlab`, `gitlab.com` host detection, and a
  configured self-hosted base URL; bare `owner/repo` still GitHub.

**Non-Goals:**
- GitLab CI/pipeline data (a DORA capability may want it later).
- GitLab write operations.
- GraphQL — REST v4 covers what we read.
- Multiple GitLab instances per run.

## Decisions

### GitLab REST v4; project path URL-encoded; gitlab.com reference

**Choice:** Address projects as `/projects/{owner%2Frepo}` (URL-encode the
namespace path). Endpoints: `/merge_requests?state=all`,
`/merge_requests/{iid}/notes`, `/merge_requests/{iid}/resource_state_events`,
`/repository/commits`, and `/groups/{group}/projects` for `--org`. Develop
and live-smoke against a small public gitlab.com project.

**Verify at apply:** the resource_state_events shape and that `state:"closed"`
carries the actor under `user.username`; confirm against gitlab.com.

### Map GitLab's vocabulary onto the existing model — no new fields

**Choice:** In the GitLab→model mapping: `iid` → `number`; `state` `opened`
→ `"open"`, `merged`/`closed` → `"closed"`; `merged_at` non-null iff the MR
merged (GitLab sets it only when merged); `author.username` → `author`;
commit `author_name` → `author_name`, `id` → `sha`, `authored_date` →
`author_date` (login is `None`, as GitLab keys commits by email/name). `raw`
retains the original GitLab object.

**Rationale:** This is exactly what the normalized model exists for. Keeping
the divergence in the mapping (not the model) means the analyses and storage
are untouched, and the model stays minimal — validated now against three
genuinely different shapes.

### Close actor via resource_state_events

**Choice:** Implement `list_issue_events` against
`/merge_requests/{iid}/resource_state_events`, mapping a `state:"closed"`
event to `ForgeIssueEvent(event="closed", actor=user.username)` — the shape
the classification capability already consumes from GitHub.

**Alternative considered:** read `closed_by` straight off the MR object
(GitLab provides it). Rejected as the primary path because the capability
calls `list_issue_events` generically; the events endpoint is the clean
analogue and also exposes the merge actor for future use.

### Token via PRIVATE-TOKEN; per provider

**Choice:** Read `GITLAB_TOKEN` and send it as the `PRIVATE-TOKEN` header
(GitLab's PAT convention). Unauthenticated access works for public projects
with the same warn-once. No central token.

### Pagination and rate limits

**Choice:** Follow `Link` rel=next where present, otherwise advance `page`
with `per_page` until an empty page (the universal signal, as the Forgejo
provider does). Honour generic `429` / `Retry-After`; GitLab also sends
`RateLimit-*` headers but generic backoff is sufficient.

## Risks / Trade-offs

- **`iid` vs `id` confusion.** → Use `iid` (the user-facing, per-project
  number) as `number`; never `id`. Covered by a provider unit test.
- **`merged` as a distinct state.** → Mapped to `closed` + non-null
  `merged_at`; the contract suite's merge-semantics invariant guards it.
- **resource_state_events missing on old self-hosted GitLab.** → Target v4;
  if absent, classification degrades to "no close actor" rather than
  crashing. Note at apply.
- **Project-path URL-encoding.** → Encode `owner/repo` → `owner%2Frepo` once
  in the provider; unit-test a namespaced path.

## Migration Plan

1. Add `lib/forge/gitlab.py` mapping GitLab v4 onto the model.
2. Register GitLab in selection (name + `gitlab.com`/self-hosted host +
   `GITSWEEPER_GITLAB_URL`); add to the CLI `--forge` set.
3. Add GitLab to the contract suite + a provider unit test file.
4. Docs (README/project.md/CHANGELOG).
5. Live smoke: `fetch --forge gitlab <small-public-project>` + `throughput`;
   re-run a GitHub and a Forgejo repo to confirm no regression.

Rollback is a revert: no schema or persisted-state change.

## Open Questions

- **Live-smoke target:** a small public gitlab.com project (chosen at apply).
  Self-hosted GitLab is supported via env but not assumed.
