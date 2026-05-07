## Why

The user's stated steering need #2 — *"werken onze mensen nog wel
aan de juiste dingen"* — is a question about where attention is
flowing. The KPI time-series shows aggregate volume; what is
missing is the **per-author × per-repo** breakdown of that volume,
plus its outcome (merged / closed / open / self-pulled).

This is a different shape from the existing series. KPI rows are
one number per (period, repo, kpi). Effort-allocation rows are
many numbers per (period, repo, author): volume,
merged_count, merged_rate, self_pulled_count, response_rate. A
separate capability with its own structured result.

## What Changes

- **New**: `effort-allocation` capability. For a given scope (a
  list of repos and a `--since` window), compute one row per
  `(repo, author)` combination — optionally split per period —
  with the columns: `submissions`, `merged`, `merged_rate`,
  `self_pulled`, `closed_by_maintainer`, `still_open`. The result
  flows through the existing renderer interface (table / JSON /
  markdown).

No changes to existing capabilities.

## Capabilities

### New Capabilities

- `effort-allocation`: per-author per-repo (optionally per-period)
  pivot of submission volume and outcomes. Answers
  *"who is working on what, and is it landing"* in one structured
  result.

## Impact

- **Code**: new module `capabilities/effort_allocation.py`. Reuses
  the storage layer; relies on `pr-classification` rows (close
  actor) being populated to compute `self_pulled`. When a closed-
  unmerged PR is not yet enriched, it is reported as
  `closed_by_maintainer` *only if* we already know that —
  otherwise it falls into a `closed_unenriched` bucket, so the
  operator can decide to run `classify` and re-run.
- **CLI**: new `gitsweeper effort` command.
- **Out of scope**: a notion of "right" things — effort is shown
  raw; the operator interprets. A future change could add a
  per-repo priority config that scores allocation against
  declared priorities.
