# Gitsweeper

Mine and analyse GitHub data — sweep a repo, surface patterns. The
v1 focus is pull-request process: how long PRs take to merge, how
that latency is distributed, how quickly maintainers first engage,
and which closed-without-merge PRs were silently retracted by the
submitter versus closed by a maintainer.

Specs live under [`openspec/`](./openspec/). The architecture, stack,
and non-trivial design choices are documented in
[`openspec/project.md`](./openspec/project.md).

## Quick start

```bash
# Install and lock dependencies (uv-managed).
uv sync

# Strongly recommended: an authenticated 5000/h budget instead of
# the 60/h unauthenticated one.
export GITHUB_TOKEN=$(gh auth token)   # or any PAT with read:repo

# Fetch the full PR history into the local cache.
uv run gitsweeper fetch nextcloud/app-certificate-requests

# Aggregate analyses against the cache.
uv run gitsweeper throughput nextcloud/app-certificate-requests
uv run gitsweeper first-response nextcloud/app-certificate-requests
uv run gitsweeper classify nextcloud/app-certificate-requests
uv run gitsweeper patterns nextcloud/app-certificate-requests

# One-shot composed markdown report (writes the file to docs/examples/
# by convention; the directory is gitignored so reports never get
# committed by accident).
uv run gitsweeper report nextcloud/app-certificate-requests \
    --refresh \
    --out docs/examples/nextcloud-csr-report-$(date -u +%Y-%m-%d).md

# Per-author slice (case-insensitive on the GitHub login).
uv run gitsweeper report nextcloud/app-certificate-requests \
    --author MWest2020 \
    --out docs/examples/nextcloud-csr-mwest2020-$(date -u +%Y-%m-%d).md
```

### Forges

Gitsweeper acquires data through a forge-provider seam (`lib/forge`).
**GitHub** (the default), **Forgejo/Gitea/Codeberg**, and **GitLab** are
supported. A bare `owner/repo` resolves to GitHub exactly as it always has,
so no existing command changes.

Select a forge in one of three ways:

- explicitly: `--forge forgejo`, `--forge gitlab` (or `--forge github`);
- by host: a `codeberg.org` URL is detected as Forgejo, a `gitlab.com` URL
  as GitLab, automatically;
- self-hosted: set `GITSWEEPER_FORGEJO_URL` / `GITSWEEPER_GITLAB_URL` to your
  instance's base URL (e.g. `https://git.example.org`) and a URL on that host
  is detected accordingly.

```bash
export GITHUB_TOKEN=$(gh auth token)        # GitHub: read:repo PAT
export FORGEJO_TOKEN=...                     # Forgejo/Codeberg/Gitea token
export GITSWEEPER_FORGEJO_URL=https://...    # self-hosted base URL (defaults to Codeberg)
export GITLAB_TOKEN=...                      # GitLab personal access token
export GITSWEEPER_GITLAB_URL=https://...     # self-hosted base URL (defaults to gitlab.com)

gitsweeper fetch --forge forgejo forgejo/forgejo
gitsweeper fetch --forge gitlab gitlab-org/gitlab-runner
```

Forgejo and GitLab reads can run unauthenticated against public repositories
on instances that permit it, with a warn-once notice; set `FORGEJO_TOKEN` /
`GITLAB_TOKEN` for the full rate-limit budget (GitLab also requires a token
for some sub-resources, such as a merge request's notes and state events,
even on public projects).

### Where things live on disk

| Path | Status | Contents |
|---|---|---|
| `cache/*.sqlite` | gitignored | Per-repo SQLite cache. Pass `--db-path cache/<repo>.sqlite` to keep them tidy. The default if `--db-path` is omitted is `$XDG_STATE_HOME/gitsweeper/gitsweeper.sqlite`. |
| `docs/examples/*.md` | gitignored | Generated reports. Convention is `<owner>-<repo>-[<author>-]<date>.md`. |
| `openspec/specs/` | tracked | Capability specs. Authoritative for behaviour. |
| `openspec/changes/archive/` | tracked | Historical change proposals (audit trail). |

Both `cache/` and `docs/examples/` are deliberately ignored — they
are run-specific artefacts that drift the moment a new snapshot is
taken. Keep them locally for sharing; do not commit them.

## Commands

| Command | What it does | API cost |
|---|---|---|
| `fetch <repo>` | Download all pull requests (paginated) into the cache. | ~`ceil(n / 100)` calls. |
| `throughput <repo> [--since] [--author] [--json]` | Time-to-merge percentiles over the cache. | 0 (cache only). |
| `first-response <repo> [--since] [--author] [--json]` | First-non-author-comment percentiles; lazily fetches comments for any uncached PR. | ~1 per uncached PR. |
| `classify <repo> [--author] [--json]` | Self-pulled vs maintainer-closed for closed-without-merge PRs; uses the issue-events endpoint to fill the data the pulls endpoint omits. | ~1 per uncached closed-unmerged PR. |
| `patterns <repo> [--since] [--author] [--json]` | Day-of-week and hour-of-day distributions for submissions and responses. | 0 (cache only). |
| `report <repo> [--author] [--since] [--refresh] [--out PATH]` | Compose every section above into a single markdown document. `--refresh` runs fetch + first-response + classify before composing. | Sum of the above when `--refresh`; 0 otherwise. |

## Manager-MCP

A small MCP server exposes Gitsweeper's PR analyses *and* a Billbird
manager-view (hours, plan-vs-actual) over stdio. Point Claude Desktop
(or any MCP-aware AI client) at `gitsweeper mcp` and a manager can
ask plan-vs-actual or PR-throughput questions in natural language.
See [`docs/mcp.md`](./docs/mcp.md) for the configuration snippet,
the nine tools the server advertises, the read-only contract, and the
required environment.

```bash
# Run the server directly (typically Claude Desktop spawns this for you).
uv run gitsweeper mcp
```

## Capabilities

- [`pr-throughput-analysis`](./openspec/specs/pr-throughput-analysis/spec.md)
  — fetch + persist, time-to-merge percentiles, `--since` and
  `--author` filtering, opt-in time-to-first-response, day/hour
  patterns.
- [`pr-classification`](./openspec/specs/pr-classification/spec.md)
  — close-event-actor enrichment, self-pulled vs maintainer-closed
  classification.
- [`pr-process-report`](./openspec/specs/pr-process-report/spec.md)
  — orchestrates the others into a single shareable markdown report.
- [`report-rendering`](./openspec/specs/report-rendering/spec.md)
  — pluggable renderer interface; CLI table, JSON, and markdown
  renderers.

## Development

```bash
uv sync
uv run pytest                          # 60 tests; should be green
uv run ruff check .
openspec validate --all --strict
```

## License

EUPL-1.2 — see `pyproject.toml`.
