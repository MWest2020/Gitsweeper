# Habitat reviewer — apply-docs-contract

_run_id reviewer-apply-docs-contract-20260713-072850 · verdict ok · 2026-07-13T07:30:37Z_

---

I've completed the review. Here's my verdict.

---

# Reviewer verdict: **PASS** ✅

Change under review: `apply-docs-contract` — branch `habitat/reviewer/apply-docs-contract`, builder commit `08b104f` / `c7d6775`.
Note: no root `CLAUDE.md` exists in this repo, so check #3 was judged against the file-path rules directly.

## 1. Scope ✅
The diff implements the change's tasks and nothing product-facing beyond them:
- `docs/reference/mcp.md`, `docs/reference/reconcile.md` — migrated pages (task 2.1)
- `docs/mcp.md`, `docs/reconcile.md` — reduced to "Moved" stubs at the old locations (task 2.1, explicitly required by proposal.md:44 / :38-39)
- `docs/index.md` — new, one paragraph + README link + section links (task 2.3)
- `LICENSE` — EUPL-1.2 (proposal.md:46)
- `.mcp.json` — already seeded on `main` with the correct template + `TODO-change-3` placeholder, so task 2.4 is satisfied
- `tasks.md` — boxes 1.1–3.1 checked; 4.1 (open PR) correctly left unchecked since Mark merges

`run-report.json` and `.habitat/*` are harness-generated bookkeeping artifacts, not builder content — not a scope violation.

## 2. Contract (Diátaxis-light) ✅
- Front matter present on **every** page with both `status` and `last_reviewed: 2026-07-13`: index=`draft`, reference/*=`draft` (migrated-without-review, per proposal.md:34-35), stubs=`deprecated`.
- **No `owner` field** anywhere (the sole `owner` grep hit is prose — `owner/name` in a table cell at `docs/reference/reconcile.md:43`).
- Markdown lives in `index.md` + `reference/`; no empty dirs; `how-to/`/`explanation/` correctly omitted.
- `docs/index.md:11` links to `../README.md` rather than replacing it.
- One language (English) throughout `docs/`.

**Accepted deviation (noted, not a fail):** check #2's literal wording says "only `index.md` + `how-to/` + `reference/` + `explanation/` carry markdown," yet top-level stubs `docs/mcp.md` and `docs/reconcile.md` carry markdown. This is a deliberate, documented requirement of the change itself (proposal.md:39, :44 — "stub met verwijzing achterlaten op de oude plek"), the stubs are minimal pointers marked `status: deprecated`, and preserving old URLs for external links is the explicit intent. The change's explicit instruction governs here.

## 3. Cage intact ✅
No `CLAUDE.md`, `.claude/agents/`, or CI config in the diff. (The earlier grep "match" on `reconcile.md` was a false positive — the substring "ci" inside "reconcile".)

## 4. No secrets ✅
Only obvious placeholders (`bb_xxx…`, `$(gh auth token)`) and env-var *names* in documentation. No real tokens, keys, or secret-bearing URLs.

---

Read-only review — no files changed. Task 4.1 (open PR titled `docs: apply handbook docs contract`, then stop for Mark's merge) remains for the builder/harness; nothing blocks it from the reviewer's side.
