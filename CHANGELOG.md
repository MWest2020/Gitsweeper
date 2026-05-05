# Changelog

All notable changes to Gitsweeper are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning will follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once there is working code worth tagging.

## [Unreleased]

### Added

- `2026-05-05` — OpenSpec baseline initialised. Project structure now
  includes `openspec/` (created via `openspec init --tools claude`) with
  the project description, the v1 stack and conventions, and the
  baseline architecture decisions captured in `openspec/project.md`.
- `2026-05-05` — Initial capability specs:
  - `pr-throughput-analysis` — fetch + persist GitHub pull requests,
    compute time-to-merge percentiles (median, p25, p75, p95, max)
    over merged PRs, support `--since` filtering, and provide an
    opt-in time-to-first-response analysis. Validated in strict mode.
  - `report-rendering` — pluggable renderer interface; CLI table
    (default) and JSON renderers shipped in v1; renderers contain no
    analysis logic. Validated in strict mode.
- `2026-05-05` — Claude Code integration via `.claude/skills/` and
  `.claude/commands/opsx/` (committed) so OpenSpec slash commands work
  in this project. `.claude/settings.local.json` is local-only and
  excluded via `.gitignore`.
- `2026-05-05` — `CHANGELOG.md` and `.gitignore` added.

### Notes

- No application code yet. Specs only — implementation lands as
  follow-up changes, each going through the standard OpenSpec change
  workflow (`openspec/changes/<change-name>/` with proposal, design
  if non-trivial, and tasks).
