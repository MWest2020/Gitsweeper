# pr-classification Specification

## Purpose
TBD - created by archiving change reusable-process-report. Update Purpose after archive.
## Requirements
### Requirement: Enrich closed-without-merge pull requests with the close-event actor

The system SHALL, on demand, fetch the GitHub issue-events for each
pull request that is closed without being merged and persist the
login of the actor who fired the most recent `closed` event.

#### Scenario: Enrichment is incremental and cached

- **GIVEN** the close-actor for a particular pull request has
  already been fetched and persisted
- **WHEN** the user runs the classification command again
- **THEN** that pull request is not re-fetched
- **AND** zero GitHub API requests are issued for it

#### Scenario: Enrichment uses the issue-events endpoint, not the pull-request endpoint

- **GIVEN** the GitHub `pulls` list endpoint omits the `closed_by`
  field for many pull requests, but the issue-events endpoint
  records every state-change with its actor
- **WHEN** the system enriches a closed-without-merge pull request
- **THEN** it queries
  `GET /repos/{owner}/{repo}/issues/{number}/events`
- **AND** uses the actor of the most recent event whose `event` is
  `closed`

#### Scenario: Pull requests not closed-without-merge are skipped

- **GIVEN** the pull request is either still open or merged
- **WHEN** classification runs
- **THEN** no events request is issued for that pull request

#### Scenario: Events response contains no closed event

- **GIVEN** the events response is empty or contains no event with
  `event == "closed"` (an edge case)
- **WHEN** the system processes that response
- **THEN** the actor is recorded as null
- **AND** the pull request is classified as "unknown" rather than
  treated as either self-pulled or maintainer-closed

### Requirement: Classify each closed-without-merge PR as self-pulled or maintainer-closed

The system SHALL, given the close-actor for a pull request,
classify the pull request as **self-pulled** when the close-actor
equals the pull-request author and **maintainer-closed** otherwise,
treating a null close-actor as **unknown**.

#### Scenario: Submitter closes their own duplicate

- **GIVEN** a pull request authored by `alice` whose close-event
  actor is also `alice`
- **WHEN** classification runs
- **THEN** the pull request is classified as self-pulled

#### Scenario: Maintainer closes a duplicate or out-of-scope PR

- **GIVEN** a pull request authored by `alice` whose close-event
  actor is `bob` (a different login)
- **WHEN** classification runs
- **THEN** the pull request is classified as maintainer-closed

#### Scenario: Self-pulled pull requests are excluded from response-rate denominators

- **GIVEN** a structured analysis result that compares "PRs that
  needed a maintainer decision" against "PRs that received one"
- **WHEN** the result is computed using classification data
- **THEN** self-pulled pull requests are excluded from the
  denominator
- **AND** the metadata records both the raw counts and the adjusted
  counts so a reader can see the effect of the adjustment

### Requirement: Expose classification counts as a structured analysis result

The system SHALL produce an `AnalysisResult` that breaks down the
closed-without-merge pull-request population by classification
category (self-pulled, maintainer-closed, unknown), suitable for
rendering through the `report-rendering` capability.

#### Scenario: Renderable classification result

- **WHEN** classification has been run for a repository and the user
  invokes the classification analysis
- **THEN** the result contains the count of self-pulled, the count
  of maintainer-closed, and the count of unknown pull requests
- **AND** the result is consumed via the `report-rendering`
  capability for output (no direct printing in the capability)

