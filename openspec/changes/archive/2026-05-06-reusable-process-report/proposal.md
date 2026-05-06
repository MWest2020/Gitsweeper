## Why

The first real-world use of gitsweeper produced a report on
`nextcloud/app-certificate-requests` for a conversation with Nextcloud
about Conduction's certificate-request process. Half of that report
came out of one-off Python scripts: filtering pull requests by author,
fetching close-actors via the issue-events API to distinguish
self-pulled from maintainer-closed PRs, computing day-of-week and
hour-of-day patterns, and assembling everything into a markdown
document. None of that is reproducible without manual scripting.

We want to do this again — for other repositories, for other authors,
on a future date — without repeating the manual work.

## What Changes

- **Modified**: `pr-throughput-analysis` gains an `--author` filter so
  the existing throughput and first-response analyses can produce a
  per-submitter slice without dropping out to ad-hoc SQL.
- **New**: `pr-classification` capability fetches close-event actors
  for closed-without-merge pull requests and persists them, so
  "self-pulled by submitter" can be cleanly separated from "closed by
  maintainer". Without this distinction, response-rate numbers are
  systematically wrong for any repository where submitters retract
  their own duplicates.
- **New**: `pr-process-report` capability orchestrates a single full
  run — fetch, throughput, first-response, classification, temporal
  patterns — and emits a markdown document suitable to share with a
  process owner. It uses `report-rendering` for the structured pieces
  and adds a markdown renderer to the registry.

No breaking changes; existing commands keep working.

## Capabilities

### New Capabilities

- `pr-classification`: enrich closed-without-merge pull requests with
  the actor that closed them, classify each as self-pulled or
  maintainer-closed, expose those counts as a structured analysis
  result.
- `pr-process-report`: produce a single, shareable markdown report for
  a repository (and optionally a single submitter) covering volume,
  time-to-merge, time-to-first-response, classification, and temporal
  (day-of-week / hour-of-day) submission and response patterns.

### Modified Capabilities

- `pr-throughput-analysis`: adds an `--author <login>` filter so
  `compute_throughput` and `compute_first_response` can be scoped to a
  single submitter, plus a temporal-patterns analysis (day-of-week and
  hour-of-day distributions for submissions and first-responses) so
  the queue-depth story can be told without ad-hoc scripts.
- `report-rendering`: adds a markdown renderer to the registry so
  `pr-process-report` can serialise its structured output via the
  existing renderer interface, not bypass it.

## Impact

- **Code**: new modules `capabilities/pr_classification.py` and
  `capabilities/process_report.py`; extensions to
  `capabilities/pr_throughput.py`, `lib/storage.py`,
  `lib/github_client.py`, `lib/rendering.py`, and `cli.py`.
- **Schema**: one new SQLite table, `pr_close_actors`, with the
  nullable `owner_namespace` seam in scope by virtue of joining
  through `pull_requests`.
- **CLI surface**: existing `throughput` and `first-response` gain
  `--author`. New commands `classify` and `report`.
- **API budget**: `classify` costs one extra GitHub API call per
  closed-without-merge PR (cached after first run). For the Nextcloud
  repo this is 193 calls; trivial under an authenticated 5000/h
  budget.
- **Out of scope** (still): non-GitHub data sources, multi-repo
  aggregation in one run, PDF / dashboard renderers, multi-tenancy.
