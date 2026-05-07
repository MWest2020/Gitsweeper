## Context

`kpi-timeseries` produces long-format `(period, repo, author, kpi,
value, sample_size)` rows. To make this actionable for the user's
regression-watch need, we summarise each series and call out the
movers. The user will consume the output as a short list ("these
are the KPIs that drifted this week"), not as a full series scan.

## Goals / Non-Goals

**Goals:**

- For each `(repo, [author], kpi)` series, decide if the **latest
  period** sits outside the trailing baseline noise band, and if
  so emit an alert with magnitude and direction.
- Configurable window (`--baseline`) and threshold (`--threshold`)
  so the operator can match the cadence and noisiness of their
  domain.
- Self-contained alert rows so downstream tooling (a cron-driven
  emailer, a Slack bot, a dashboard) does not need to re-query
  the cache.

**Non-Goals:**

- Bootstrap confidence intervals. Z-score on the trailing
  population is enough for v1. If false positives prove a problem
  on real data, we revisit.
- Time-series statistical models (ARIMA, change-point detection).
  Same reason: simpler test first; upgrade if real data motivates.
- Automatic alert delivery. The command writes a structured
  result; the cron/wrapper that consumes it is the operator's.
- Multi-period regression (e.g. "last 3 weeks have all been
  high"). v1 looks at the most recent period only; rolling-window
  smoothing is a natural follow-up if needed.

## Decisions

### Z-score on trailing values, not bootstrap

For each series we compute `mean` and `stdev` over the trailing N
periods (excluding the current). The latest value is then
expressed as `z = (current - mean) / stdev`. If `|z| >= threshold`
we emit an alert.

This is fast, easy to explain, and easy to check by eye. The
alternative (bootstrap CI on the median's sampling distribution)
is more principled in the abstract, but adds runtime cost and
opacity for a v1 that has not yet seen real false-positive
behaviour. Upgrade later if motivated.

### Latest period only

The "latest period" is whichever period has the highest value in
its label. ISO-week labels (`2026-W18`) sort
correctly as strings, so this is a string-max operation. For
calendar-month / quarter labels the same property holds.

### Insufficient baseline → no alert

If the trailing window contains fewer than the requested number of
periods, we silently produce no alert for that series. The
alternative (some kind of warning row) creates noise during
ramp-up; the metadata records how many series were skipped so the
absence is observable.

### Stdev floor

If all trailing values are identical, the stdev is 0 and the
z-score is undefined (or +inf for any current ≠ baseline). We
treat stdev = 0 by skipping the alert: a flat baseline carries no
notion of "noise" to be exceeded. A consumer who wants
"any change is an alert" can use a threshold of `0` and a
baseline-flat heuristic; that is not what `--threshold` does.

### Output is a structured `AnalysisResult` only

Same renderer-layer pattern as everything else. Table is the
human-readable default; JSON is what the cron wrapper reads.
Markdown is supported because the renderer registers it; that lets
the report capability one day include a "regressions this week"
section without bespoke formatting.

## Risks / Trade-offs

- **Z-score is not robust to skewed baselines.** Many of our KPIs
  are right-skewed (median TTM, FRT). The trailing distribution of
  weekly medians, though, is usually closer to symmetric. Real
  data will tell us if this matters; for v1 the simpler test wins.
- **Alert noise from low-volume periods.** A week with only 1 PR
  produces a high-variance estimate. Consumers should look at
  `sample_size` (carried through from the underlying series row)
  before acting on an alert. We do not gate by sample size in v1
  — that is a kind of policy decision the operator should make,
  not the tool.
- **The "latest period" can be partial.** If the analysis runs
  mid-week, the current ISO week is not yet complete and naturally
  has a low volume + skewed value. The cron/operator is expected
  to schedule runs at week-boundary; we will not paper over
  scheduling bugs in the analysis.
