# Golden1 Signal Resolution Stale-Mtime Incident — Root Cause, Timeline, Impact, Fix (2026-08-12)

**Status: real production bug, confirmed to have driven real account trades for
~1 week, real financial impact (estimated, not exact — see §6). Fixed same
day. This is not a hypothetical/what-if finding — the affected file was the
live `report/group_a_plus/latest/execution_plan.json` pointer, and the
account's actual holdings history tracks the bad signal closely (§4).**

## 1. What broke

`group_a_plus.runners.a2111._resolve_golden_signal_path()` (used by
`run_a2118()`, which every production `execution_plan.json` /
`daily_signal.py` run depends on) selects "the current golden1 basis" by
taking whichever file matches `results/signal_group_a_*.json` (plus the
curated `results/group_a_combined_live_latest.json` pointer) **has the
newest filesystem mtime** — not whichever is dated closest to today, not
whichever is tagged as a genuine live run. Docstring at
`a2111.py:94-102` ("H3", from the 2026-07-02 Fable 5 audit) documents this
as a known, deliberately-unfixed limitation.

A partial mitigation exists: since 2026-08-04
(`project_golden1_signal_resolution_whatif_pollution_20260804`), any run of
`generate_dual_group_signal.py` with `--override-holdings-json` set writes
its output as `whatif_signal_{group}_*.json` instead of
`signal_{group}_*.json`, specifically so what-if/hypothetical runs stop
matching this glob and can't be mistaken for a live signal. **This fix
only covers files created after 2026-08-04.** A file from *before* the fix
existed, `results/signal_group_a_20260803_195945.json` (created
2026-08-03, `requested_as_of_date: 2026-08-04`, `override_holdings_source:
None`), was never renamed and kept its non-`whatif_`-prefixed name. Its
holdings (`0050.TW: 89, 00631L.TW: 0, 00679B.TWO: 10000, 00632R.TW: 0`)
don't match any real account snapshot from that period — it was some kind
of test/exploratory run, not a production-intended signal.

**Because nothing newer matching this glob was generated after 2026-08-03,
this one test file's mtime silently became "the current golden1 basis"
for every `run_a2118()` call — including every real
`execution_plan.json` regeneration — from 2026-08-04 through
2026-08-10 (confirmed range; see §3), continuing through 2026-08-12
until fixed in this session.** Its frozen `target_weights` —
`{0050.TW: 0.30, 00631L.TW: 0.0, 00632R.TW: 0.2708, cash: 0.429}` — were
served as "today's golden1" on every one of those days regardless of what
the market actually did.

## 2. Why this matters: golden1 is supposed to be computed fresh every day

`golden_weights = _normalize(_weights_from_group_a(golden_signal))` in
`group_a_plus/runners/a2118.py:796` is deliberately *not* a static
50/20/30 table — a2118's own code comment states "golden1 itself drifts
daily" specifically because it's meant to track the live PVA/SJM
risk-scaling overlay computed by `generate_dual_group_signal.py`. The
entire point of this design is that golden1's weights respond to current
price/momentum/acceleration (P/V/A) state. A stale-mtime resolution bug
defeats this by construction — for over a week, the "live" golden1 basis
was not live at all.

## 3. Reconstructed timeline: what golden1 actually should have shown vs. what was frozen

Re-ran `generate_dual_group_signal.py` (which computes PVA/SJM fresh on
every call, independent of the `_resolve_golden_signal_path()` bug) with
each historical `--as-of-date` to reconstruct the genuine signal:

