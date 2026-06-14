## Why

The last piece of `Road_to_el_DORA-do`: turning the metrics + retro signals
into a periodic message a team actually sees. `dora-metrics` and
`retro-signals` produce the content; this change composes them into a Slack
message and delivers it — closing the merge and letting
`Road_to_el_DORA-do` be retired.

Per the agreed shape: a plain **`gitsweeper deliver` command** the user
schedules themselves (cron / a routine) — no CI coupling, portable, works for
any forge. Output goes to **stdout/file by default**; it only reaches Slack
with an explicit `--post` flag and a webhook in the environment. Egress is
opt-in, explicit, and testable without ever posting.

## What Changes

- **New capability `scheduled-delivery`** with a `gitsweeper deliver <repo>`
  command that composes the `dora-metrics` and `retro-signals` results into
  one team-level report and renders it.
- **Two formats:** `--format slack` (default) emits a **Slack Block Kit** JSON
  message; `--format markdown` emits a human-readable summary. Both carry the
  same team-level data (PR numbers, no authors).
- **Egress is opt-in.** By default the payload is written to stdout or
  `--out <file>` — no network. With `--post` and `SLACK_WEBHOOK_URL` set, the
  Block Kit payload is POSTed to that incoming webhook. `--post` without a
  webhook is a clear, named error; the command never posts implicitly.
- **Scheduling is the user's** — documented (cron / the schedule routine), not
  built in. The command is a one-shot; running it on a timer is out of band.
- **Reuses the existing capabilities** — `deliver` calls the `dora_metrics`
  and `retro_signals` compute functions; it adds composition + Block Kit
  formatting + the optional POST, no new analysis.

## Capabilities

### New Capabilities
- `scheduled-delivery`: compose DORA + retro into a Slack Block Kit (or
  markdown) message and deliver it — stdout/file by default, Slack webhook on
  explicit opt-in.

### Modified Capabilities
<!-- none — composes dora-metrics + retro-signals; no change to their specs -->

## Impact

- **Code (Python):** new `capabilities/scheduled_delivery.py` (compose the two
  reports → a Block Kit dict and a markdown string; a `post_to_webhook` using
  `httpx`); a `deliver` command in `cli.py`. Reuses `dora_metrics` +
  `retro_signals`; the comment fetch for retro runs as part of `deliver` (like
  `retro`), so `deliver` takes `--forge`.
- **Tests:** `tests/test_scheduled_delivery.py` — Block Kit structure (valid
  blocks, team-level: no author), markdown rendering, the `--post`-without-
  webhook error, and the POST path against a **fake** httpx transport (no real
  network). Empty-window handling.
- **CLI:** `gitsweeper deliver <repo> [--forge] [--since] [--period] [--format slack|markdown] [--out FILE] [--post]`.
- **Config:** `SLACK_WEBHOOK_URL` documented as the only egress point (one
  webhook, one channel) — set it only when `--post` is used.
- **Docs / CHANGELOG:** README command + a "delivery" note (scheduling is the
  user's job; egress is opt-in); CHANGELOG entry. A note that this supersedes
  `Road_to_el_DORA-do`.
- **Outward-facing safety:** the only external action is the opt-in POST to a
  user-supplied webhook. Nothing is sent without `--post` + `SLACK_WEBHOOK_URL`.

## Follow-on (not this change)

- Retire `Road_to_el_DORA-do` with a "superseded by gitsweeper" README note
  once `deliver` is in use.
