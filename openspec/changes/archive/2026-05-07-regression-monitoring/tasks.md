## 1. regression-monitoring capability

- [ ] 1.1 New module `capabilities/regression_monitoring.py` with
      `compute_regression_alerts(conn, *, kpis, baseline_periods=12,
      threshold_sigma=2.0, since=None, author=None, by_author=False,
      repos=None) -> AnalysisResult`.
- [ ] 1.2 Internally calls `kpi_timeseries.compute_kpi_timeseries`
      and groups by (repo, author, kpi) to extract per-series
      trailing window.
- [ ] 1.3 Skip series with fewer than `baseline_periods` trailing
      values; record skipped count in metadata.
- [ ] 1.4 Skip series where trailing stdev is 0; record in metadata.
- [ ] 1.5 Emit one row per moved series with `repo`, `author`,
      `kpi`, `period`, `current_value`, `baseline_mean`,
      `baseline_stdev`, `z_score`, `direction` (`up` / `down`).

## 2. CLI

- [ ] 2.1 New command `gitsweeper regressions --baseline 12
      --threshold 2.0 --kpis ... [--since] [--author] [--repos] [--json]`.
- [ ] 2.2 Sensible default kpis: median-time-to-merge,
      median-first-response, response-rate, volume.

## 3. Tests

- [ ] 3.1 Stable series → no alerts.
- [ ] 3.2 Spike up → up-direction alert with correct z-score.
- [ ] 3.3 Drop down → down-direction alert.
- [ ] 3.4 Insufficient baseline → no alert; metadata records
      skipped count.
- [ ] 3.5 Flat baseline (stdev=0) → no alert.
- [ ] 3.6 --baseline narrows window; --threshold relaxes alerts.

## 4. Validation, smoke, archive

- [ ] 4.1 `openspec validate --strict`.
- [ ] 4.2 `pytest -q` and `ruff check .` clean.
- [ ] 4.3 Smoke against `cache/conductionnl-openregister.sqlite`
      with --baseline 6 (we have ~10 weeks of data; 12 is too
      long for the smoke).
- [ ] 4.4 Update `CHANGELOG.md`.
- [ ] 4.5 `openspec archive regression-monitoring`.
