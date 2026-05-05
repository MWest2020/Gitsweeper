# Gitsweeper

A platform for mining and analysing GitHub data. The name is a nod to
Minesweeper: you sweep a repository and surface patterns hidden in its
issue and pull-request history.

**Scale of ambition:**

- v1: GitHub-only, single user, CLI.
- horizon: more data sources, more analyses, optional renderers to
  PDF / markdown / dashboards.

The architecture should leave room for that horizon without building it
today.

## Stack

- **Language:** Python 3.11+
- **Tooling:** [uv](https://docs.astral.sh/uv/) for environments,
  dependencies, and script execution. Never call `pip` directly.
- **HTTP client:** `httpx` for the GitHub REST API.
- **Analysis:** `polars` (preferred over pandas).
- **CLI:** `typer` + `rich`.
- **Storage:** SQLite via the standard-library `sqlite3` module (DB-API
  2.0). No ORM. Queries written in portable SQL only — no SQLite-only
  types or extensions — so a Postgres switch is a day of work, not a
  rewrite.
- **Tests / lint:** `pytest`, `ruff`.
- **Licence:** EUPL-1.2.

## Conventions

- **Boring & auditable wins.** Pick well-understood, battle-tested
  approaches over clever ones. Optimise for readability and
  reviewability. When in doubt, choose the option a future maintainer
  can audit without context.
- **uv-only.** All Python tooling commands go through `uv` (`uv run`,
  `uv add`, `uv sync`). Lockfile is part of the audit trail.
- **Portable SQL.** No `AUTOINCREMENT`, no JSON1 in queries, no
  SQLite-specific functions. Store JSON payloads as `TEXT`, parse in
  Python.
- **Capabilities per use-case, not per layer.** A capability owns a
  user-visible analysis (e.g. `pr-throughput-analysis`). Internal
  building blocks (the GitHub client, the storage layer) are shared
  libraries, not capabilities.
- **Cross-cutting capabilities only when truly cross-cutting.**
  `report-rendering` is a capability because every analysis produces
  output; centralising the renderer contract avoids each use-case
  inventing its own.
- **Multi-tenancy off, but prepared.** Schemas carry a nullable
  `owner_namespace` column from day one. No auth layer, no tenant
  resolution — just the seam.
- **CHANGELOG.md is non-negotiable.** Every session that changes
  observable state gets a dated entry. Keep-a-Changelog format,
  `[Unreleased]` until there is working code worth tagging.

## Repository layout (intended)

```
gitsweeper/
  openspec/             # specs, changes, project.md (this file)
  src/gitsweeper/
    cli/                # typer entrypoints
    capabilities/
      pr_throughput/    # one package per capability
    lib/
      github_client/    # shared: REST, pagination, rate limits
      storage/          # shared: sqlite + portable SQL
      rendering/        # shared: renderer interface + impls
  tests/
  CHANGELOG.md
  pyproject.toml
```

Capabilities depend on libraries; libraries do not depend on
capabilities. Renderers are libraries used by capabilities through the
`report-rendering` interface.

## Architecture decisions

These are the non-trivial choices that shape v1. They live here rather
than in a per-change `design.md` because there is no change yet — this
is the greenfield baseline. Future changes that revisit any of these
decisions get their own change folder with a `design.md`, per
OpenSpec convention.

### Percentiles, not means, for time-to-merge

PR time-to-merge distributions are right-skewed: a handful of stale PRs
drag the mean upward and obscure typical behaviour. Median plus p25 /
p75 / p95 / max gives a faithful picture of both the common case and
the tail without smuggling in a normality assumption that does not
hold.

### Time-to-first-response as a separate metric

Total time-to-merge mixes two very different things: how long the
maintainer takes to engage, and how long the back-and-forth with the
submitter takes afterwards. Reporting first-response separately lets
us tell a maintainer-responsiveness story without conflating it with
submitter follow-up latency. It costs one extra API call per PR
(comments listing), which is why it lives in an opt-in command.

### REST instead of GraphQL for v1

GraphQL would be more efficient per-call, but for the data we need
(PRs, comments) REST is simpler, has no schema to keep in sync, and
its rate-limit model is easier to reason about. Good enough for one
user against one repo at a time. Revisit if we ever hit GraphQL-only
fields or need fewer round-trips at scale.

### SQLite now, Postgres-ready by discipline

A single-user CLI does not justify running Postgres. SQLite is
zero-config, file-based, and ships with Python. The cost is real —
SQLite has its own type quirks and JSON1 extension — so the discipline
is: write only portable SQL, store JSON as `TEXT`, never use
`AUTOINCREMENT`. When multi-user or multi-tenant becomes relevant, the
switch is "swap the connection factory and run migrations", not a
rewrite.

### Capabilities per use-case, not per layer

A layered architecture (`api/`, `services/`, `models/`) optimises for
people who think in layers. Gitsweeper's growth axis is "more
analyses", not "more layers", so we organise by what a user runs.
Each capability evolves independently; shared infrastructure
(`github-client`, `storage`) is an implementation detail consumed by
capabilities, not a peer of them.

### `report-rendering` is a capability, not a library

Output format is the one thing every current and future analysis has
in common. If renderers were library code, each capability would grow
its own `--format` flag and its own table-builder, and adding a PDF
renderer later would mean touching every capability. Lifting it to a
capability lets us define the renderer contract once and add formats
(markdown, PDF, dashboard JSON) without touching analysis code.

### Full-refresh caching, not incremental

A repository's PR history is small enough (low thousands at most for
the Nextcloud target) that re-fetching everything is fine, and it
avoids a class of bugs around "what counts as changed". When the
horizon includes much larger repos we revisit; until then, full
refresh is cheaper to reason about than to optimise.

