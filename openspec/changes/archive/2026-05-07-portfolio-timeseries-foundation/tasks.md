## 1. Multi-repo and --org fetch

- [ ] 1.1 `lib/github_client.py`: add `list_org_repos(org)` using
      the existing paginate / rate-limit machinery.
- [ ] 1.2 `cli.py`: `fetch` accepts `nargs=-1` positional args; add
      `--org <name>` option. Combine and dedupe before iterating.
- [ ] 1.3 Per-repo failure does not abort the batch: log to stderr,
      track exit code, continue.
- [ ] 1.4 Tests with mocked transport: org pagination; positional
      multi-repo; combination dedupe; partial failure exit code.

## 2. KPI timeseries capability

- [ ] 2.1 `capabilities/kpi_timeseries.py`:
      `compute_kpi_timeseries(conn, *, kpis, period="iso-week",
      since=None, author=None, repos=None) -> AnalysisResult`.
- [ ] 2.2 Closed KPI registry: `median-time-to-merge`,
      `median-first-response`, `response-rate`, `volume`. Unknown
      KPI raises `ValueError` translated to `BadParameter` at the
      CLI boundary.
- [ ] 2.3 Period seam: `period` parameter accepts `"iso-week"`
      today; the bucket function is dispatched on the value so
      `"calendar-month"` etc. land as a single-line addition later.
- [ ] 2.4 Long format: rows are
      `[period, repo, author, kpi, value, sample_size]`. Author
      column is `None` when the user did not group by author.
- [ ] 2.5 Empty buckets omitted (no NaN/0 sentinels).
- [ ] 2.6 CLI: `gitsweeper timeseries [--kpis] [--period]
      [--since] [--author] [--repos] [--json]`.
- [ ] 2.7 Tests: synthetic data over multiple ISO weeks, multi-repo
      aggregation, by-author breakdown, KPI-name validation,
      empty-bucket omission, --since narrowing, --repos restriction.

## 3. Validation, smoke, archive

- [ ] 3.1 `openspec validate --strict` (specs and change). Fix
      issues.
- [ ] 3.2 `pytest -q` and `ruff check .` clean.
- [ ] 3.3 Smoke against the existing `cache/conductionnl-openregister.sqlite`:
      `gitsweeper timeseries --kpis median-time-to-merge,volume
      --period iso-week --since 2025-01-01 --db-path cache/conductionnl-openregister.sqlite`.
- [ ] 3.4 Update `CHANGELOG.md`.
- [ ] 3.5 `openspec archive portfolio-timeseries-foundation`.
