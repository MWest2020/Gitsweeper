## 1. Composition + formatting

- [ ] 1.1 `capabilities/scheduled_delivery.py`: `build_blockkit(dora_report, retro_report, meta)` → a Slack Block Kit dict (header, DORA section with bands, retro-signals section by PR number, divider, context block with repo/window/generated-at). PR refs render as plain `#<n>` — no author links
- [ ] 1.2 `build_markdown(dora_report, retro_report, meta)` → a human-readable summary of the same data
- [ ] 1.3 `post_to_webhook(url, payload)` using `httpx` (POST JSON; raise a clear error on non-2xx)
- [ ] 1.4 Empty-window handling: coherent "no data / no signals" message that is still a valid Block Kit / markdown payload
- [ ] 1.5 Team-level: no author/login/`@`-mention anywhere in either format

## 2. CLI

- [ ] 2.1 `gitsweeper deliver <repo>` in `cli.py`: `--forge`, `--since`, `--period {week,month}`, `--format {slack,markdown}` (default slack), `--out FILE`, `--post`, `--db-path`. NO `--author`
- [ ] 2.2 Flow: fetch+cache comments (like `retro`) → compute `dora_metrics` + `retro_signals` → format → write to stdout/`--out`; with `--post`, POST to `SLACK_WEBHOOK_URL`
- [ ] 2.3 `--post` without `SLACK_WEBHOOK_URL` → named non-zero error, no network call. Webhook read from env only; never written to output/logs

## 3. Tests

- [ ] 3.1 `tests/test_scheduled_delivery.py`: Block Kit structure valid (expected block types); markdown rendering; both formats team-level (assert no author/login in serialized output)
- [ ] 3.2 `--post` path against a FAKE httpx transport (assert it POSTs the payload to the configured URL) — no real network
- [ ] 3.3 `--post` without webhook → error, no call; webhook never appears in rendered/`--out` output
- [ ] 3.4 Empty-window message renders as valid payload

## 4. Docs

- [ ] 4.1 `README.md`: add `deliver` to the command table + a "delivery" note — scheduling is the user's job (cron / routine), egress is opt-in (`--post` + `SLACK_WEBHOOK_URL`), one webhook = one channel
- [ ] 4.2 `CHANGELOG.md`: dated entry; note this supersedes the `Road_to_el_DORA-do` Actions workflow

## 5. Verify

- [ ] 5.1 `uv run ruff check .` clean; `uv run pytest` green
- [ ] 5.2 Smoke (render only, NO `--post`, no live Slack): over a cached repo, `deliver --format markdown` and `deliver --format slack` to stdout produce a coherent message; confirm no author and no webhook in output
