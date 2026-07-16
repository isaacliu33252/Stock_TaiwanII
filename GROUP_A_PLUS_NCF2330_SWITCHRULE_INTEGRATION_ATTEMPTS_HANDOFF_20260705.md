# GroupA+ ncf_2330 Integration Attempts + SwitchRule Dormant-Field Sweep Handoff - 2026-07-05

## Executive Summary

Follow-up to `GROUP_A_PLUS_A2118_CHIP_FALLBACK_HANDOFF_20260704.md` and
`GROUP_A_PLUS_FABLE_AUDIT_MARKET_STATE_ARBITRATION_HANDOFF_20260704.md`.

This session ran five separate, independent attempts to find a way to make
ncf_2330 (the TSMC individual-stock model) or two dormant `SwitchRule` fields
actually improve a2118. **All five were rejected.** No production code
changed as a result of this session — the one production-path edit made
mid-session (wiring `_apply_tsmc_weakness_trim` into `build_daily_signal`)
was reverted after backtesting showed it lost money. The most useful output
is not a new feature but a second, independent confirmation of the
regime-ambiguity finding from the 2026-07-04 market_state arbitration
handoff: price/volatility-only early-warning signals cannot distinguish a
normal correction from a genuine crash before the fact, using the data this
project currently has.

## Part 0: ncf_2330 integration status at session start

`group_a_plus/operations/daily_signal.py` had `_apply_tsmc_weakness_trim`
(reduce 00631L 25% when TSMC weakness is confirmed AND 00631L's own NCF
signal agrees) fully implemented and unit-tested, but **never called** from
`build_daily_signal` — only `_apply_bearish_high_risk_trim` was wired in
(line ~1224). So ncf_2330 was already feeding `signal_alignment` (advisory
score) and alert messages (`tsmc_led_narrow_reference`,
`tsmc_weak_manual_review`), but had zero effect on actual portfolio weights.
This was flagged as an incomplete wiring, not an intentional shadow-only
design, and the user asked to wire it in and backtest.

## Attempt 1: Wire `_apply_tsmc_weakness_trim` into `build_daily_signal`, then backtest

Wired the call in (`daily_signal.py`, right after `_apply_bearish_high_risk_trim`).
72 relevant tests passed. Checked the effect using the pre-existing
`scripts/misc/a2118_ncf_2330_tsmc_overlay_sweep.py` sweep
(`results/a2118_ncf_2330_tsmc_overlay_sweep_20260704.json`, 2025-01-02 ~
2026-07-02, 324 parameter combinations), whose thresholds exactly match the
hardcoded production defaults in `_apply_tsmc_weakness_trim` /
`_tsmc_0050_health_snapshot`.

Production-default result: final_value -65,578 (-3.1%), Sharpe +0.011 (noise,
from lower volatility only), **max_drawdown delta = 0.0 (no improvement)**.
Full sweep: **0/324 variants improved final_value; 0/324 improved
max_drawdown.** The trim never fires near the window's actual max-drawdown
day; every trigger is a short-lived pullback that later recovers.

**Reverted.** `daily_signal.py` is back to advisory-only ncf_2330 (matches
pre-session state).

## Attempt 2: Fold ncf_2330 tail risk into `total_risk_score`

Rationale: ncf_2330's own 4-round validation history (`NCF_2330_*HANDOFF*.md`)
found only the tail-risk output survives out-of-sample checks; the
directional output does not. `total_risk_score` already gates a2118's real
defensive entry (`require_total_risk_score=6`) and the bearish high-risk trim
(`total_risk_score>=9`), so this tests adding one more binary flag to that
existing, already-causally-connected score instead of a new independent
price-return trigger.

Script: `scripts/misc/ncf_2330_total_risk_score_overlay_sweep.py`. Method:
monkeypatch `_regime_features` in-process (never edits the file) to add
`chip_tsmc_2330_tail_risk = (prob_fwd_mdd_gt5_h20 >= threshold)` into
`chip_score`/`total_risk_score`, run full `run_a2118` with production NCF
params. Thresholds swept: 0.40, 0.45, 0.50, 0.55, 0.60.

**Result: zero effect at every threshold.** `defensive_days_delta = 0` and
all metric deltas = 0.0 in all 5 variants. The days ncf_2330 flags as
tail-risk-elevated never happen to coincide with `total_risk_score` sitting
exactly one point below the require-6 gate in this window — the existing
12+2 chip/derivative flags dominate the score.

Output: `results/ncf_2330_total_risk_score_overlay_sweep_20260705.json`.

## Attempt 3: Re-entry veto (asymmetric use, fits a2118's "never fully exit" philosophy)

