## 1. Storage extensions

- [ ] 1.1 Add `pr_close_actors` table to `SCHEMA_STATEMENTS` in
      `lib/storage.py` (pr_id PK FK, actor TEXT, fetched_at TEXT
      NOT NULL).
- [ ] 1.2 Add `upsert_close_actor(conn, pr_id, actor)` and
      `list_close_actors(conn, repo_id)` functions.
- [ ] 1.3 Extend `list_pull_requests` and `list_first_responses` to
      accept an optional `author` parameter (case-insensitive match
      via `LOWER()`).
- [ ] 1.4 Tests: schema includes new table; upsert is idempotent;
      author filter is case-insensitive.

## 2. github_client extensions

- [ ] 2.1 Add `list_issue_events(owner, repo, number)` returning an
      iterator over events using the same paginate / rate-limit
      machinery.
- [ ] 2.2 Test with mocked transport: pagination, rate-limit
      handling reused.

## 3. --author filter on pr-throughput-analysis

- [ ] 3.1 Thread `author` through `compute_throughput` and
      `compute_first_response` in `capabilities/pr_throughput.py`.
- [ ] 3.2 Add `--author` flag to `throughput` and `first-response`
      CLI commands.
- [ ] 3.3 Tests: per-author throughput math; --author + --since
      composition; empty-population result; case-insensitivity.

## 4. Temporal-patterns analysis

- [ ] 4.1 Add `compute_temporal_patterns(conn, repo_id, *,
      author=None, since=None) -> AnalysisResult` to
      `capabilities/pr_throughput.py`. Result columns include
      day-of-week submission counts, response counts, median
      first-response by submission DOW, and hour-of-day distributions.
- [ ] 4.2 Add `gitsweeper patterns` CLI command (uses --author and
      --since like the others).
- [ ] 4.3 Tests on synthetic data: weekday counts, hour buckets,
      empty buckets reported with sample size 0.

## 5. Markdown renderer

- [ ] 5.1 Add `MarkdownRenderer` class in `lib/rendering.py`,
      register as `"markdown"`.
- [ ] 5.2 Tests: heading is the title; rows appear; metadata appears;
      no decorative banners; existing renderers unchanged.

## 6. pr-classification capability

- [ ] 6.1 New module `capabilities/pr_classification.py` with:
      `enrich_close_actors(conn, client, repo_id, owner, name)` —
      iterates over closed-without-merge PRs, skips already-cached,
      fetches events, persists actor (or NULL).
- [ ] 6.2 `compute_classification(conn, repo_id, *, author=None) ->
      AnalysisResult` — counts self-pulled / maintainer-closed /
      unknown; metadata records adjusted denominator for response
      rate.
- [ ] 6.3 New CLI command `gitsweeper classify <repo>` (and option
      on `report`).
- [ ] 6.4 Tests with FakeClient and synthetic events: incremental
      skip; null actor → unknown; classification correctness; PRs
      not closed-unmerged are skipped.

## 7. pr-process-report capability

- [ ] 7.1 New module `capabilities/process_report.py` with
      `generate_report(conn, client, owner, name, *, author=None,
      since=None, refresh=False) -> str`.
- [ ] 7.2 The function composes section by section, calling each
      capability for its `AnalysisResult` and the markdown renderer
      to format. Sections: header, volume, time-to-merge,
      time-to-first-response, classification, temporal patterns.
- [ ] 7.3 New CLI command `gitsweeper report <repo> [--author]
      [--since] [--refresh] [--out PATH]`. Default writes to stdout.
- [ ] 7.4 Tests: empty cache produces non-zero exit with a clear
      message; --out writes file; --refresh path goes through
      fetch / first-response / classify; sections appear in fixed
      order.

## 8. Validation and archive

- [ ] 8.1 `openspec validate --strict` (specs and change). Fix
      issues.
- [ ] 8.2 Full `pytest -q` and `ruff check .` clean.
- [ ] 8.3 Smoke run: `gitsweeper report nextcloud/app-certificate-
      requests --author MWest2020 --out /tmp/test-report.md` and
      eyeball the output.
- [ ] 8.4 Update `CHANGELOG.md` with the dated entry.
- [ ] 8.5 `openspec archive reusable-process-report` to merge the
      deltas into baseline specs.
