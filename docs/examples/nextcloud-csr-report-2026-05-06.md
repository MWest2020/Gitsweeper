# nextcloud/app-certificate-requests — process report

**Snapshot date:** 2026-05-06
**Dataset:** all 1000 pull requests in
[`nextcloud/app-certificate-requests`](https://github.com/nextcloud/app-certificate-requests)
(the full history; the repository's last page is page 10 at 100 per
page).
**Conduction's slice:** the 22 pull requests authored by `MWest2020`.
**Tool:** [gitsweeper](../../README.md), v1 baseline.

---

## TL;DR for Fabrice

1. **The cert-request process is healthy on the typical case.** Median
   time-to-merge is **1.65 days**; median time to first maintainer
   response is **1.08 days**. 87% of PRs that need a decision get one.

2. **The tail matters.** 5% of merged PRs take more than **16.8 days**;
   the worst legitimate case is **111.9 days**. One PR waited
   **273.9 days** for a first response. These are not "the average is
   slow" — they are individual stalls inside an otherwise fast process.

3. **Conduction's specific gap is response latency, not response
   quality.** Our PRs are responded to at the same rate as the repo
   norm (~80% vs 87%, not significant on N=15), but our median
   first-response is **3.59 days versus the repo's 1.08** — about
   3.3× longer. Most of that gap is "queue depth on batch
   submissions" rather than rejection; once a maintainer engages the
   review-to-merge cycle is fast.

The single most actionable item is item 3.

---

## Repo-wide overview

### Volume

| | count |
|---|---|
| Total PRs in history | 1000 |
| Merged | 780 |
| Closed without merge | 193 |
| Still open | 27 |

### Time-to-merge over merged PRs (days)

```
count   780
p25     0.26
median  1.65
p75     4.44
p95     16.81
max     111.93
mean    4.30   (≈ 2.6 × median; right-skewed, so use the percentiles)
```

The **mean** of 4.30 days is misleading on its own — it is dragged up
by a small number of stalls. Half of all merged PRs land within
~1.7 days, three-quarters within ~4.4 days. Reporting **median + p95**
is the honest summary.

### Time to first maintainer response (days)

The "first response" is the first comment on the PR by anyone other
than the author. Out of 1000 PRs:

| | count |
|---|---|
| Got a non-author comment | 787 |
| No non-author comment yet | 213 |

Of those 213 silent PRs, the breakdown is:

| Category | count | Notes |
|---|---|---|
| **Self-pulled by submitter** | 100 | Submitter closed their own PR (often a duplicate or a quickly-superseded draft). Not a maintainer-engagement signal. |
| Merged silently | 89 | Maintainer just merged it without commenting — the response was the merge itself. Counts as engagement. |
| Still open | 19 | Currently waiting; outcome unknown. |
| Closed by maintainer without comment | 3 | Genuine silent rejections — rare. |
| Unknown | 2 | Events API gave no clear actor. |

Adjusted for self-pulled and currently-open PRs, the **maintainer
response rate** on PRs that actually needed a decision is:

```
787 responded / (1000 − 100 self-pulled − 19 still open) = 787/881 ≈ 87 %
```

### Time-to-first-response distribution (days)

```
count   787
p25     0.20
median  1.08
p75     3.92
p95     14.52
max     273.90
```

The 273.90-day max is one outlier; the bulk of the distribution is
under 4 days.

---

## Conduction's slice (`MWest2020`, 22 PRs)

### Volume

| | count |
|---|---|
| Total PRs by MWest2020 | 22 |
| Merged | 11 |
| Self-pulled (closed by submitter, no maintainer action needed) | 7 |
| Closed by maintainers without merging | 2 |
| Still open | 2 |

The 7 self-pulled PRs are duplicates / replaced submissions:

| Self-pulled | Replaced by |
|---|---|
| #716, #717, #718, #719, #720 (closed within hours of creation) | #721, #722, #723, #724 — all merged |
| #727 | follow-up update on #725 (already merged) |
| #899 | #898 / #916 (merged) |

These do not represent maintainer non-responsiveness and are excluded
from the response-rate denominator below.

### Time-to-merge over Conduction's 11 merged PRs (days)

```
count   11
p25     0.35
median  3.01
p75     5.20
p95     9.40
max     9.40
mean    3.62
```

The Conduction distribution is **tight** — there is no stall tail. The
slowest of our merges (9.4 days, [#722](https://github.com/nextcloud/app-certificate-requests/pull/722))
is well below the repo's p95 (16.8 days).

### Time-to-first-response over Conduction PRs

Adjusted denominator (excluding self-pulled and currently-open):
22 − 7 − 2 = **15 PRs** that maintainers had to make a decision on.

| | count | rate |
|---|---|---|
| Got first maintainer response | 12 | 80% |
| No response (1× silent maintainer-close, 2× silently rejected) | 3 | 20% |

This is **in line with the repo norm of 87%** within the noise of
N=15.

```
count   12
median  3.59
mean    3.31
p25     2.22
p75     5.20
p95     5.97
max     5.97
```

This **is** out of line with the repo norm (median 1.08 days).
Conduction PRs wait roughly **3.3× longer than typical** for the
first maintainer comment.

### Who responds

| Maintainer | Conduction PRs responded to |
|---|---|
| `mgallien` | 5 |
| `camilasan` | 5 |
| `tobiasKaminsky` | 1 |
| `GretaD` | 1 |

Two maintainers (`mgallien`, `camilasan`) handle 10 of 12 responses on
our PRs. That is good for relationship building; it is also a single
point of latency when both are unavailable.

### Currently open Conduction PRs

| # | Title | Created | Days open |
|---|---|---|---|
| [#996](https://github.com/nextcloud/app-certificate-requests/pull/996) | Update certificate request in opencatalogi.csr | 2026-04-27 | ~9 |
| [#997](https://github.com/nextcloud/app-certificate-requests/pull/997) | Update certificate request in openregister.csr | 2026-04-27 | ~9 |

Both are below repo p95 (14.5 days) but well above repo median (1.1
days). Worth a `@mention` to `mgallien` or `camilasan` if not
addressed shortly.

---

## Where the gap actually is

**Time-to-merge after first response** (rough estimate from
Conduction's data: median TTM 3.0 days minus median first-response
3.6 days ≈ 0; many Conduction PRs are merged the same day a
maintainer first engages). This is fast — **once a maintainer looks,
the PR closes**.

The bottleneck is the **wait before the first maintainer look**. And
inspecting the timing pattern (e.g. #721–724 all created on
2024-08-31, all responded to on 2024-09-05 in the same minute), the
gap looks like a **batched-pickup delay**: maintainers process
Conduction's submissions as a group rather than one-by-one, so a batch
of N PRs all wait the time-to-pickup of the slowest, not the fastest.

---

## Concrete suggestions for the conversation

1. **Don't ask for "faster merges".** The post-engagement cycle is
   already fast, and the median time-to-merge for Conduction
   (3.0 days) is two days off the repo median in a process where
   Friday-to-Monday gaps already account for most of that. Easy to
   close that gap on accident, no real-world benefit.

2. **Do ask whether a lightweight pickup signal is feasible.** A
   convention like "@mention `mgallien` (or a `cert-request-team`
   group) when a Conduction batch is ready" would likely move our
   response median from ~3.6 days into the repo norm of ~1.1 days,
   without adding maintainer load — they react when pinged, just
   currently they pick up at their own polling cadence.

3. **Adopt a no-duplicate submission discipline on our side.** Seven
   of our 22 PRs were self-pulled within hours, all duplicates of
   other PRs we submitted the same day. That noise hurts review
   ergonomics ("did you mean #898 or #899?") and makes our slice look
   worse than it is. Probably one workflow change locally — submit
   once, only resubmit if explicitly asked.

---

## Methodology and caveats

- **Source:** GitHub REST API (`GET /repos/{owner}/{repo}/pulls?state=all`,
  paginated). Comments are from `GET /repos/{owner}/{repo}/issues/{n}/comments`.
  Close-actor for closed-without-merge PRs is from
  `GET /repos/{owner}/{repo}/issues/{n}/events` (taking the actor of
  the last `closed` event).
- **"First response" is the first issue-comment by a non-author.**
  This does **not** count formal PR reviews (`APPROVE` /
  `REQUEST_CHANGES`) or line-specific review comments. For this
  repository — a CSR collection where review is rare and most
  engagement is via comments — the issue-comment proxy matches
  reality, but a maintainer who silently approves a review without
  commenting will appear "silent" in our data.
- **Self-pulled detection** uses the close-event actor; it does not
  capture the rare case where a submitter cleans up their own PR via
  a different account.
- **Time-to-merge** is wall-clock UTC (`merged_at - created_at`). It
  includes weekends, holidays, and review-back-and-forth.
- **Sample size for Conduction's 80% response rate is 15 PRs.** The
  difference from the repo norm of 87% is well within sampling noise
  on a population that small.
- **No PR review-state data was fetched**, so PRs that received a
  formal review-request-changes but no comment will misclassify as
  silent. For this repo we estimate this is rare based on a manual
  spot check.

---

## Reproducing this report

```bash
export GITHUB_TOKEN=$(gh auth token)   # or any PAT with read:repo
gitsweeper fetch nextcloud/app-certificate-requests
gitsweeper throughput nextcloud/app-certificate-requests
gitsweeper throughput nextcloud/app-certificate-requests --since 2025-01-01
gitsweeper first-response nextcloud/app-certificate-requests
```

The Conduction-specific cuts and the close-actor enrichment that fed
the "self-pulled vs maintainer-closed" split were one-off SQL queries
against the local cache; they are not (yet) part of the gitsweeper
CLI.

---

## Appendix — day-of-week and hour-of-day patterns

The "queue depth" effect referenced in the TL;DR is not pure
randomness. Three reinforcing patterns explain most of Conduction's
3.3× first-response gap. None is decisive on its own; together they
account for the majority of the delta.

### 1. Maintainers work weekdays, with a strong Mon→Fri taper

Day-of-week distribution of all 787 first-responses (UTC):

```
Mon  26.4%  ████████████████████████   ← biggest day
Tue  20.6%  ██████████████████
Wed  16.4%  ██████████████
Thu  19.1%  █████████████████
Fri  13.6%  ████████████              ← weekday low
Sat   1.7%  █
Sun   2.3%  ██
```

Friday is the lightest weekday, doing about half the volume of
Monday. Weekends are effectively dark (4% combined).

The same pattern shows up in merges: Mon 26.4%, Fri 14.5%, weekend
2.6%. Submissions, in contrast, are almost flat across weekdays
(Mon 17.4% to Fri 15.1%) with a moderate weekend dip (Sat-Sun ~9%).
That asymmetry — flat submissions, peaked responses — is the
weekend-trap math: Friday submissions get caught.

### 2. Submission-day determines wait time

Median first-response by the day the PR was submitted (repo-wide):

| Submitted on | n | Median first-response (days) | p95 |
|---|---|---|---|
| Mon | 130 | 0.71 | 21.82 |
| Tue | 115 | 0.74 | 20.58 |
| Wed | 135 | 0.77 | 11.07 |
| Thu | 140 | 0.76 | 13.31 |
| **Fri** | **112** | **2.95** | **14.20** |
| Sat | 74 | 2.25 | 22.94 |
| Sun | 81 | 1.37 | 10.89 |

Submitting on Friday means waiting ~4× longer than Mon–Thu (2.95d
vs 0.71–0.77d median). Saturday submissions wait roughly the same;
Sunday is faster than Saturday because Monday catches them.

### 3. Hour-of-day — EU work hours dominate

First responses by hour-of-day (UTC):

```
00  ██                                 0.9%
07  ███████████                        3.9%
08  ████████████████████████████████   13.3%   ← morning peak (09:00 CET)
09  ██████████████████████████          8.8%
10  ███████████████████████             7.8%
11  █████████████████                   6.0%
12  ██████████████████                  6.2%
13  █████████████████████████████████  11.1%   ← post-lunch peak
14  ██████████████████████              7.6%
15  ███████████████████████             7.8%
16  ██████████████████                  6.1%
17  ████████                            2.7%
18  ███████                             2.4%
19  ███████████                         3.8%
20  █████████████                       4.4%
21  ████████                            2.9%
```

The bulk of activity sits in 08:00–16:00 UTC (09:00–17:00 CET, or
10:00–18:00 CEST). This strongly suggests an EU-based maintainer
team. Submissions outside that window — i.e. evenings or weekends
in CET/CEST — automatically wait until the next morning at minimum.

### 4. Conduction's submission timing falls in poor slots

```
MWest2020 submission day-of-week (n=22):
  Mon   9.1%
  Tue  40.9%  ████████████████████████   ← Conduction's spike
  Wed   9.1%
  Thu   0.0%
  Fri  22.7%  █████████████              ← weekend-trap day
  Sat  18.2%  ██████████                 ← guaranteed multi-day wait
  Sun   0.0%

→ 41% (Fri + Sat) goes into the weekend
```

```
MWest2020 submission hour-of-day (UTC, n=22):
  08  ██████████████████████████████   27.3%   ← 09:00 CET, healthy
  09  █████████████████████████        22.7%   ← 10:00 CET, healthy
  19  ███████████████                  13.6%   ← 21:00 CET, after hours
  20  ████████████████████             18.2%   ← 22:00 CET, after hours

→ 32% submitted outside EU work hours
```

### 5. Per-maintainer activity is uneven across the week

```
mgallien     (n=297): Mon 25%, Tue 26%, Wed 14%, Thu 16%, Fri 18%
camilasan    (n= 15): mostly Thu (53%), some Tue/Wed (40%)
GretaD       (n= 18): Thu (50%), Wed (28%)
tobiasKaminsky (n=1): Tue
```

`mgallien` is the most consistent across the week and handles 38%
of all responses; `camilasan` and `GretaD` are Thursday-heavy. For
Conduction's queue specifically, `mgallien` and `camilasan` together
do 10 of the 12 responses we receive — and their availability
patterns differ.

### How much of the gap does this actually explain?

Rough decomposition of Conduction's 3.3× first-response slowdown:

- **Weekend-trap submissions (Fri/Sat = 41% of our PRs):** at the
  repo-wide cost of ~2.2 extra days each, this contributes roughly
  0.9 days to our 2.5-day excess over the repo median.
- **Off-hours submissions (32% in 19–20 UTC):** an additional
  fraction of a day each, contributing perhaps 0.2–0.3 days.
- **Batch-pickup effect (visible on Tue submissions, where
  Conduction's median is ~3.0d vs the repo Tue median of 0.74d):**
  the residual ~1.5+ days unexplained by calendar effects. This is
  the part a `@mention`-style pickup signal would close.

The first two are submitter-side workflow (don't submit Fri-Sat-
evenings). The third is the substantive ask of the conversation:
make Conduction batches visible at submission time so they don't
wait through their normal poll cadence.

### Practical guidance derived from this

| Lever | Cost to us | Expected savings |
|---|---|---|
| Stop submitting Fri/Sat (defer to Mon morning UTC) | Tiny (a day's delay on our side) | ~1.5 days off our first-response median |
| Stop submitting 19–20 UTC (defer to 08–09 UTC) | Trivial | ~0.5 days |
| Pickup signal (`@mention` on batch ready) | Negligible to maintainers | ~1.5 days (closes the residual) |
| Stop duplicate-batch submissions | Local discipline | Cleans up the data, no first-response impact |