## Storage schema (sketch)

Portable SQL: no `AUTOINCREMENT`, no JSON1, no SQLite-only types.
Primary keys are explicit `INTEGER` (rowid) or natural keys. JSON
payloads are stored as `TEXT` and parsed in Python. `owner_namespace`
is the nullable seam for future multi-tenancy.

```sql
CREATE TABLE repositories (
    id              INTEGER PRIMARY KEY,
    owner           TEXT    NOT NULL,
    name            TEXT    NOT NULL,
    owner_namespace TEXT,                       -- nullable: multi-tenancy seam
    fetched_at      TEXT    NOT NULL,           -- ISO 8601 UTC
    UNIQUE (owner, name, owner_namespace)
);

CREATE TABLE pull_requests (
    id           INTEGER PRIMARY KEY,
    repo_id      INTEGER NOT NULL REFERENCES repositories(id),
    number       INTEGER NOT NULL,
    state        TEXT    NOT NULL,              -- 'open' | 'closed'
    created_at   TEXT    NOT NULL,
    merged_at    TEXT,                          -- nullable: not all closed PRs merge
    closed_at    TEXT,
    author       TEXT    NOT NULL,
    raw_payload  TEXT    NOT NULL,              -- full GitHub JSON, stored as text
    fetched_at   TEXT    NOT NULL,
    UNIQUE (repo_id, number)
);

CREATE TABLE pr_first_responses (
    pr_id             INTEGER PRIMARY KEY REFERENCES pull_requests(id),
    first_response_at TEXT,                     -- nullable: PR may have no non-author response
    responder         TEXT,                     -- nullable for the same reason
    fetched_at        TEXT    NOT NULL
);
```

This is a sketch, not a migration. Real migrations will live alongside
the storage library and be the canonical source.

## Out of scope for v1

Explicit non-goals, listed so they do not creep in:

- More than one use-case capability. `issue-response-analysis`,
  `release-cadence`, etc. come later.
- Renderers beyond CLI table and JSON. No PDF, markdown, dashboards.
- Multi-repo aggregation in a single run.
- Incremental cache updates. Full refresh is good enough at this scale.
- Non-GitHub data sources (GitLab, Forgejo, NPM registry, etc.).
- Multi-tenancy, auth, user management.
- Scheduled runs, alerts, notifications.
- Web UI.