| date | **true** 0050 / 00631L / 00632R (reconstructed) | **frozen** 0050 / 00631L / 00632R (what production actually showed) |
|---|---|---|
| 2026-08-04 | 35.5% / 7.0% / 27.5% | 30% / 0% / 27.1% |
| 2026-08-05 | 36.4% / 7.0% / 26.6% | 30% / 0% / 27.1% |
| 2026-08-06 | 36.3% / 7.0% / 26.7% | 30% / 0% / 27.1% |
| 2026-08-07 | 36.1% / 7.0% / 26.9% | 30% / 0% / 27.1% |
| 2026-08-10 | 36.6% / 7.0% / 26.4% | 30% / 0% / 27.1% |
| **2026-08-12 (today)** | **62.6% / 7.4% / 0.0%** | **30% / 0% / 27.1% (until fixed this session)** |

Two distinct failure modes, not one:

1. **2026-08-04 through 2026-08-10**: the frozen signal was in the *same
   directional posture* as the true one (both wanted the 00632R hedge
   active, roughly 26-28% either way) but **understated 0050 by ~5-6
   points and completely zeroed out 00631L** (true value ~7% throughout,
   frozen showed 0%). A real, if smaller, miscalibration every single
   day of this window.
2. **Sometime between 2026-08-10 and 2026-08-12**: the true PVA/SJM state
   genuinely flipped from defensive (hedge active) to bullish (0050 62.6%,
   hedge fully removed) — a real regime change the frozen signal could
   not see at all, because it was still serving the 2026-08-03 snapshot.
   This is the larger of the two gaps.

## 4. This drove real account trades — not just a stale report

Reconstructed real holdings directly from the dated personal workbook
snapshots the user saved each day (`taiwan_stock_202608{04,06,07,10,12}.xlsx`,
row `即時庫存`) — a finer-grained trail than the execution-plan-input
copies alone:

