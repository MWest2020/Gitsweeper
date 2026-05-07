## Context

`kpi-timeseries` answers "how is each KPI trending" at the
aggregate level. `regression-monitoring` answers "which series
moved this period". Neither answers "where is each person's effort
going, and is it landing?" — the user's stated steering need.

The data needed lives in the existing cache: `pull_requests`
(author, state, dates), `pr_first_responses` (response coverage),
and `pr_close_actors` (self-pulled vs maintainer-closed). The
work is shaping that into a per-author × per-repo pivot.

## Goals / Non-Goals

**Goals:**

- One row per `(repo, author)` (or `(period, repo, author)` with
  `--by-period`).
- Columns that distinguish "submitted PRs" from "PRs that
  required a maintainer decision" so a high self-pull rate does
  not deflate the merged rate.
- Clean handling of the not-yet-classified case: the bucket is
  visible, not folded into one of the others.
- Output flows through the renderer interface like everything
  else.

**Non-Goals:**

- Defining "right" things. Effort is descriptive; alignment with
  intent is the operator's call. A future change could add a
  per-repo priority config (`gitsweeper-priorities.yaml`) and
  compute alignment scores; we do not block on that.
- Per-PR drill-down. Aggregate granularity, like the rest of the
  toolchain.
- Topic / label-based pivoting. PR labels live in the
  `raw_payload` JSON; extracting them is a future change once we
  see real demand.

## Decisions

### Three closure buckets, not two

Self-pulled, maintainer-closed, and closed-unenriched are *all*
visible. Folding closed-unenriched into closed-by-maintainer would
inflate the maintainer-rejection rate; folding it into self-pulled
would inflate the duplicate rate. Reporting it separately lets
the operator decide whether to run `gitsweeper classify` first.

The metadata count of `closed_unenriched` total across the result
makes "is my data ready for this question?" a one-look check.

### Effective denominator for merged_rate

`merged / (merged + closed_by_maintainer)` is the fraction of
*decisions* that came out as a merge. The intuitive denominator
("all closed PRs") would punish authors who self-clean their
duplicates — exactly the wrong incentive. The chosen denominator
matches the response-rate convention used elsewhere in the
toolchain (`pr-classification` excludes self-pulled from the
response-rate denominator).

### Closed-unenriched not in the denominator

If we do not yet know whether a closure was self-pulled or
maintainer-closed, we cannot honestly compute `merged_rate`.
Excluding it from the denominator keeps the rate
interpretable; the metadata flags how much was excluded so the
operator knows when to enrich.

### `merged_rate = None` on empty denominator

Same convention as everywhere else in the toolchain: do not emit
`NaN` or `0`. None is the only honest value; the renderer
formats it as the standard placeholder ("—").

### One result, optionally per-period

`--by-period` adds the period column to the row tuple. ISO week,
matching `kpi-timeseries`. The trade-off is row count — N
authors × M repos × P periods grows fast — but at the scale we
see (Conduction ~5–15 active authors × ~10 repos × ~12 weeks),
the table renderer still copes and the JSON is fine for
machines. If portfolio sizes grow, we add filtering or pivot
options without changing the underlying capability.

## Risks / Trade-offs

- **The result can be wide.** Eight columns plus the dimension
  columns is a lot for the table renderer at small terminal
  widths. Markdown and JSON are unaffected. If the table view
  becomes unreadable on real terminals, we add column-selection
  (`--columns submissions,merged_rate`).
- **`pr_close_actors` may be stale.** Enrichment is incremental;
  if a PR was recently closed and we have not run `classify`
  since, it shows as `closed_unenriched`. The metadata count
  makes this visible. We accept the ergonomic cost; auto-running
  classify silently would breach the
  "no surprise GitHub calls" principle from
  `pr-process-report`.
- **Anonymous-bot PRs muddy attribution.** `github-actions[bot]`
  shows up as an author. We treat bots like any other author —
  the operator can filter them with `--author` exclusion (which
  this change does *not* introduce; if it becomes a real pain
  point we add `--exclude-authors`).
