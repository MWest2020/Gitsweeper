## 1. DORA computation

- [x] 1.1 `capabilities/dora_metrics.py`: a `CORRECTIVE_KEYWORDS` constant + an `is_corrective(title)` helper (leading `revert`/`hotfix`/`rollback`, or `fix:`/`fix(...):`, case-insensitive)
- [x] 1.2 Pure functions over the cached merged PRs producing a `DoraReport` result: deployment frequency (count per `week`/`month` bucket + headline rate), lead time (median/p75/p90 of created→merged), change failure rate (corrective ÷ all merged), time to restore (median created→merged over corrective)
- [x] 1.3 DORA band classification from documented threshold constants (Elite/High/Medium/Low) for each metric; carry the sample count with each
- [x] 1.4 Read the PR title from the stored `raw_payload` (uniform `title` across forges); reuse storage's merged-PR query (honour `--since`)
- [x] 1.5 Empty-population handling: explicit empty result, no NaN/divide-by-zero

## 2. CLI

- [x] 2.1 `gitsweeper dora <repo>` in `cli.py`: `--since`, `--period {week,month}` (default month), `--json`; NO `--author`
- [x] 2.2 Render the `DoraReport` through `report-rendering` (table + JSON)

## 3. Tests

- [x] 3.1 `tests/test_dora_metrics.py`: each of the four metrics over canned PR sets; the corrective heuristic (positive + negative titles); period bucketing; band classification at threshold boundaries; empty population
- [x] 3.2 Team-level guarantee: assert the result/JSON carries no author field and the command has no `--author`
- [x] 3.3 Forge-agnostic: a canned set whose `raw_payload` titles come from each forge shape still classifies correctly

## 4. Docs

- [x] 4.1 `README.md`: add `dora` to the command table + a short "DORA (team-level, proxy-based)" note naming the proxies
- [x] 4.2 `CHANGELOG.md`: dated `[Unreleased]` `### Added` entry

## 5. Verify

- [x] 5.1 `uv run ruff check .` clean; `uv run pytest` green
- [x] 5.2 Live smoke: fetched `forgejo/meta` (Forgejo/Codeberg) into a cache, then `gitsweeper dora forgejo/meta` rendered sensible metrics + bands (deploy freq 0.32/day High, lead-time median 0.17d Elite, change-fail 0.00 Elite, time-to-restore empty handled cleanly, per-month deploy buckets). JSON output confirmed to contain no author/login/username (team-level guarantee). The path is forge-agnostic (reads the cache), so GitHub/GitLab render identically from their caches.
