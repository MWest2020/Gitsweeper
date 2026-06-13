## Why

With the forge seam complete (GitHub, Forgejo, GitLab), the engine can finally
deliver the thing `Road_to_el_DORA-do` prototyped: DORA delivery metrics —
over any forge, not just GitHub. This is the USP of the merge. `dora-metrics`
is the first capability absorbed from that prototype: the four classic DORA
metrics, computed at **team level only**, rendered through the existing
renderer.

It is deliberately built on the data gitsweeper **already caches** (pull
requests), using documented proxies, so it needs no new fetching and no
provider change. Release-based deployments, per-PR first-commit lead time, and
issue-rework signals are richer inputs that later changes can add; v1 ships the
boring, immediately-useful version from cached PRs.

## What Changes

- **New capability `dora-metrics`** with a `gitsweeper dora <repo>` command
  computing the four DORA metrics from the local PR cache, scoped by `--since`
  and bucketed by a `--period` (week/month):
  - **Deployment frequency** — merged PRs per period (a merge = a deployment;
    the standard proxy when there is no explicit deploy pipeline).
  - **Lead time for changes** — median (+ p75/p90) of PR `created_at` →
    `merged_at` over merged PRs (PR cycle time as the lead-time proxy).
  - **Change failure rate** — fraction of merged PRs whose title marks them a
    fix/revert/hotfix (deterministic keyword heuristic), i.e. share of
    deployments that were corrective.
  - **Time to restore service** — median time-to-merge of those
    fix/revert/hotfix PRs (how fast corrective changes land).
- **Team-level only.** No per-author breakdown, no logins or `@`-mentions in
  the output — "speel op de bal, niet op de mens", carried over from
  `Road_to_el_DORA-do` as a spec-level constraint. (This is why `dora` has no
  `--author`, unlike `throughput`.)
- **Forge-agnostic.** Operates on the normalized cached PRs, so it works
  identically over GitHub, Forgejo, and GitLab. The fix/revert heuristic reads
  the PR title, which all three forges expose under `title`.
- **DORA performance band.** Each metric is annotated with its DORA band
  (Elite / High / Medium / Low) using the published thresholds, so the output
  is interpretable at a glance.
- Renders through the `report-rendering` capability (CLI table by default,
  `--json`), like every other analysis.

## Capabilities

### New Capabilities
- `dora-metrics`: the four DORA metrics computed team-level from the cached PR
  data, forge-agnostic, with documented proxies and DORA performance bands.

### Modified Capabilities
<!-- none — reads the existing cache; no change to forge-access, storage, or other analyses -->

## Impact

- **Code (Python):** new `src/gitsweeper/capabilities/dora_metrics.py`
  (computation + a `DoraReport` result), a `dora` command in `cli.py`. Reads
  merged PRs from storage; parses the PR title from the stored `raw_payload`
  (uniform `title` field across forges) for the fix/revert heuristic. No
  fetching, no schema change, no provider change.
- **Tests:** `tests/test_dora_metrics.py` — the four metrics, the keyword
  heuristic, period bucketing, empty-population handling, band classification,
  and the team-level guarantee (no author field in the result).
- **CLI:** `gitsweeper dora <repo> [--since] [--period week|month] [--json]`.
- **Docs / CHANGELOG:** README command table + a short "DORA" note;
  `CHANGELOG` entry. Not breaking.

## Follow-on (not this change)

- `retro-signals` — sprint-spillover, long threads, friction-language,
  tech-debt markers (deterministic keyword lists, no LLM).
- `scheduled-delivery` — scheduled run → Slack Block Kit, superseding the
  `Road_to_el_DORA-do` Actions workflow.
- Richer DORA inputs: release/tag-based deployment frequency, first-commit lead
  time, issue-rework rate — each its own change if the proxies prove too coarse.
