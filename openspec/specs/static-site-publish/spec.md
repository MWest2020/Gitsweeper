# static-site-publish Specification

## Purpose
TBD - created by archiving change static-site-publish. Update Purpose after archive.
## Requirements
### Requirement: Produce a deployable HTML+SVG bundle from the cache

The system SHALL accept a target output directory and write a
self-contained static site containing an index page, per-repo
pages, embedded SVG charts, and the underlying JSON data files
that backed each rendered view, so a downstream operator can host
the bundle (`python -m http.server`, GitHub Pages, S3, etc.) or
inspect it offline.

#### Scenario: Index page lists every repo in scope

- **GIVEN** the cache contains pull requests for multiple
  repositories and the user runs `gitsweeper publish --out
  docs/examples/dashboard/`
- **WHEN** the command completes
- **THEN** `docs/examples/dashboard/index.html` exists
- **AND** the index contains one row per repository in scope,
  with headline KPIs (latest-period values for
  median-time-to-merge, response-rate, volume) and a count of
  active regression alerts on that repo

#### Scenario: Per-repo pages are present and linkable

- **WHEN** the publish command completes for a repo `owner/name`
- **THEN** `docs/examples/dashboard/repo/owner-name.html` exists
- **AND** `index.html` links to that page using a relative URL

#### Scenario: JSON data files accompany the rendered views

- **WHEN** the publish command completes
- **THEN** `docs/examples/dashboard/data/timeseries.json` and
  `docs/examples/dashboard/data/alerts.json` exist
- **AND** their contents are exactly the JSON the corresponding
  capabilities (`kpi-timeseries`, `regression-monitoring`)
  produce, so a downstream consumer can ingest the same bytes
  that backed the page

### Requirement: Charts are pre-rendered SVG, no JS

The system SHALL embed all charts as SVG produced at publish time
— never as JavaScript-driven canvas, dynamic libraries, or remote
asset references. This keeps the bundle viewable offline and
auditable.

#### Scenario: Charts render with browser JS disabled

- **GIVEN** a published bundle inspected in a browser with
  JavaScript disabled
- **WHEN** any page is loaded
- **THEN** every chart on the page is visible
- **AND** the page makes no network requests for chart-rendering
  libraries

#### Scenario: Bundle has no remote references

- **WHEN** the published bundle is grepped for `<script` tags or
  network-loaded URLs in `<link>` / `<img>` / `<iframe>` elements
- **THEN** no such elements reference an external host
- **AND** any styling and script that does exist is inlined or
  stored in `assets/`

### Requirement: Bundle is reproducible from cache alone

The system SHALL produce the same bundle (modulo timestamps shown
on the page) for the same cache state and same flags, so a
contributor can re-run the publish command and verify the result
without consulting external state.

#### Scenario: No GitHub API calls during publish

- **GIVEN** a populated cache
- **WHEN** `gitsweeper publish` runs
- **THEN** zero GitHub API requests are issued
- **AND** the published bundle reflects only what is in the cache
  (the operator runs `fetch` / `first-response` / `classify`
  beforehand if they want fresher data)

#### Scenario: Empty cache produces a clear error, not a half-bundle

- **GIVEN** the cache contains no pull requests for the requested
  scope
- **WHEN** the publish command runs
- **THEN** the command exits with a non-zero status and a clear
  message
- **AND** no partial bundle is left in the output directory

### Requirement: Bundle scope is configurable

The system SHALL accept `--repos owner/repo` (repeatable),
`--since YYYY-MM-DD`, `--baseline <n>`, and `--threshold <s>`
options that flow through to the underlying analyses, so the
operator can tune the bundle to a portfolio slice and an alert
sensitivity that match their domain.

#### Scenario: --repos restricts the portfolio shown

- **GIVEN** the user passes `--repos owner/a owner/b`
- **WHEN** the publish command runs
- **THEN** the index page lists only `owner/a` and `owner/b`
- **AND** only their per-repo pages are written

#### Scenario: --baseline and --threshold flow into the alerts

- **GIVEN** the user passes `--baseline 4 --threshold 1.5`
- **WHEN** the publish command runs
- **THEN** the alerts section uses a 4-period trailing baseline
  and a 1.5σ threshold
- **AND** the metadata block on the index page records both
  values so the bundle is interpretable in isolation

