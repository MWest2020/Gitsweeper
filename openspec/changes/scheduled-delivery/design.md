## Context

`dora-metrics` and `retro-signals` compute team-level reports from the cache.
`Road_to_el_DORA-do` delivered the equivalent as a weekly Slack Block Kit
message from a GitHub Action. This change reimplements the delivery as a
portable `gitsweeper deliver` command, per the agreed shape: stdout/file by
default, Slack only on explicit opt-in, scheduling left to the user.

## Goals / Non-Goals

**Goals:**
- One command that composes DORA + retro into a Slack Block Kit message (and a
  markdown alternative), team-level.
- Egress opt-in and explicit: no network unless `--post` + a webhook.
- Reuse the two existing capabilities; add only composition + formatting +
  the POST.

**Non-Goals:**
- Built-in scheduling (cron/Actions/routine). The command is one-shot; the
  user schedules it. Documented, not coded.
- Multiple channels / a Slack app with broad scopes. One incoming webhook,
  one channel — the boring, narrow egress (as Road chose).
- Per-person content. Inherited team-level guarantee from dora + retro.
- LLM summarisation. The message is the deterministic data, as Road insisted.

## Decisions

### A one-shot `gitsweeper deliver` command; scheduling is external

**Choice:** `deliver` runs once and exits. Periodic execution is the user's
cron or a scheduling routine, documented in the README.

**Rationale:** a forge-agnostic CLI shouldn't embed a scheduler or couple to
one forge's CI (a GitHub Action delivering GitLab metrics is incoherent). A
plain command composes with any scheduler and stays testable.

### Egress is opt-in: stdout/file default, Slack only with `--post`

**Choice:** default output is the rendered payload to stdout or `--out FILE`,
with no network call. `--post` (requiring `SLACK_WEBHOOK_URL`) POSTs the Block
Kit payload to that incoming webhook. `--post` without the env var is a named
error; the command never posts implicitly.

**Rationale:** the only outward-facing action is gated behind an explicit flag
and a user-supplied secret, so the command is safe to run and test without
ever reaching Slack. One webhook is the single, loggable egress point — the
narrow, auditable choice Road also made.

### Two formats: Slack Block Kit (default) and markdown

**Choice:** `--format slack` emits a Block Kit JSON message; `--format
markdown` emits a human-readable summary of the same data. Both team-level.

**Rationale:** Block Kit is the Slack payload; markdown serves a human reading
stdout or a gist (Road produced both). Same data, two renderers — no
divergence in content.

### Block Kit message structure

A header (`DORA + retro — {repo}`), a section with the four DORA metrics and
their bands, a section with the retro signals (stale / long-thread / friction
/ tech-debt / smooth, by PR number), a divider, and a context block naming the
source repo, the window, and the generation time. Issue/PR references render as
plain `#<number>` (no author links). The structure is a small builder function,
not a template engine.

### Compose, don't recompute

**Choice:** `deliver` calls `dora_metrics` and `retro_signals` compute
functions and formats their results; it performs the same comment fetch
`retro` does (hence `--forge`). It adds no new analysis.

## Risks / Trade-offs

- **Accidental egress.** → Egress is impossible without `--post` *and*
  `SLACK_WEBHOOK_URL`; the POST path is unit-tested against a fake transport,
  never a live channel, in this change.
- **Block Kit schema drift.** → Keep to the stable core blocks (header,
  section, divider, context); validate structure in tests; a malformed block
  surfaces as a Slack 400 the user sees on `--post`, not silently.
- **Webhook secret handling.** → Read from the environment only; never logged;
  never written to `--out`. One webhook, one channel.

## Migration Plan

1. `capabilities/scheduled_delivery.py`: `build_blockkit(dora, retro, meta)`,
   `build_markdown(...)`, `post_to_webhook(url, payload)` (httpx).
2. `cli.py`: `deliver` command (fetch comments → compute dora + retro →
   format → write or post).
3. Tests (Block Kit structure, markdown, team-level, `--post` error, POST via
   fake transport, empty window).
4. Docs + CHANGELOG; README scheduling + egress note.
5. Smoke: `deliver --format markdown` and `--format slack` to stdout over a
   cached repo (render only — no `--post`, no live Slack).

Rollback is a revert: read-only except the opt-in POST.

## Open Questions

- Default `--period` for the DORA half (inherit dora's `month` default).
- Whether to include action buttons (link to repo) in the Block Kit — minor;
  start without, add if wanted.
