# TSMC Concentration Divergence (ADD_00631L vs ADD_0050) - Group A+ Review

**Status: shadow-only, not promoted. User-proposed mechanism, 2026-08-09.**

## Background

User proposed distinguishing whether 0050's rally is TSMC-driven or broad,
via `ex_tsmc_return`, `TSMC_contribution_to_0050`, and
`concentration_divergence` metrics, plus cross-sectional breadth (% of 0050
constituents above 20MA, % advancing, equal-weight vs cap-weight proxy,
top-5 contribution), to decide -- only when A21.18 is about to add 00631L in
golden1 -- whether to add 00631L normally, redirect the new capital to 0050
instead, or do nothing.

**Investigation before building anything found most of the core math
already live**, just advisory-only:
`group_a_plus/operations/daily_signal.py` already computes
`0050_ex_tsmc_proxy` (identical to the proposed `ex_tsmc_return`) and
classifies `narrow_lead`/`tsmc_led_narrow` states (TSMC up, ex-TSMC basket
flat/down) with a `reference_guidance.allow_00631l_add: False` label --
but that guidance is `trade_policy: diagnostic_only_no_weight_change`, never
enforced. `tsmc_leadership_vs_0050_ex_tsmc` (= `concentration_divergence`)
also already exists in `group_a_plus/ncf_2330/leadership.py`, but was tested
as an NCF *predictive feature* on 2026-07-07 and found redundant with
`return_1d` (zero incremental AUC on purged CV / 2025-2026 OOS) -- that
finding is about its use as an ML feature, not about its use as a
rule-based regime classifier for allocation decisions, so it doesn't by
itself invalidate this different use case.

Real gaps identified: (1) `narrow_lead` was never wired into anything that
changes weights; the only weight-changing mechanism
(`_apply_tsmc_weakness_trim`) only fires on `tsmc_weak_confirmed` (TSMC
itself weak) and reduces 00631L to *cash*, never to 0050; (2) no
`ADD_0050_INSTEAD` redirection existed at all; (3) the proposed
constituent-level breadth metrics (20MA breadth, advancing %, equal-weight
vs cap-weight proxy, top-5 contribution across all ~50 constituents) had no
supporting data -- this project's DB only has individual-stock price
history for 4 large caps beyond TSMC (2317 Hon Hai, 2454 MediaTek, 2308
Delta, 2382 Quanta).

## What Was Built

### 1. `group_a_plus/integrations/tsmc_concentration_divergence.py`

Reusable module, price-only (no NCF dependency, fully backtestable without
lookahead):

- `ex_tsmc_return()`, `tsmc_contribution_to_0050()`,
  `concentration_divergence()` -- the three formulas from the proposal.
- `classify_narrow_lead()` -- reproduces `daily_signal.py`'s `narrow_lead`
  boolean exactly (verified against source).
- `top5_breadth_snapshot()` -- **top-5 mega-cap proxy, not full-universe
  breadth**. Uses TSMC (officially calibrated weight, 0.5831, from
  `group_a_plus/utils/tsmc_0050_weight.py`) plus the 4 other large caps
  this project has price history for, with their weights sourced from
  `evaluate_stockmixer_atfnet_shadow.py`'s `PARTIAL_0050_PROXY_WEIGHTS`
  (itself labelled research-only there, not independently re-verified).
  Combined estimated weight ~71.1% of 0050. Reports: `top5_above_ma20_pct`,
  `top5_advancing_5d_pct`, `top5_weighted_contribution_ratio_5d`.
  **A true equal-weight-vs-cap-weight proxy across all ~50 constituents was
  NOT built** -- would need a new constituent-list + OHLCV-fetch pipeline
  for the other ~45 mid-cap stocks; not attempted this pass.

13 unit tests (`tests/test_tsmc_concentration_divergence.py`), all passing,
covering the three formulas and the narrow_lead classifier's boundary
conditions.

**Data staleness found while building this**: the 4 non-TSMC large-cap
tickers (2317/2454/2308/2382) are stuck at **2026-07-15** in this DB, ~3.5
weeks stale versus 0050.TW's fresh 2026-08-07 -- confirmed via
`refresh_group_data.py`'s `GROUP_A_TICKERS`/`GROUP_B_TICKERS` lists, which
don't include any of the 4. They were populated once by an unrelated
research script (`evaluate_stockmixer_atfnet_shadow.py` or
`evaluate_cross_market_directed_graph_shadow.py`) and never added to any
daily refresh. **Not fixed this pass** -- same class of gap as
[[project_readiness_review_as_of_staleness_20260808]] found earlier this
session; the breadth diagnostic's live usefulness is currently limited by
this staleness until these 4 tickers are added to a daily fetch.

### 2. `scripts/evaluate/build_tsmc_concentration_divergence_breadth_snapshot.py`

Thin CLI wrapper around `top5_breadth_snapshot()`. Read-only diagnostic,
writes to `report/group_a_plus/latest/tsmc_concentration_divergence_breadth.json`.
No live weight impact.

### 3. `scripts/evaluate/evaluate_add_0050_instead_of_00631l_shadow.py`

The actual `ADD_0050_INSTEAD` shadow backtest. Reuses a2118's real regime
backtest unchanged (`golden1_0531` untouched); post-processes only the
resulting daily target-weight series: on any day where 00631L.TW's target
weight is *increasing* versus the prior day AND `narrow_lead` is detected
(price-only), redirects the increment (default `redirect_add_only`
variant) or the entire golden1 00631L sleeve (`redirect_full_golden1_631l`
variant) into 0050.TW instead. Two independent tests confirm this is
purely additive: `golden1_0531_unchanged: true` in every report, and the
mechanism only ever touches 0050.TW/00631L.TW weights on days it fires.

