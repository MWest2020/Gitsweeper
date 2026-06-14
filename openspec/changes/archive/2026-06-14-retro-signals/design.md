## Context

`dora-metrics` shipped the metric half of `Road_to_el_DORA-do`. The other half
is retro signals: deterministic cues for a team retrospective. Road computed
them over GitHub Project issue threads. gitsweeper is PR-centric and caches no
comment bodies, so this change adds a comments cache and computes PR-based
analogues of Road's signals.

## Goals / Non-Goals

**Goals:**
- Team-level retro signals — stale PRs, long threads, friction language,
  tech-debt markers, smooth PRs — over cached PRs + a new comments cache.
- Deterministic and auditable: documented keyword constants, no LLM.
- Forge-agnostic via the normalized `ForgeComment`.
- No per-person output: signals reference PR numbers only.

**Non-Goals:**
- Sprint/iteration awareness (gitsweeper has no project/sprint data) — "stale
  open PR" stands in for Road's sprint-spillover.
- Sentiment scoring beyond keyword counts.
- Slack delivery / scheduling — that is `scheduled-delivery`.
- Commit-message scanning (commits aren't persisted) — tech-debt markers scan
  comments + titles for now.

## Decisions

### Persist comment bodies in a new `pr_comments` cache

**Choice:** add `pr_comments(pr_id, author, created_at, body, fetched_at)`,
populated via the existing provider `list_issue_comments`. The `retro` command
fetches comments (like `first-response`) then computes over the cache.

**Rationale:** friction language and long threads live in the discussion, not
in titles; the signal is only meaningful with bodies. The provider already
returns them (`ForgeComment.body`); we just persist. Portable SQL, JSON-free,
consistent with the existing schema.

**Trade-off / the thing to sign off:** this is the first time gitsweeper stores
discussion **text** locally. It is a single-user local cache and `retro` output
is team-level (PR numbers, no authors), but the bodies are retained. The
thinner alternative — scan PR titles only, no comments cache — avoids the
retention entirely but is much weaker. Recommended: store the bodies; the value
is in the threads.

### Deterministic bilingual keyword sets (locked here)

**Choice:** carry Road's keyword lists verbatim as documented module constants
(case-insensitive, whole-phrase match):

- **Friction (NL):** "loopt vast", "wacht op", "onduidelijk", "blokkeert",
  "geen idee", "frustrerend", "lastig".
- **Friction (EN):** "blocked", "stuck", "waiting on", "unclear", "no idea",
  "frustrating".
- **Tech-debt:** "hack", "workaround", "todo", "fixme", "wtf", "ugly",
  "tijdelijk", "quick fix".

**Source:** `Road_to_el_DORA-do/.github/prompts/sprint-retro.md`. Keeping them
identical preserves continuity with the workflow this supersedes. They are one
constant per list so they are auditable and adjustable; `dora-metrics` and a
future shared keyword module can converge later.

### Thresholds, documented and adjustable

**Choice:** stale-open = open PR with `created_at` older than 14 days
(configurable via `--stale-days`); long-thread = > 10 comments (Road's number);
smooth = merged within 3 days with < 2 comments. All in documented constants.

### Team-level only

**Choice:** every signal is reported by PR number (and, for friction/tech-debt,
the match count). No author login, name, or `@`-mention appears. Comment
`author` is stored in the cache (for possible future use) but never surfaced by
`retro`.

**Rationale:** Road's "speel op de bal, niet op de mens", encoded as a spec
requirement so it cannot regress — same guarantee `dora` carries.

## Risks / Trade-offs

- **Storing comment text.** → Local single-user cache; team-level output;
  signed off before apply. A `--no-comments` thin mode (titles only) remains
  available as the fallback if retention is unwanted.
- **Keyword lists are coarse / language-bound.** → Documented, adjustable
  constants; bilingual NL+EN as Road had; matches are advisory cues, not
  scores. Reported with counts so a noisy match is visible.
- **Comment fetch cost + auth.** → One listing call per PR, cached after the
  first run (like first-response); some forges need a token for comment
  sub-resources (documented).

## Migration Plan

1. `storage.py`: `pr_comments` table + upsert/list.
2. `capabilities/retro_signals.py`: keyword constants + pure signal functions
   + a `RetroReport` result.
3. `cli.py`: `retro` command — fetch comments via the provider, persist,
   compute, render.
4. Tests (signals, bilingual matching, team-level, empty, storage).
5. Docs + CHANGELOG.
6. Smoke: `retro` over a cached real repo on a forge that allows anonymous
   comment reads (or with a token).

Rollback is a revert plus dropping the `pr_comments` table; no change to
existing tables.

## Open Questions

- **Store comment bodies, or thin titles-only mode?** (Recommended: store; the
  signal needs threads. This is the sign-off.)
- Default `--stale-days` (14?) and the long-thread threshold (10, from Road) —
  fine to adjust.
