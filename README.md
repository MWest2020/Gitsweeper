# Gitsweeper

Mine and analyse GitHub data — sweep a repo, surface patterns. v1
focuses on pull-request throughput: how long PRs take to merge, how
that latency is distributed, and how quickly maintainers first engage.

Specs live under [`openspec/`](./openspec/). The architecture, stack,
and non-trivial design choices are documented in
[`openspec/project.md`](./openspec/project.md).

## Quick start

```bash
# Install and lock dependencies (uv-managed).
uv sync

# Optional but strongly recommended: 60 unauthenticated requests/hour
# is not enough for most real repos.
export GITHUB_TOKEN=ghp_yourtokenhere

# Fetch the full PR history for a repository (cached locally).
uv run gitsweeper fetch nextcloud/app-certificate-requests

# Time-to-merge percentiles over the cache.
uv run gitsweeper throughput nextcloud/app-certificate-requests
uv run gitsweeper throughput nextcloud/app-certificate-requests --since 2025-01-01
uv run gitsweeper throughput nextcloud/app-certificate-requests --since 2025-01-01 --json

# Time-to-first-response (one extra API call per uncached PR; opt-in).
uv run gitsweeper first-response nextcloud/app-certificate-requests --since 2025-01-01
```

The local cache lives at `$XDG_STATE_HOME/gitsweeper/gitsweeper.sqlite`
(or `~/.local/state/gitsweeper/gitsweeper.sqlite` on systems without
XDG). Override with `--db-path`.

## Capabilities (v1)

- [`pr-throughput-analysis`](./openspec/specs/pr-throughput-analysis/spec.md)
  — fetch + persist, time-to-merge percentiles (median, p25, p75, p95,
  max), `--since` filtering, opt-in time-to-first-response.
- [`report-rendering`](./openspec/specs/report-rendering/spec.md)
  — pluggable renderer interface; CLI table (default) and JSON in v1.

## Development

```bash
uv sync
uv run pytest                      # 34 tests; should be green
uv run ruff check .
openspec validate --specs --strict
```

## License

EUPL-1.2 — see `pyproject.toml`.