Tested across the same 7-window OOS set established earlier this session
(2017-2019 was excluded here since it wasn't part of this script's default
list, but the other 6 spanning 2020-2026 including COVID/2021
correction/2022 bear/2024 crash were used, plus the 3 recent live windows).

**Result: 7/7 windows triple-pass (final value, Sharpe, max drawdown all
>= baseline), decision = `candidate_for_group_a_plus_shadow_queue`.**

**Critical caveat, do not over-read this result**: `narrow_lead` itself
fires reasonably often (13-63 days per window), but the actual trigger
condition (`narrow_lead` AND 00631L's target weight increasing that same
day) only fired **3 times total across all 7 windows (~6+ years of
history)** -- because a2118's current golden1 weights hold 00631L near 0%
most of the time already (a consequence of other existing overlays), so
there are very few "00631L is being added" moments for this guard to act
on in the first place. Four of the seven windows had **zero** redirect
events (delta exactly 0.0 on every metric). The 7/7 pass is real but is
mostly "the guard almost never activates, so it trivially can't hurt" --
**not strong evidence that it helps**. The 3 events that did fire were all
directionally positive (delta final_value +2,630 to +6,378 on
million-dollar portfolios) but n=3 is far too small to draw statistical
confidence from.

## Decision

**Shadow-only, not promoted.** Per this project's own signal-validation
discipline
([[project_signal_validation_checklist_adopted_20260723]]), a mechanism
that only fired 3 times in 6+ years of backtest cannot be validated as
having a real edge yet -- it needs either (a) many more years of data
where 00631L is actually being actively added in golden1 (which requires
a market/strategy configuration this project hasn't spent much history in),
or (b) a live observation period once the guard is wired in as a pure
diagnostic overlay (log what it *would* have done, without acting) to
accumulate more real trigger events before considering enforcement.

Recommended next steps if this line is continued:
1. ~~Fix the 4-ticker staleness~~ **Done same day (2026-08-09).**
   `scripts/fetch/fetch_cross_market_ohlcv.py`'s `DEFAULT_TICKERS` now
   includes 2317/2454/2308/2382 (backfilled 2019-01-01 to present via
   `external_market_ohlcv`, same mechanism as 2330.TW). Refreshes
   unconditionally every daily pipeline run going forward.
   `tsmc_concentration_divergence.py`'s `_load_close_prices()` updated to
   read all 5 top-5-proxy tickers from `external_market_ohlcv` (previously
   split ohlcv/external_market_ohlcv). Verified: diagnostic now reports
   `date: 2026-08-07`, matching 0050.TW's freshness (was stuck at
   2026-07-15).
2. Wire `top5_breadth_snapshot()` into `daily_signal.py` as a separate
   additive logging package. The intended placement is a new `top5_breadth`
   key inside `_tsmc_0050_health_snapshot()`'s return dict, without touching
   `state`, `reference_guidance`, `_apply_tsmc_weakness_trim()`, or
   `execution_regime`. Keep this separate from the pure formula/backtest/log
   package so the mixed `daily_signal.py` working-tree changes can be
   reviewed and tested on their own.
3. Consider extending to true full-~50-constituent breadth (a new data
   pipeline) only if the top-5 proxy's advisory logging over time shows it
   would have caught something the top-5 proxy alone missed -- not
   speculatively building it now.

## 2026-08-09 Incident Note: Accidental Production `live_signal.json` Overwrite

While verifying an earlier local `daily_signal.py` prototype end-to-end, ran
`group_a_plus/operations/daily_signal.py` without redirecting `--output`
away from its default, which is the live production pointer
`report/group_a_plus/latest/live_signal.json`. This overwrote it in place
(confirmed via `git diff`: 356 insertions / 344 deletions).

Assessed as low-risk, not corruption: `daily_signal.py` has no code path
that writes `execution_plan.json` (grepped, zero hits) -- that file's
separate modification (mtime 2026-08-08 22:01, ~14h before this incident)
came from other activity, not this command. The diff shows a legitimate
refresh with real current data: `execution_regime` stayed `golden1`
unchanged, `actual_data_date` moved from a stale 2026-08-05 (the file
hadn't been refreshed since 2026-08-06, already 3 days overdue before this
incident) to a fresh 2026-08-07, plus the new `top5_breadth` field. No
test/placeholder values were involved. User was informed transparently and
chose to keep the refreshed file rather than revert.

Also discovered while investigating: this repository currently has heavy
**concurrent multi-session activity** -- dozens of untracked files from
unrelated research lines (harlf_*, moira_*, adaptive_quantile_risk_gate_*,
regime_weighted_tail_conformal_*, defensive_cash_floor_*, and more) were
present in `git status` that this session never created. Any file under
`report/group_a_plus/latest/` should be assumed possibly volatile/being
written by other concurrent sessions at any time, not just this one.

**Lesson for future work in this repo**: any script whose default output
path is a `report/group_a_plus/latest/*` production pointer needs an
explicit `--output` redirect before running for verification/testing
purposes, even for a "just confirm the new field shows up" smoke test --
matching the existing standing rule for `execution_plan.py`'s
`--latest-pointer` (see
[[feedback_execution_plan_latest_pointer_default_overwrite]]), now
generalized to apply to any production-pointer-writing script in this
project, not just that one.
