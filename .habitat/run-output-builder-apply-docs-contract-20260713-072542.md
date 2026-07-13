# Habitat builder — apply-docs-contract

_run_id builder-apply-docs-contract-20260713-072542 · verdict ok · 2026-07-13T07:28:45Z_

---

Committed. Everything is done except the actual PR creation (task 4.1), which I can't perform — `gh` is not installed and pushing/PRs are the harness's job (task 1.1). Here's the report.

## Run report — `apply-docs-contract`

**Branch:** `habitat/builder/apply-docs-contract` · **Commit:** `c7d6775` `docs: apply handbook docs contract`

### What I did
- **`docs/reference/mcp.md`, `docs/reference/reconcile.md`** — migrated verbatim from `docs/mcp.md` / `docs/reconcile.md`, with front matter `status: draft` + `last_reviewed: 2026-07-13` (migrated, no content review → draft per contract). Internal cross-links between the two still resolve (both now co-located in `reference/`).
- **`docs/mcp.md`, `docs/reconcile.md`** — replaced with deprecated stubs pointing to the new locations (README and possible external links still target these paths). Front matter `status: deprecated`.
- **`docs/index.md`** — new: what the project is, status, link to `../README.md` (does not replace it), and links to the present sections.
- **`LICENSE`** — canonical EUPL-1.2 text (project policy; `pyproject.toml` already declares EUPL-1.2). Fetched from the SPDX license-list source.
- **`.mcp.json`** — already present with the seed template; `TODO-change-3` placeholder left untouched. No change needed.

### Self-check (task 3.1) — all pass
- Only the allowed `reference/` subfolder carries markdown; no empty dirs; stubs sit at `docs/` root as the contract requires.
- Every page has YAML front matter (`status` + `last_reviewed`); no `owner` field.
- One language: English throughout. All 8 relative links resolve to real files.

### Tasks
1.1–3.1 checked off. **4.1 not done:** `gh` is unavailable in this environment and pushing/PR-opening belong to the habitat harness (task 1.1), so I stopped short of opening the PR. I did **not** merge.

### Ready-to-use PR
**Title:** `docs: apply handbook docs contract`

**Body:**
```markdown
Applies the handbook docs contract (Westmarch add-docs-contract) to Gitsweeper.

Contract points applied:
- [x] docs/ layout per contract (index.md + reference/); empty dirs omitted
- [x] Minimum viable: index.md + one reference page (two present)
- [x] YAML front matter on every page (status + last_reviewed); no owner field
- [x] Migrated-without-review pages: status: draft, last_reviewed = 2026-07-13
- [x] One language per repo: English
- [x] README kept; docs/index.md links to it, does not replace it
- [x] Loose docs migrated; deprecated stubs left at old paths for external links
- [x] docs/{mcp,reconcile}.md -> reference/; stubs left behind
- [x] docs/index.md new, derived from README
- [x] LICENSE: EUPL-1.2 added (project policy)
- [x] .mcp.json present per seed template; url placeholder TODO-change-3 kept

Non-goals respected: no merge, no changes to CLAUDE.md / .claude/agents/ / CI,
no other scope. Mark merges.
```

One out-of-scope observation (not touched): `README.md` line 112 says the MCP server advertises "nine tools" while `docs/reference/mcp.md` documents five — a pre-existing inconsistency outside this change.