| workbook date | 0050.TW | 00631L.TW (labelled "50+2" through 08-04) | 00632R.TW (labelled "50反1" from 08-06) | 00679B.TWO |
|---|---|---|---|---|
| 2026-08-04 | 3834 | **800** | (position doesn't exist yet) | 3000 |
| 2026-08-06 | 3914 | **0** | **2000** (new) | 3000 |
| 2026-08-07 | 3994 | 0 | 2000 | 3000 |
| 2026-08-10 | 3994 | 0 | **11000** (+9000) | **100** (−2900) |
| 2026-08-12 (before fix) | 3994 | 0 | **22000** (+11000) | 100 |

Between 2026-08-04 and 2026-08-06, the account's real 00631L position was
sold from 800 shares to 0, and a new 00632R hedge position was opened in
the same slot — matching the frozen signal's `00631L: 0%` / `00632R: ~27%`
target exactly, not the true signal's `00631L: 7%`. The 00632R position
was then built up in (at least) three separate steps — 2,000 → 11,000
(2026-08-07 to 08-10) → 22,000 (08-10 to 08-12), an 11x increase overall —
consistent with the account continuing to top up toward the frozen ~27%
hedge target every time new cash was added over the week, each time
re-confirmed by the same stuck signal. The 00679B position was cut from
3,000 to 100 shares in the same 08-07→08-10 window, most likely funding
part of the 00632R build-up (00679B itself was flat over this period,
26.41→26.49, not a material P&L driver either way). **This is not a
report that sat unread; the holdings history shows repeated, escalating
trades placed against it across at least three separate dates over the
affected week.**

## 5. Market context: which direction this cost money

`ohlcv` table, 2026-08-03 to 2026-08-12 (`FinRL/data/stock_data.db`):

| ticker | 08-03 close | 08-12 close | change |
|---|---|---|---|
| 0050.TW | 102.00 | 105.20 | **+3.14%** |
| 00631L.TW (2x) | 32.62 | 35.45 | **+8.68%** |
| 00632R.TW (-1x) | 10.60 | 10.06 | **−5.09%** |

The market rose over this window (0050 +3.1%, amplified to +8.7% in the
2x product). The account (a) held **zero** 00631L since 2026-08-06 instead
of the ~7% weight the true signal called for throughout, missing that
leveraged upside, and (b) built up a large 00632R short-equity hedge
position that lost value as the market rose, right through the point
(around 2026-08-10/12) where the true signal had already dropped the
hedge to zero.

## 6. Estimated financial impact (methodology and caveats)

**This is an estimate from available price/weight data, not an exact
realized P&L — there is no complete intraday trade log for this account
in this environment** (`isaac_tra_20260718.xlsx`, the manual broker
transaction export used for reconciliation, is dated 2026-07-18, predating
this entire incident window — see the pre-existing
`broker_holdings_reconciliation_review.json` staleness warning already
flagged in `ops_health.json` before this investigation started). The
components below are as precise as the available data supports; do not
treat the total as an exact figure.

1. **00631L underweight opportunity cost**: 00631L was cut from 800 to 0
   shares between the 08-04 and 08-06 workbook snapshots (exact trade day
   not pinned down further than that 2-day window), while the true target
   signal wanted ~7% of portfolio continuously from 08-04 onward. Using
   the 08-05 close (34.15, the midpoint-window proxy for the sale) through
   08-12 (35.45, +3.8%) against a ~7%-of-~$1.65M target weight —
   approximately **$4,300-$4,900** in missed gains from being at 0%
   instead of ~7% weight (range reflects the 2-day sale-date uncertainty).
2. **00632R hedge mark-to-market loss**, now with three dated checkpoints
   instead of two:
   - Leg 1 (2,000 shares, opened ~08-06 @ 10.33 → today's 10.06): **≈$540** loss.
   - Leg 2 (+9,000 shares, added between 08-07's 10.35 and 08-10's 10.17,
     using the range midpoint ≈10.25 as the estimated build-up cost →
     today's 10.06): **≈$1,710** loss.
   - Leg 3 (+11,000 shares, added between 08-10's 10.17 and 08-12's 10.06,
     midpoint ≈10.12 → today's 10.06): **≈$660** loss.
   - Plus today's actual unwind transaction cost (commission + slippage +
     sell tax, taken directly from this session's real execution plan):
     **$647**.
   - Subtotal: **≈$3,550**.
3. **00679B**: cut 3,000 → 100 shares in the 08-07→08-10 window while the
   price was flat (26.41 → 26.49) — not a material P&L driver either way,
   noted for completeness only.
4. **Combined estimate: approximately $7,900-$8,500**, on a portfolio of
   roughly $1.6-1.7M (**~0.5% of portfolio value**) over about one week.
   This is tighter than the first-pass estimate (now backed by three
   dated 00632R checkpoints instead of two endpoints), but still an
   estimate, not an exact realized figure — intraday trade prices within
   each build-up window remain unknown.

## 6b. Full root cause, re-verified: why 08-04 specifically never happened, and why nothing caught it for 9 days

User pushed back after the first pass of this investigation ("我還是沒看到根本原因, 為什麼沒有更新8/4?") — the first version explained the *mechanism* (mtime-based resolution + an unprotected pre-fix file) but not *why, operationally, no fresher file ever appeared* or *why nothing surfaced the problem for over a week*. Re-investigated both questions exhaustively rather than re-asserting the same explanation:

**Why no fresh file ever appeared between 2026-08-03 and this session's fix**: exhaustively listed every file matching `_resolve_golden_signal_path()`'s candidate set (`results/signal_group_a_*.json` plus `results/group_a_combined_live_latest.json`) with an mtime between 2026-08-01 and 2026-08-12 20:00. Exactly two files exist in that entire window: `signal_group_a_20260801_203956.json` (08-01, itself a pre-fix what-if artifact per `project_golden1_0531_a2118_20260803_predict_divergence_20260801`) and `signal_group_a_20260803_195945.json` (08-03, the file identified in §1). **Nothing else was ever generated in this window.** This isn't a failure of a scheduled job — there was no attempt at all, because the only script that produces a genuine entry in this candidate set, `scripts/run/run_group_a_combined_signal.py`, is confirmed not to be part of `run_ncf_daily_pipeline.py` (it only appears there as a path reference for freshness bookkeeping — see §8) or any other automation. It has to be run manually, on purpose, and nobody did during this window.

**Why 15+ manual `execution_plan.py`/`daily_signal.py` re-runs during this same window didn't self-correct it**: `run_a2118()` is a pure *consumer* of `_resolve_golden_signal_path()`'s result — it reads whichever file wins the mtime race, but nothing in that call chain ever regenerates or refreshes the underlying golden1 signal file itself. Re-running `execution_plan.py` any number of times only re-reads the same stale winner; only a separate, explicit run of the signal generator itself can produce a new candidate.

**Why nothing surfaced the staleness even to a careful manual reading of the output**: `a2111.py:_golden_signal_metadata()` *does* compute exactly the diagnostic needed to catch this — `golden_signal_path`, `golden_signal_modified_at` (the file's mtime), and `golden_signal_sha256` — and stores it in the a2118 report dict under `golden_signal_coverage`, explicitly described in its own docstring as existing "to make the [mtime] choice auditable." **Verified this metadata never reaches either `daily_signal.py`'s or `execution_plan.py`'s final output**: `grep` for `golden_signal_coverage` / `golden_signal_modified_at` / `golden_signal_path` in both source files, and directly in the real `execution_plan.json`, returns zero matches. The information needed to catch this bug was computed, every single time, for all 15+ runs — and silently discarded before reaching any human-visible output. Compounding this, `execution_plan.json`'s own `actual_data_date` field reflects OHLCV/NCF data recency (which genuinely *was* current each day), creating a false impression that "the data is fresh" while the golden1 regime weight table specifically was frozen underneath it, invisibly.

**Summary of the three independent gaps, all required for this to have gone undetected for 9 days**:
1. Resolution logic trusts filesystem mtime with no distinction between genuine daily runs and old test artifacts (known, H3, unfixed by design).
2. The one script that produces genuine entries isn't automated and nobody ran it manually in this window — not a bug, an operational gap.
3. The audit trail that *would* have caught this (`golden_signal_coverage`) is computed but never propagated to any user-facing output — a silent data-loss point in the reporting pipeline, not previously documented anywhere.

## 6c. Is this bug pattern live elsewhere right now? (due-diligence sweep)

User asked "還有什麼地方要修復" (what else needs fixing) after the root-cause
was established. Grepped the whole codebase for the same
`max(candidates, key=lambda p: p.stat().st_mtime)` / equivalent glob-then-mtime
pattern: it appears in **at least 15 places**, including several on
production-critical paths — `group_a_plus/operations/execution_plan.py`
(`_latest_compounding_regime_path`), `group_a_plus/operations/daily_signal.py`
(three separate resolvers), `group_a_plus/runners/a2118.py` /
`a2115.py` (`_resolve_ncf_path`, feeding the NCF live-overlay/late-bull-hedge
trigger described in §1-2), `group_a_plus/operations/ops_health.py`, and
`group_a_plus/integrations/cross_market_graph_shadow.py`. This is a
systemic pattern, not a one-off mistake local to golden1 resolution.

Checked whether any of the other production-critical resolvers are
*currently* serving a stale file the same way golden1 was: `ls -t` on the
NCF resolvers' (`ncf_00631l_latest_*.json`, `ncf_00632r_latest_*.json`)
and the compounding-regime resolver's
(`00631l_leveraged_compounding_regime_*.json`) candidate sets — **both
currently resolve to genuinely fresh (2026-08-12) files.** This is
because both NCF signal generation and the compounding-regime calculation
*are* wired into `run_ncf_daily_pipeline.py`'s automated steps (confirmed
by this session's own pipeline run earlier the same day), unlike golden1
generation. **Conclusion: this specific incident was possible because
golden1 happened to be the one resolver in this family not covered by
automation — not because the mtime-resolution pattern itself is
currently broken elsewhere.** The pattern remains a latent risk: any of
these other resolvers would silently reproduce the same failure mode the
day its own upstream automation lapses, with the same blind spot (no
propagated `*_modified_at` diagnostic in any of them, per a quick check
of their call sites — not exhaustively verified for all 15 occurrences).

## 7. Fix applied this session

1. Generated a genuine, fresh (non-what-if) golden1 signal for today:
   `scripts/run/run_group_a_combined_signal.py` (no over-ride flags),
   writing `results/signal_group_a_20260812_215403.json` and refreshing
   the curated pointer `results/group_a_combined_live_latest.json` — both
   now have today's mtime, correctly superseding the stale 2026-08-03
   file in `_resolve_golden_signal_path()`'s max-mtime selection.
2. Verified the fix: re-ran `execution_plan.py` (scratch-redirected first)
   and confirmed `target_weights` now reflect the fresh signal
   (`0050: 53%, 00631L: 7.4%, 00632R: 0%, cash: 39.6%` — the 0050 figure
   is lower than the unconstrained 62.6% because a `0050 target-weight
   step limiter` overlay capped the single-day move, a separate,
   intentional risk control, not a bug).
3. Regenerated the **real** production `execution_plan.json` (real
   holdings from `taiwan_stock_20260812.xlsx` + $1,000,000 cash, per
   user instruction) — this is a live pointer overwrite, done with
   explicit user confirmation. Recommended trades: sell all 22,000
   00632R shares, sell all 100 00679B shares, buy 1,715 more 0050 shares,
   buy 1,364 00631L shares (new position). `planning_status: ready`,
   turnover 27.5% (under the 50% auto-cap), no manual confirmation
   required.

## 8. What this fix does and does not address

- **Fixed**: today's golden1 basis is fresh again, and will stay fresh as
  long as `run_group_a_combined_signal.py` (or an equivalent real,
  non-what-if `generate_dual_group_signal.py` call) is run at least once
  after any future what-if/test run that might otherwise claim the
  newest mtime.
- **Not fixed (root cause remains)**: `_resolve_golden_signal_path()`
  itself still resolves by max-mtime with no distinction between "genuine
  daily run" and "old pre-2026-08-04 test artifact still sitting in
  `results/`." The 2026-08-04 partial fix (whatif_ prefix) only prevents
  *future* pollution from override-holdings runs; it does not retroactively
  protect against older non-prefixed files, and does not prevent a
  *future* genuine-looking but stale file (e.g. from a crashed automation
  run, or another one-off test that doesn't use `--override-holdings-json`)
  from silently becoming "today's golden1" again.
- **Not fixed**: `run_group_a_combined_signal.py` is confirmed **not**
  part of the automated daily pipeline (`run_ncf_daily_pipeline.py` only
  references its output paths for freshness bookkeeping, never invokes
  it) — this is why the golden1 basis could go stale for over a week
  without any automated alert. There is a freshness watchdog
  (`readiness_review_freshness`, seen flagging dozens of other stale
  research files in `ops_health.json`), but it evidently does not cover
  `results/signal_group_a_*.json` / `results/group_a_combined_live_latest.json`
  specifically, or it would have caught this.
- **Not done in this session** (deliberately, given time/scope — flagged
  for a follow-up, not fixed here): making `_resolve_golden_signal_path()`
  itself robust (e.g. preferring the curated `group_a_combined_live_latest.json`
  pointer outright over the raw glob, or requiring a `_generated_at`
  timestamp field inside the file rather than trusting filesystem mtime,
  which is trivially wrong after any file copy/checkout/restore); adding
  `run_group_a_combined_signal.py` (or a lighter always-fresh variant) to
  the automated daily pipeline; adding a freshness check specifically for
  the golden1 signal basis to `ops_health.json`.
- **Fixed in this session (2026-08-12, same day, after the re-investigation
  in §6b identified the gap)**: `golden_signal_coverage` now propagates.
  `group_a_plus/operations/daily_signal.py::build_daily_signal()` computes
  `golden_signal_age_days` (business days between `golden_signal_modified_at`
  and the signal's `actual` data date, via the existing `_business_days_between`
  helper) and appends a soft warning — `"golden1 signal basis (...) is N
  business days old ... consider running scripts/run/run_group_a_combined_signal.py"`
  — to `execution_warning_reasons` when that age exceeds 2 business days.
  Does not block execution (advisory only, matching how every other soft
  staleness issue is already handled in this function — e.g.
  `optional_warnings`). The full `golden_signal_coverage` dict (path,
  sha256, mtime, weights, caveat) is also now included verbatim in
  `daily_signal.py`'s output. Because `execution_plan.py` already embeds
  `daily_signal.py`'s entire report under `source_live_signal`, this
  field automatically reaches `execution_plan.json` too — **no change to
  `execution_plan.py` itself was needed.**

  Verified: (a) standalone unit-level check of the age computation against
  this incident's real dates (2026-08-03 → 2026-08-12) returns 7 business
  days, comfortably above the 2-day threshold — confirming this mechanism
  would have caught the incident on day one, had it existed; (b) a
  scratch-redirected `daily_signal.py` run against today's now-fresh
  golden1 signal (age 0) produces zero warnings — no false positive;
  (c) a scratch-redirected `execution_plan.py` run confirms
  `source_live_signal.golden_signal_coverage` is present in its output;
  (d) production `report/group_a_plus/latest/live_signal.json` and
  `execution_plan.json` MD5s unchanged throughout (all verification runs
  used `--output`/`--latest-pointer` redirected to
  `results/scratch_predict_20260813/`).

  Still not done (deliberately left for a separate follow-up, not blocking
  this fix): extending the same propagation pattern to the ~15 other
  call sites sharing the max-mtime resolution pattern found in §6c;
  adding the equivalent staleness check to `ops_health.json`; adding
  `run_group_a_combined_signal.py` to the automated pipeline; hardening
  `_resolve_golden_signal_path()` itself.

## 9. Files

| File | Nature |
|---|---|
| `results/signal_group_a_20260812_215403.json` | New — genuine fresh golden1 signal, generated this session |
| `results/group_a_combined_live_latest.json` | Overwritten — curated pointer refreshed |
| `results/group_a_combined_live_latest.csv`, `results/group_a_combined_bundle_latest.json` | Overwritten alongside the above by `run_group_a_combined_signal.py` |
| `report/group_a_plus/latest/execution_plan.json` | **Overwritten — real production pointer**, regenerated with real holdings (`taiwan_stock_20260812.xlsx`) + $1,000,000 cash, per explicit user instruction |
| `results/group_a_plus_execution_plan_v2.json` | Overwritten — non-pointer copy of the same regeneration |
| `results/scratch_predict_20260813/*` | New — this session's what-if/verification scratch artifacts (predictions and fix-verification runs), safely redirected throughout, never touching production |
| `group_a_plus/operations/daily_signal.py` | **Modified** — `build_daily_signal()` now computes `golden_signal_age_days`, appends a soft staleness warning to `execution_warning_reasons` past 2 business days, and includes `golden_signal_coverage` verbatim in its output (§8 follow-up fix) |
| This file | New, incident handoff record |

## 10. Memory index

`project_golden1_signal_stale_mtime_incident_20260812.md`. Related:
`project_golden1_signal_resolution_whatif_pollution_20260804` (the prior,
partial diagnosis/fix of the same underlying mechanism — this incident is
that same class of bug, from a file predating that fix),
`feedback_execution_plan_latest_pointer_default_overwrite`,
`feedback_production_pointer_scripts_need_output_redirect_for_testing`,
`project_production_pointer_backup_protection_20260809` (the rolling
`.bak` protection this project already has for accidental overwrites —
does not cover this class of bug, since the file *was* being written
correctly each time, just from a stale upstream input).
