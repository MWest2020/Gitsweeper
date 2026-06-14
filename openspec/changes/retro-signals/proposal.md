## Why

`Road_to_el_DORA-do` produced two halves: DORA metrics (now shipped as
`dora-metrics`) and **retro signals** — the conversation-topic cues a team
discusses at a retro: where work got stuck, which threads ran long, where the
language turned frustrated, where tech debt is accruing. This change brings
that second half into gitsweeper, forge-agnostic and team-level.

The honest catch: Road read those signals from issue *comment threads*, and
gitsweeper does not cache comment bodies — only PRs and a first-response
timestamp. A retro-signals worth having needs the discussion text. The forge
providers already expose it (`list_issue_comments` → normalized `ForgeComment`
with a `body`); this change **persists** those bodies in a new comments cache
and computes the signals over them.

## What Changes

- **New comments cache.** A `pr_comments` table (pr_id, author, created_at,
  body, fetched_at) populated by a fetch step that reuses the existing
  provider `list_issue_comments`. This is the new piece — gitsweeper will
  store PR discussion text locally for the first time.
- **New capability `retro-signals`** with a `gitsweeper retro <repo>` command
  computing, team-level, over the scoped window:
  - **Stale open PRs** — PRs still open older than a threshold (from cached
    `created_at` + state). The PR-cache analogue of Road's sprint-spillover.
  - **Long threads** — PRs with more than N comments. Top few.
  - **Friction language** — counts of a documented bilingual (NL + EN) keyword
    set in comment bodies + PR titles; top PRs by match count.
  - **Tech-debt markers** — counts of a documented keyword set
    (`hack`/`workaround`/`TODO`/`tijdelijk`/…) in comment bodies + PR titles.
  - **Smooth PRs** — merged quickly with few comments (a positive signal).
- **Team-level only**, like `dora`: signals are reported by **PR number**,
  never by author login or `@`-mention. Keyword lists are deterministic
  constants — no LLM, matching Road's "auditable, no black-box" rule.
- **Forge-agnostic.** Comments come through the normalized `ForgeComment`, so
  the signals compute identically over GitHub, Forgejo, and GitLab.

## Capabilities

### New Capabilities
- `retro-signals`: deterministic, team-level retro conversation cues
  (stale PRs, long threads, friction language, tech-debt markers, smooth PRs)
  over cached PRs + a new comments cache.

### Modified Capabilities
<!-- none — adds a comments table + fetch; no change to existing analyses or specs -->

## Impact

- **Storage (NEW persisted data):** a `pr_comments` table holding comment
  **bodies**. This is the first time gitsweeper stores discussion text. It is
  a local single-user SQLite cache, and `retro` output stays team-level (no
  authors), but the bodies sit in the cache — a deliberate data-retention
  step that wants sign-off.
- **Code (Python):** new `capabilities/retro_signals.py` (keyword constants +
  pure signal functions + result); `storage.py` gains `pr_comments`
  upsert/list; a `retro` command in `cli.py` that fetches comments (provider)
  then computes. Reuses `list_issue_comments` — no new provider method.
- **Tests:** `tests/test_retro_signals.py` — each signal, the bilingual
  keyword matching, team-level guarantee (no author in output), empty
  handling; a storage test for `pr_comments`.
- **CLI:** `gitsweeper retro <repo> [--forge] [--since] [--json]` — needs a
  fetch (like `first-response`), so it takes `--forge`.
- **Docs / CHANGELOG:** README command + a "retro signals" note naming the
  keyword lists' source (Road); CHANGELOG entry.
- **Note on auth:** comment sub-resources may require a token on some forges
  (e.g. gitlab.com), same caveat as `first-response`.

## Decision needed before apply

The new bit — **persisting PR comment bodies locally** — is a data-retention
choice, and the friction/tech-debt **keyword lists** are non-obvious picks.
Both want your sign-off (this is the spec gate). Alternative if you'd rather
not store comment text: a thinner v1 that scans only PR **titles**
(no comments cache) — forge-agnostic and zero new persistence, but much
weaker, since friction lives in threads, not titles.

## Follow-on (not this change)

- `scheduled-delivery` — scheduled run → Slack Block Kit (DORA + retro),
  superseding the `Road_to_el_DORA-do` Actions workflow.
