## Why

`kpi-timeseries` produces the raw long-format series; on its own it
is still descriptive. To support **regression watch** — the user's
stated sturing-need #1 — the tool needs to point at *which* KPIs
moved away from their trailing baseline, with a magnitude and a
direction, so the user reads a short list of alerts rather than
scanning the full series.

This change adds that one step: take the latest period of each
series, compare it against the trailing N periods, emit alerts
where the current value sits outside the baseline noise band.

## What Changes

- **New**: `regression-monitoring` capability. Consumes the same
  long-format series as `kpi-timeseries` (per-period KPI values per
  repo, per author optionally), summarises the trailing baseline
  per (repo, author, kpi), and emits a structured list of alerts —
  one row per moved KPI — with current value, baseline mean and
  standard deviation, z-score, and direction (up or down). KPIs
  that did not move are omitted.

No spec changes to existing capabilities.

## Capabilities

### New Capabilities

- `regression-monitoring`: trailing-baseline alerting on top of the
  `kpi-timeseries` long-format series. The first piece of A
  (Analysis) on top of the existing R (Reporting).

## Impact

- **Code**: new module `capabilities/regression_monitoring.py`. Reuses
  the kpi-timeseries computation; no new SQL or HTTP work.
- **CLI**: new `gitsweeper regressions` command.
- **Out of scope**: bootstrap confidence intervals (z-score on the
  trailing distribution is enough for v1; CIs land if and when we
  observe false positives that motivate the extra cost). Alert
  delivery (email, Slack) — the command writes a result; whatever
  cron/wrapper consumes it is up to the operator.
