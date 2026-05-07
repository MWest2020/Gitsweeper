## 1. effort-allocation capability

- [ ] 1.1 New module `capabilities/effort_allocation.py` with
      `compute_effort_allocation(conn, *, since=None, repos=None,
      by_period=False) -> AnalysisResult`.
- [ ] 1.2 Pull rows by joining `pull_requests` with
      `pr_close_actors`, optionally bucketing by ISO week derived
      from `created_at`.
- [ ] 1.3 Three closure buckets: `self_pulled`,
      `closed_by_maintainer`, `closed_unenriched`.
- [ ] 1.4 `merged_rate = merged / (merged + closed_by_maintainer)`;
      `None` if denominator is 0.
- [ ] 1.5 Metadata records `closed_unenriched_total` and the row
      count.

## 2. CLI

- [ ] 2.1 New command `gitsweeper effort [--since] [--repos]
      [--by-period] [--json]`.

## 3. Tests

- [ ] 3.1 Multi-author multi-repo seed → row per (repo, author).
- [ ] 3.2 `--by-period` adds period column.
- [ ] 3.3 Self-pulled vs maintainer-closed counted from
      `pr_close_actors`.
- [ ] 3.4 Closed-unenriched is its own bucket.
- [ ] 3.5 `merged_rate` excludes self-pulled and unenriched.
- [ ] 3.6 Empty denominator → `merged_rate is None`.

## 4. Validation, smoke, archive

- [ ] 4.1 `openspec validate --strict`.
- [ ] 4.2 `pytest -q` and `ruff check .` clean.
- [ ] 4.3 Smoke against `cache/conductionnl-openregister.sqlite`
      with `--since 2026-01-01`.
- [ ] 4.4 Update `CHANGELOG.md`.
- [ ] 4.5 `openspec archive effort-allocation`.