Rationale: only delay re-entry from the NCF late-bull hedge back to golden1
(never trigger a new hedge entry) if ncf_2330's own tail risk is still
elevated when 00631L's own H5 signal would otherwise exit the hold.

Script: `scripts/misc/ncf_2330_reentry_veto_sweep.py`. Reimplements a2118's
`h5_reentry_min>0` hold state machine (production doesn't use
`gain_prob_soft_min`/`rally_suppress_min`, so those branches were omitted)
with a veto condition added on the exit path. Sanity check (`veto_max=1.01`,
should never fire) reproduced the real `_apply_late_bull_overlay` baseline
exactly — confirms the reimplementation is faithful. Thresholds swept: 0.40,
0.45, 0.50, 0.55, 0.60.

**Result: veto never fires at any threshold** (`vetoed_exit_days: []` for
all 5). a2118's late-bull hedge only triggered once in the entire
2025-01-02~2026-07-03 window (5 total hedge/hold days), and on the actual
exit day, ncf_2330's tail risk was already low — the sample is too small and
too rare to test this idea meaningfully.

Output: `results/ncf_2330_reentry_veto_sweep_20260705.json`.

## Side investigation: `switch_backtest.json` anomaly (reverted, unresolved origin)

Found `report/group_a_plus/latest/switch_backtest.json` (the legacy A20.7
compatibility report; `strategy.json` confirms "legacy_pointer_unchanged" —
not consumed by a2118/a2118's live execution) modified with an extended date
range (to 2026-07-03, was 2026-06-18) and four new but disabled `SwitchRule`
fields (`override_risk_score=0`, `override_drawdown_threshold=-0.05`,
`low_risk_exit_ma_gap=null`, `low_risk_exit_score_threshold=1`). Compared
old vs. new `recommended` metrics: final_value +1.3%, but **Sharpe -0.072,
Sortino -0.091, volatility up, max_drawdown unchanged to 10 decimal places**
— not an improvement, more consistent with the same rule re-run over a
slightly longer window. Origin (which script/run produced this) was not
traced. **Reverted to HEAD via `git checkout --`.** If the extended window is
wanted for its own sake later, regenerate it deliberately with a named
output path rather than overwriting the compatibility report silently.

## Attempt 4: Sweep the two dormant `SwitchRule` fields directly (`override_risk_score`, `low_risk_exit_ma_gap`)

The anomaly above surfaced two fields that exist in the `SwitchRule`
dataclass (`backtest_group_a_plus_switch_policy.py`) but are left at
disabled defaults in `_build_switch_rule()` (`group_a_plus/runners/a2111.py`,
used by both a2111 and a2118):
- `override_risk_score` / `override_drawdown_threshold`: bypass the MA-gap
  price-entry check and enter defensive purely on
  `total_risk_score >= override_risk_score AND drawdown <= override_drawdown_threshold`.
  0 = disabled (current production state).
- `low_risk_exit_ma_gap` / `low_risk_exit_score_threshold`: once
  `total_risk_score <= low_risk_exit_score_threshold`, use a smaller
  (faster) exit MA-gap instead of the normal one. `None` = disabled (current
  production state).

Script: `scripts/misc/a2118_switch_rule_override_lowrisk_exit_sweep.py`.
Method: monkeypatch `_build_switch_rule` inside `group_a_plus.runners.a2118`'s
own namespace, run full `run_a2118` with production NCF params, 2025-01-02 ~
2026-07-03.

**`override_risk_score`** (5 risk scores × 4 drawdown thresholds = 20
combos): **0/20 genuine improvements.** Every combo that actually fires
(`defensive_days_delta > 0`) makes things worse: final_value -$84k to -$373k,
Sharpe/Sortino down, and **max_drawdown often gets *worse*, not better** (up
to -3.48pp), because the extra entries catch short-lived pullbacks that
later recover, in this bull-skewed sample.

**`low_risk_exit_ma_gap`** (4 gaps × 4 score thresholds = 16 combos): 12/16
technically "improve" but by an identical, flat +$3,607 (+0.17%) / +0.0036
Sharpe in every one of the 12, with **`defensive_days_delta = 0` in every
single variant** — one historical event shaved a day or two off a re-entry
timing, not a systematic effect. Not statistically meaningful, not worth the
added parameter surface.

Output: `results/a2118_switch_rule_override_lowrisk_exit_sweep_20260705.json`.

## Attempt 5: Test `override_risk_score` on the 2008 TWII proxy (a genuine crash sample)

Part 1 — confirm it's untestable as specified: `override_enter` reads
`total_risk_score`, which (per `GROUP_A_PLUS_A2118_CHIP_FALLBACK_HANDOFF_20260704.md`
and `market_state_2008_proxy_backtest.py`'s existing assertion) is stuck at 0
for the entire 2008 proxy window — no chip/derivative tables exist that far
back. Confirmed empirically: 3 thresholds (6, 8, 10) all produce identical
436 defensive days. `override_risk_score` literally cannot be evaluated on
this data.

Part 2 — substitute `tail_risk_score` (purely price/return-derived:
historical-VaR breach + realized-vol-ratio regime, range 0-2, proven NOT
stuck at 0 in 2008) for `total_risk_score` in the same override logic, as
the only available way to ask the intended question. Script:
`scripts/misc/a2118_override_risk_2008_proxy_test.py`.

**Result: a genuine improvement, in a very narrow band.** At
`tail_risk_score >= 1` and `drawdown <= -8% or -10%` (only **3 extra days**
of earlier entry vs. the already-promoted `chip_data_fallback` baseline):

| Defense variant | Final value | Max drawdown |
|---|---:|---:|
| Cash, baseline → override | 4.79x → **5.14x (+7.2%)** | -20.9% → **-15.2% (+5.7pp)** |
| 00632R hedge, baseline → override | 9.16x → **10.16x (+10.9%)** | -22.8% → **-15.9% (+6.9pp)** |

At a looser trigger (`drawdown <= -5%`, 23 extra days), the cash-defense
variant still improves but the 00632R-hedge variant's max_drawdown gets
*worse* (-22.8% → -25.0%) — over-triggering adds whipsaw cost. At
`tail_risk_score >= 2` (stricter), it never fires differently from baseline
at any drawdown threshold tested.

Output: `results/a2118_override_risk_2008_proxy_test_20260705.json`.

## Cross-check: same mechanism on real 2025-2026 data

Before treating Attempt 5's result as informative, tested the *identical*
mechanism and thresholds (`tail_risk_score >= 1`, `drawdown <= -8%/-10%`,
bypassing all entry gates) on real 2025-01-02~2026-07-03 data. Script:
`scripts/misc/a2118_tail_risk_override_2025_2026_crosscheck.py`.

**Result: pure cost, no benefit.** 11 or 3 extra defensive days
respectively; final_value -$91.6k to -$113.9k (-4.3% to -5.3%); Sharpe -0.066
to -0.074; **max_drawdown delta = 0.0 in both cases** — the mechanism never
touches the real 2025-2026 max-drawdown day, it only catches false alarms
that later recovered.

Output: `results/a2118_tail_risk_override_2025_2026_crosscheck_20260705.json`.

## Consolidated Conclusion

This is the same tension already documented in
`GROUP_A_PLUS_FABLE_AUDIT_MARKET_STATE_ARBITRATION_HANDOFF_20260704.md`'s
Decision Item A (`market_state.py`'s `crash_risk` classifier: 2025-2026 says
"hold beats defending", 2008 proxy says the opposite), now independently
reproduced via a completely different technical mechanism
(`SwitchRule.override_risk_score`, substituting `tail_risk_score`). Two
different diagnostic approaches, same two samples, same contradiction. This
strengthens (rather than merely repeats) the earlier conclusion:

- **Root cause is not a modeling gap fixable by better tuning.** Early-stage
  normal corrections and early-stage genuine crashes are close to
  indistinguishable in this project's price/volatility-only signals
  (`ma_gap`, `drawdown`, `tail_risk_score`) — the first few days look
  statistically similar regardless of what follows.
- The mechanism that *conceptually* should discriminate them —
  `total_risk_score` (institutional/foreign capital flow + derivatives
  positioning) — has never actually been validated against a real crash,
  because Taiwan chip/derivative data does not exist in this project's DB
  far enough back to cover 2008. This is a **data availability limitation**,
  not evidence the concept is wrong.
- A real improvement here would require a new data dimension not currently
  in this project (credit spreads, VIX-equivalent, USD/TWD, cross-asset
  confirmation), not another sweep of existing price-derived thresholds
  using the same two samples.
- **Recommendation: stop iterating on this with current data.** Both
  samples are real ((one real 1.5-year bull run, one TWII proxy for a single
  historical crash) but small and directionally opposed — further
  parameter search over the same two samples is more likely to overfit to
  noise than find a genuine edge.

## ncf_2330 status (unchanged from before this session)

Remains advisory-only: feeds `signal_alignment` (10th/11th source) and
alert messages (`tsmc_led_narrow_reference`, `tsmc_weak_manual_review`); has
**zero effect on portfolio weights**, confirmed correct/intentional now
after three independent rejected attempts to give it weight-level influence
(direct trim, total_risk_score component, re-entry veto). See
`project_ncf_2330_tsmc_stock_model_20260703` for the model's own 4-round
validation history (tail risk is the only surviving signal; direction was
falsified).

## Files Produced This Session

New research scripts (all read-only w.r.t. production code — monkeypatch
in-process, never edit files on disk):
- `scripts/misc/ncf_2330_total_risk_score_overlay_sweep.py`
- `scripts/misc/ncf_2330_reentry_veto_sweep.py`
- `scripts/misc/a2118_switch_rule_override_lowrisk_exit_sweep.py`
- `scripts/misc/a2118_override_risk_2008_proxy_test.py`
- `scripts/misc/a2118_tail_risk_override_2025_2026_crosscheck.py`

New result files:
- `results/ncf_2330_total_risk_score_overlay_sweep_20260705.json`
- `results/ncf_2330_reentry_veto_sweep_20260705.json`
- `results/a2118_switch_rule_override_lowrisk_exit_sweep_20260705.json`
- `results/a2118_override_risk_2008_proxy_test_20260705.json`
- `results/a2118_tail_risk_override_2025_2026_crosscheck_20260705.json`

## No Production Changes

`daily_signal.py`'s mid-session edit (wiring `_apply_tsmc_weakness_trim`)
was reverted. `report/group_a_plus/latest/switch_backtest.json`'s
mid-session-discovered change was reverted via `git checkout --`. No other
production file (`a2118.py`, `market_state.py`, `signal_alignment.py`,
`a2111.py`, `group_a_plus_config.json`, `report/group_a_plus/latest/strategy.json`)
was modified during this session — those files' pending changes are all
carried over from the prior (2026-07-04) session and are still uncommitted;
see "Open item: uncommitted work" below.

## Open Item: Uncommitted Work (carried over, not resolved this session)

As of this session's end, `git status` still shows the following, grouped
by the plan discussed with the user but not yet executed:

1. **a2118 chip-data-outage fallback fix** (verified, recommended to commit):
   `backtest_group_a_plus_switch_policy.py`, `group_a_plus/runners/a2118.py`,
   `report/group_a_plus/latest/strategy.json`,
   `tests/test_backtest_group_a_plus_switch_policy_chip_fallback.py`,
   `GROUP_A_PLUS_A2118_CHIP_FALLBACK_HANDOFF_20260704.md`,
   `scripts/misc/a2118_chip_fallback_2008_proxy_verify.py`,
   `scripts/misc/a2118_chip_fallback_threshold_sweep.py`.
2. **market_state.py + daily_signal.py diagnostic fixes + ncf_2330 advisory
   wiring** (verified, recommended to commit): `group_a_plus/operations/market_state.py`,
   `group_a_plus/operations/daily_signal.py`, `group_a_plus/integrations/signal_alignment.py`,
   `tests/test_group_a_plus_market_state.py`, `tests/test_group_a_plus_daily_signal_v2.py`,
   `tests/test_group_a_plus_latest_strategy.py`, `tests/test_group_a_plus_signal_alignment.py`,
   `GROUP_A_PLUS_FABLE_AUDIT_MARKET_STATE_ARBITRATION_HANDOFF_20260704.md`,
   `scripts/misc/market_state_persistence_backtest.py`,
   `scripts/misc/market_state_2008_proxy_backtest.py`.
3. **ncf_2330 research history** (shadow-only, record-keeping): `ncf_2330.py`,
   three `NCF_2330_*HANDOFF*.md` files, `GROUP_A_PLUS_NCF2330_20260703_DATA_HANDOFF_20260704.md`,
   `scripts/misc/ncf_2330_round4_txo_trend.py`, `scripts/misc/ncf_2330_tail_risk_sweep.py`,
   plus this session's `scripts/misc/a2118_ncf_2330_tsmc_overlay_sweep.py` and the
   five new scripts/results listed above.
4. **2008 shadow candidate research** (already rejected, record-keeping):
   `GROUP_A_PLUS_2008_SHADOW_CANDIDATE_2025_2026_VERIFY_HANDOFF_20260703.md`,
   `scripts/misc/verify_2008_shadow_candidate_2025_2026.py`.
5. **Unrelated FinRL work** (pre-dates this session, independent of Group A+):
   `FinRL/OPTIMIZATION_LOG.md`, `FinRL/data/stock_db.py` (SQL-injection fix),
   `FinRL/data/technical_indicators.py`.

Full test suite verified healthy at session end (run twice, consistent):
**568 passed, 9 skipped.** The user has not yet decided whether/how to split
these into commits — next session should resume from this list rather than
re-deriving it.
