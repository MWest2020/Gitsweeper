## Context

`Road_to_el_DORA-do` computed DORA metrics from GitHub Project data inside a
Slack-posting Actions workflow. gitsweeper now has a forge-agnostic PR cache
(GitHub, Forgejo, GitLab) and a renderer. `dora-metrics` reimplements the DORA
core as a capability over that cache.

The cache holds, per PR: `number`, `state`, `created_at`, `merged_at`,
`closed_at`, `author`, and the full `raw_payload`. It does **not** hold
releases/tags, per-PR commit lists, or issue status history. So v1 derives the
four metrics from what is there, with proxies documented below; richer inputs
are follow-on changes.

## Goals / Non-Goals

**Goals:**
- The four DORA metrics — deployment frequency, lead time for changes, change
  failure rate, time to restore — computed team-level from the PR cache.
- Forge-agnostic: identical over GitHub, Forgejo, GitLab.
- Deterministic and auditable: no LLM, no per-person data.
- Interpretable: each metric annotated with its DORA performance band.

**Non-Goals:**
- Release/tag-based deployment frequency (needs a new forge method) — proxy
  with merges for now.
- First-commit-based lead time (needs per-PR commits) — proxy with PR cycle
  time.
- Issue-rework rate (needs issue status history) — out of scope for v1.
- Per-author DORA. Deliberately excluded (privacy constraint).
- Slack delivery / scheduling — that is `scheduled-delivery`.

## Decisions

### Compute from the cached PRs, with documented proxies

**Choice:**
- **Deployment frequency** = count of PRs with a non-null `merged_at` per
  `--period` bucket (week or month). A merge is treated as a deployment.
- **Lead time for changes** = median / p75 / p90 of (`merged_at` −
  `created_at`) over merged PRs in scope (PR cycle time).
- **Change failure rate** = (# merged PRs whose title matches the
  fix/revert/hotfix heuristic) ÷ (# merged PRs).
- **Time to restore service** = median (`merged_at` − `created_at`) of the
  fix/revert/hotfix PRs.

**Rationale:** these need no new fetching and no provider/schema change, so the
capability is boring to build and review, and works over all three forges
immediately. Merge-as-deploy and cycle-time-as-lead-time are the standard DORA
proxies used when there is no explicit deploy pipeline or commit-level data.
The cost is accuracy, which the output names explicitly (see Risks); a later
change can swap in releases / first-commit data behind the same metric names.

**Alternatives considered:** add `list_releases` to all three providers for
true deployment frequency — real scope (three providers + contract) for a v1
that proxies fine; deferred. Add `target_branch` to the model to count only
default-branch merges — a model+mapping change across three forges; v1 counts
all merges and documents it.

### Fix/revert/hotfix detection: a deterministic title heuristic

**Choice:** a merged PR is "corrective" if its title (case-insensitive,
read from `raw_payload["title"]` — uniform across the three forges) matches a
documented keyword set: a leading `revert`, `hotfix`, `rollback`, or a
conventional-commit `fix:` / `fix(scope):` prefix. The keyword list is a module
constant.

**Rationale:** deterministic and auditable — no LLM black-box — exactly the
property `Road_to_el_DORA-do` insisted on. Title-based keeps it forge-agnostic
(all three expose `title`) and needs no extra API calls.

**Alternatives considered:** Road's "revert/hotfix PR within 48h touching the
same files as a prior merge" — more precise but needs per-PR file lists (extra
fetching) and pairing logic; deferred. The title heuristic under-counts
silent fixes; documented as a known floor, not a true rate.

### Team-level only — no per-author output

**Choice:** `dora` has no `--author`; the result carries no author field and no
logins. Authorship in the cache is used only for counts that are already
aggregate (and DORA needs none of it).

**Rationale:** the `Road_to_el_DORA-do` principle "speel op de bal, niet op de
mens". DORA measures a team's delivery system, not individuals; per-person DORA
invites misuse. Encoded as a spec requirement so it cannot regress.

### DORA performance bands from published thresholds

**Choice:** annotate each metric with Elite / High / Medium / Low using the
DORA report thresholds, held in a documented constant:
- Deployment frequency: Elite ≥ daily; High weekly–monthly; Medium monthly–
  6-monthly; Low < 6-monthly.
- Lead time: Elite < 1 day; High < 1 week; Medium < 1 month; Low ≥ 1 month.
- Change failure rate: Elite ≤ 15%; High ≤ 30%; Medium ≤ 45%; Low > 45%.
- Time to restore: Elite < 1 hour; High < 1 day; Medium < 1 week; Low ≥ 1 week.

**Rationale:** raw numbers are hard to read; the band is the standard,
recognised interpretation. Thresholds live in one constant so they are
auditable and adjustable.

## Risks / Trade-offs

- **Proxies are coarse.** Merge ≠ deploy when CD is decoupled; PR cycle time ≠
  true lead time; the title heuristic under-counts fixes. → The output labels
  each metric as a proxy and names its basis; the band is advisory. A later
  change swaps richer inputs behind the same names.
- **Small samples make bands jumpy.** → Report the underlying counts alongside
  every metric and band, and handle an empty population explicitly (no NaN,
  no division-by-zero) — consistent with the throughput capability.
- **Keyword heuristic is English/convention-biased.** → It is a documented,
  adjustable constant; `retro-signals` (follow-on) already plans bilingual
  keyword lists that this can later share.

## Migration Plan

1. `capabilities/dora_metrics.py`: pure functions over a list of cached PRs →
   a `DoraReport`; no I/O beyond storage reads.
2. `cli.py`: `dora` command (reads cache, calls the capability, renders).
3. Tests over canned PR sets (incl. empty, all-merged, mixed, corrective).
4. Docs + CHANGELOG.
5. Smoke: `gitsweeper dora` over a cached real repo on each forge.

Rollback is a revert: read-only, no schema or persisted-state change.

## Open Questions

- **Default period:** week or month? (Recommend `--period month` default for
  small repos so buckets aren't mostly empty; weekly for active ones.)
- Whether to surface deployment frequency as a count-per-bucket series or a
  single rate — leaning: both (a headline rate + the per-bucket series, like
  the kpi-timeseries capability).
