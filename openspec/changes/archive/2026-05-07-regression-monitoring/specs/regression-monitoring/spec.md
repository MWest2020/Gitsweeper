## ADDED Requirements

### Requirement: Compute trailing-baseline alerts for each moved KPI

The system SHALL produce an `AnalysisResult` whose rows describe,
for each (repo, [author], kpi) combination, whether the latest
period's value departs from the trailing baseline distribution by
more than a configurable threshold, expressed as a z-score on the
trailing-baseline mean and standard deviation.

#### Scenario: Stable series produces no alerts

- **GIVEN** a KPI series whose latest value sits within ±1 standard
  deviation of the trailing-baseline mean
- **WHEN** the regression analysis runs with the default threshold
  of 2σ
- **THEN** no alert row is emitted for that (repo, kpi)

#### Scenario: Spike above baseline is flagged with direction up

- **GIVEN** a KPI series whose trailing 12 periods have mean 1.0
  and standard deviation 0.2, and the latest period is 2.5
- **WHEN** the regression analysis runs with threshold 2σ
- **THEN** an alert row is emitted with `direction == "up"`
- **AND** the row records `current_value`, `baseline_mean`,
  `baseline_stdev`, and `z_score` so the magnitude is visible

#### Scenario: Drop below baseline is flagged with direction down

- **GIVEN** a series whose latest period is 3σ below the trailing
  mean
- **WHEN** the regression analysis runs
- **THEN** an alert row is emitted with `direction == "down"`

#### Scenario: Insufficient baseline produces no alerts, not bogus ones

- **GIVEN** a series with fewer than the minimum required periods
  in the baseline (e.g. only 2 trailing periods for a default
  baseline of 12)
- **WHEN** the regression analysis runs
- **THEN** no alert is emitted for that (repo, kpi)
- **AND** the metadata records the population that was skipped so
  the absence is interpretable

### Requirement: Configurable trailing-baseline window and threshold

The system SHALL accept `--baseline <n>` (number of trailing
periods to use; default 12) and `--threshold <s>` (z-score
threshold; default 2.0) so the operator can tune sensitivity to
their domain.

#### Scenario: --baseline narrows the window

- **GIVEN** the user supplies `--baseline 4`
- **WHEN** the regression analysis runs
- **THEN** the four periods immediately preceding the latest one
  are used to compute the baseline mean and standard deviation
- **AND** earlier periods do not contribute

#### Scenario: --threshold relaxes alerting

- **GIVEN** a series whose latest value sits 2.2σ above the
  baseline mean
- **WHEN** the user runs with `--threshold 3`
- **THEN** no alert is emitted for that series
- **AND** the same input with `--threshold 2` would have alerted

### Requirement: Emit alerts as structured rows for downstream consumption

The system SHALL emit alerts through the standard renderer
interface (`report-rendering`), so the same command produces a
human-readable table by default and a machine-readable JSON
payload with `--json`. Alerts must carry enough fields that a
downstream consumer (cron-driven mailer, Slack bot, dashboard
generator) can render or filter without re-querying the cache.

#### Scenario: Each alert row is self-contained

- **WHEN** an alert is emitted
- **THEN** the row contains, at minimum, `repo`, optional
  `author`, `kpi`, `period` (latest), `current_value`,
  `baseline_mean`, `baseline_stdev`, `z_score`, and `direction`
- **AND** the metadata records the baseline window length and
  threshold used so the run is reproducible
