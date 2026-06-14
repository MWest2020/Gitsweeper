## 1. Comments cache

- [x] 1.1 `storage.py`: `pr_comments` table (pr_id FK, author, created_at, body, fetched_at; portable SQL, no JSON1) + `upsert_comments` + `list_comments`
- [x] 1.2 A fetch path that calls the provider's `list_issue_comments` per PR and persists `ForgeComment` rows (reuse the first-response fetch pattern; cache so a re-run doesn't re-fetch)
- [x] 1.3 Storage test for `pr_comments` upsert/list

## 2. Signal computation

- [x] 2.1 `capabilities/retro_signals.py`: documented keyword constants — `FRICTION_KEYWORDS_NL`, `FRICTION_KEYWORDS_EN`, `TECH_DEBT_KEYWORDS` (verbatim from `Road_to_el_DORA-do/.github/prompts/sprint-retro.md`) + threshold constants (`STALE_DAYS=14`, `LONG_THREAD=10`, smooth window 3d / <2 comments)
- [x] 2.2 Pure signal functions over cached PRs + comments → a `RetroReport`: stale open PRs, long threads, friction (count over bodies+titles, ranked), tech-debt (count + PRs), smooth PRs
- [x] 2.3 All signals reference PR number only — no author surfaced; case-insensitive whole-phrase keyword matching
- [x] 2.4 Empty handling: each signal reported as explicitly empty, no error

## 3. CLI

- [x] 3.1 `gitsweeper retro <repo>` in `cli.py`: `--forge`, `--since`, `--stale-days`, `--json`; NO `--author`. Fetch comments → persist → compute → render
- [x] 3.2 Render the `RetroReport` through `report-rendering` (table + JSON)

## 4. Tests

- [x] 4.1 `tests/test_retro_signals.py`: each signal over canned PR+comment sets; bilingual friction matching (NL + EN positive, non-match negative); tech-debt matching; stale/long-thread/smooth thresholds; empty population
- [x] 4.2 Team-level guarantee: result/JSON carries no author; command has no `--author`
- [x] 4.3 Forge-agnostic: comments from each forge's `ForgeComment` classify identically

## 5. Docs

- [x] 5.1 `README.md`: add `retro` to the command table + a "retro signals" note crediting the keyword-list source (Road)
- [x] 5.2 `CHANGELOG.md`: dated `[Unreleased]` `### Added` entry; note the new `pr_comments` cache (comment bodies stored locally)

## 6. Verify

- [x] 6.1 `uv run ruff check .` clean; `uv run pytest` green
- [x] 6.2 Live smoke: `retro` over a cached real repo (a forge allowing anonymous comment reads, or with a token) renders sensible signals; confirm no author in output
