# scheduled-delivery Specification

## Purpose
TBD - created by archiving change scheduled-delivery. Update Purpose after archive.
## Requirements
### Requirement: Compose DORA and retro into one team-level message

The system SHALL provide a `gitsweeper deliver <repo>` command that composes
the `dora-metrics` and `retro-signals` results for a repository into a single
team-level message, reusing those capabilities rather than recomputing.

#### Scenario: Both halves appear in the message

- **GIVEN** a repository with cached PRs (and comments for the retro half)
- **WHEN** the user runs `gitsweeper deliver <repo>`
- **THEN** the message contains the four DORA metrics with their bands and the
  retro signals (stale / long-thread / friction / tech-debt / smooth)
- **AND** every reference is a PR number — no author login, name, or
  `@`-mention appears

### Requirement: Render as Slack Block Kit or markdown

The system SHALL render the message as a Slack Block Kit JSON payload by
default (`--format slack`), or as a human-readable markdown summary
(`--format markdown`), carrying the same team-level data either way.

#### Scenario: Block Kit is the default format

- **WHEN** the user runs `deliver` without `--format`
- **THEN** the output is a valid Slack Block Kit message (header, section(s),
  context block) as JSON

#### Scenario: Markdown alternative

- **WHEN** the user runs `deliver --format markdown`
- **THEN** the output is a human-readable markdown summary of the same data

### Requirement: Egress is opt-in and explicit

The system SHALL write the rendered payload to stdout or `--out <file>` with no
network call by default, and SHALL POST to a Slack incoming webhook only when
`--post` is given and `SLACK_WEBHOOK_URL` is set. No message is sent
implicitly.

#### Scenario: Default run makes no network call

- **WHEN** the user runs `deliver <repo>` without `--post`
- **THEN** the payload is written to stdout (or `--out`)
- **AND** no request is made to any webhook

#### Scenario: Posting requires the flag and the webhook

- **GIVEN** `--post` is given and `SLACK_WEBHOOK_URL` is set
- **WHEN** `deliver` runs
- **THEN** the Block Kit payload is POSTed to that webhook URL

#### Scenario: --post without a webhook is a named error

- **GIVEN** `--post` is given but `SLACK_WEBHOOK_URL` is not set
- **WHEN** `deliver` runs
- **THEN** the command exits non-zero with an error naming the missing
  `SLACK_WEBHOOK_URL`
- **AND** makes no network call

### Requirement: The webhook is the single egress point and is never disclosed

The system SHALL treat `SLACK_WEBHOOK_URL` as the only external egress, read it
from the environment only, and never write it to stdout, `--out`, or logs.

#### Scenario: Webhook is not leaked into output

- **WHEN** `deliver` renders or writes the payload
- **THEN** the webhook URL does not appear in the rendered message, the
  `--out` file, or any log line

### Requirement: Scheduling is external to the command

The system SHALL implement `deliver` as a single-shot command and SHALL NOT
embed a scheduler; periodic execution is left to the user's own scheduling
(documented).

#### Scenario: One run per invocation

- **WHEN** the user runs `deliver`
- **THEN** it composes, delivers once, and exits
- **AND** does not spawn a timer, daemon, or background loop

### Requirement: Empty window is delivered explicitly

The system SHALL produce a coherent message even when the window has no merged
PRs or no signals, stating the emptiness rather than erroring or emitting a
malformed payload.

#### Scenario: Empty window

- **GIVEN** a window with no merged PRs and no retro signals
- **WHEN** `deliver` runs
- **THEN** the message renders with explicit "no data / no signals" content and
  remains a valid Block Kit (or markdown) payload

