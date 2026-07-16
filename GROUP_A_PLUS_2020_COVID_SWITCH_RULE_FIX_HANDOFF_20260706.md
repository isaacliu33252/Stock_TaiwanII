# GroupA+ 2020 COVID Switch-Rule Fix Handoff - 2026-07-06

## Status

**IMPLEMENTED IN PRODUCTION.** A candidate fix to the A21.18 switch rule
cleared the formal promotion gate for the first time this session, and was
then wired into the live runner per explicit user decision:

- Multi-window gate: `candidate_available`, 6/6 windows pass
  (`results/group_a_plus_momentum_fast_exit_final_multi_window_gate_20260706.json`)
- Promotion gate: `promotion_ready`
  (`results/group_a_plus_momentum_fast_exit_final_promotion_gate_20260706.json`)
- **Implemented**: `backtest_group_a_plus_switch_policy.py`'s `_switch_returns`
  gained three new opt-in parameters (`risk_score_lookback_days`,
  `momentum_fast_exit_min`, `momentum_fast_exit_ma_gap_min`; all default
  `None`, zero behavior change for every other existing caller --
  A21.11/a207/etc. are unaffected). `group_a_plus/runners/a2118.py` now
  passes these with defaults `5` / `0.10` / `-0.08` into its own
  `_switch_returns` call, and exposes matching CLI flags
  (`--risk-score-lookback-days` / `--momentum-fast-exit-min` /
  `--momentum-fast-exit-ma-gap-min`). Also recorded in the report's `rules`
  dict for audit visibility.
- a2120-a2126 (shadow candidates that wrap `run_a2118`) inherit this fix
  automatically -- none of them override the three new parameters.
- Full test suite after implementation: `639 passed, 9 skipped, 0 failed`
  (`.venv/bin/python -m pytest -q tests/`, 648 tests total, ~47 min).
- Manual live-signal spot check post-implementation:
  `today_regime=golden1`, new params correctly present in the runner report
  (`risk_score_lookback_days=5`, `momentum_fast_exit_min=0.1`,
  `momentum_fast_exit_ma_gap_min=-0.08`).

## Origin: Five-Crisis Backtest

This started from a broader request to backtest GroupA+'s latest production
strategy and golden1_0531 across five historical crises (2008 GFC, 2011
European debt crisis, 2015 China A-share crash, 2018 US-China trade war,
2020 COVID crash). New data-prep scripts were added for 2015 (real ETF OHLCV,
available from 2015-01-05) and 2018 (TWII index proxy, since real ETF OHLCV
has a hard gap 2017-2019):

- `scripts/misc/prepare_2015_china_crash_data_20260706.py`
- `scripts/misc/prepare_2018_trade_war_twii_proxy_data_20260706.py`
- `scripts/misc/backtest_group_a_plus_latest_vs_golden1_0531_five_crises_20260706.py`

Only 2008 showed the switch rule providing real protection (340 defensive
days, MDD -62%->-37% vs golden1_0531 buy-and-hold). 2011/2015/2018/2020 all
showed **zero** defensive days -- the rule never triggered at all in those
folds under the current production configuration.

## Root Cause 1 (Entry Side): Same-Day Signal Misalignment

Direct inspection of the 2020 Feb-Apr window found `total_risk_score` peaked
at 6 (the rule's `require_total_risk_score` threshold) on 2020-03-06, while
`drawdown` only reached -10.4% that day (short of the -11% `enter_drawdown`
threshold). By 2020-03-09, drawdown had breached -11% (falling to -30% by
2020-03-19), but `total_risk_score` had already faded under 6 and never
returned. Checked day-by-day 2020-02-15..2020-04-15: `price_enter AND
total_risk_ok` was never simultaneously True on any single day. This is a
timing-alignment defect, not a chip-data-availability problem
(institutional_data/margin_data/taifex_options_daily are all real for 2020).

**Fix**: relax `total_risk_ok` to a rolling max of `total_risk_score` over
the last 5 trading days (inclusive) instead of only today's value.

- `scripts/misc/evaluate_risk_score_lookback_candidate_20260706.py`
  (`_switch_returns_risk_lookback`)

Result at lookback=5: 2020 now triggers (27 defensive days), MDD -30.97% ->
-19.64%\* (see correction below), Sharpe 1.253 -> 1.439\*. 2008/2011/2015/2018
and the current 2025-2026 live window: bit-identical to baseline (zero side
effects).

\* These first-pass numbers were later found to be inflated by Bug 1 below.

## Bug Found and Fixed: 00679B.TWO Flattened for the Whole 2020 Test Window

`_load_real_2020_prices_with_00679b_backfill` (in the five-crises script)
originally queried 0050/00631L/00632R only, then set the ENTIRE 00679B.TWO
column to a single constant (its first-ever real price), instead of only
back-filling the pre-2020 lead-in gap. This flattened 00679B (a 30-40%
weight in the defensive basket) for 2020 itself too, where real, varying
00679B prices exist and matter. Caught by noticing `bond30_cash30` and
`bond40` baskets produced bit-identical 2020 metrics despite different
00679B weights -- only possible if 00679B carried zero real variance that
year.

**Fixed**: query all four tickers together over the full range and
`.bfill()` 00679B (matches `scripts/misc/garch_specialist_routing_2020_fold_
20260705.py`'s established precedent). Corrected lookback=5 numbers: final
value 1,890,964 (was 1,921,708), MDD -24.05% (was -19.64%), Sharpe 1.294 (was
1.439) -- the true cost is worse than first reported. Also caught and fixed
a second instance of the same class of bug (missing
`chip_data_fallback_max_stale_days=10` on a manually-reconstructed baseline
curve) later in the session -- see Verification section.

## Gate Result After Root Cause 1 Only: Blocked

`results/risk_score_lookback_multi_window_reports_20260706/*.json` +
`results/group_a_plus_risk_score_lookback_multi_window_gate_20260706.json`:
5/6 windows pass, 2020 fails `final_value_drag` (-4.65%, exceeds the -2%
governance floor). Decision: `research_only_no_multi_window_pass`.

Swept `DEFENSIVE_BASKETS` alternatives (cash30/bond20/bond40/cash40) at
lookback=5 -- `scripts/misc/evaluate_risk_score_lookback_basket_sweep_
20260706.py`. None cleared -2%; best (cash40) was -4.01%, still ~2x over
budget, and more-aggressive baskets made MDD worse, not better. Conclusion:
the defensive-basket *composition* was never the problem -- the cost was
structural: once entered, the rule doesn't exit until `ma_gap` recovers to
+1%, and during a fast V-shaped rebound that recovery lags the actual price
action by weeks, no matter what you hold while waiting.

## Root Cause 2 (Exit Side): Momentum Recovers Weeks Before ma_gap

With entry now firing on 2020-03-09 (lookback=5), inspecting the subsequent
defensive window found `exit_momentum` (5-day 0050 return) turned positive
on 2020-03-25 (+5.6%) and spiked to +12.6% on 2020-03-26 -- three weeks
before `ma_gap` finally cleared the existing `exit_ma_gap=0.01` threshold on
2020-04-17 (the actual exit date). The existing exit condition requires
`ma_gap >= exit_ma_gap AND exit_momentum > 0` (same day); during a fast
rebound, momentum recovers far faster than a 100-day MA gap ever can.

**First fix attempt**: add an independent fast-exit path -- exit immediately
(once `min_hold_days` met) if `exit_momentum >= momentum_fast_exit_min`,
regardless of `ma_gap`.

- `scripts/misc/evaluate_momentum_fast_exit_candidate_20260706.py`

At `momentum_fast_exit_min=0.10`: 2020 final value 1,986,790 (beats the
no-switch baseline 1,983,244), Sharpe 1.512, MDD -24.05%. But this also
fired once in 2008 on 2008-11-03 (+14.4% 5-day return -- **higher** than
2020's own +12.6% trigger), a well-documented dead-cat bounce deep in the
GFC bear market (that day: ma_gap=-23.7%, drawdown=-39.2%). Pure momentum
magnitude cannot distinguish a genuine V-recovery from a bear-market trap --
2008's bounce was literally bigger.

**Refinement**: `ma_gap` does separate them cleanly. 2020-03-26 (genuine
recovery): ma_gap=-4.4%. 2008-11-03 (trap): ma_gap=-23.7%. 2011's two
similarly-genuine fast-exit candidates (2011-10-13, 2011-12-26): ma_gap=-8.3%
and -3.1%. Added `momentum_fast_exit_ma_gap_min` as a required co-condition.

- `scripts/misc/evaluate_momentum_fast_exit_ma_gap_guard_sweep_20260706.py`

Swept the guard at -0.05/-0.08/-0.10/-0.15 (momentum threshold fixed at
0.10): all four values give identical results -- 2008/2011 revert exactly to
clean baseline (2008-11-03 excluded), 2020 keeps the fix (2020-03-26 still
fires), and in the current live 2025-2026 window the guard also correctly
suppresses a spurious fast-exit candidate that fired without it (2025-04-16),
reverting live to bit-identical baseline. Chose `-0.08` as the final value
(comfortably inside the -0.05..-0.15 robust range).

## Final Candidate

`momentum_fast_exit_min=0.10`, `momentum_fast_exit_ma_gap_min=-0.08`, on top
of the already-established `risk_lookback_days=5`.

- `scripts/misc/evaluate_momentum_fast_exit_final_candidate_20260706.py`

| Window | Baseline Final | Candidate Final | Baseline Sharpe | Candidate Sharpe | Baseline MDD | Candidate MDD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2008 GFC | 2,225,418 | 2,225,418 | 0.418 | 0.418 | -37.45% | -37.45% |
| 2011 Euro debt | 1,074,134 | 1,074,134 | 0.087 | 0.087 | -22.02% | -22.02% |
| 2015 China crash | 1,086,121 | 1,086,121 | 0.286 | 0.286 | -16.39% | -16.39% |
| 2018 Trade war | 1,467,506 | 1,467,506 | 0.513 | 0.513 | -16.27% | -16.27% |
| **2020 COVID** | 1,983,244 | **1,986,790** | 1.253 | **1.512** | -30.97% | **-24.05%** |
| Live 2025-2026 | 2,086,287 | 2,086,287 | 2.422 | 2.422 | -14.45% | -14.45% |

Five of six windows are bit-identical to production (zero side effects).
2020 improves on every metric simultaneously (final value, Sharpe, MDD) --
not a risk/return trade-off, an outright dominance.

## Gate Results

Multi-window gate (`results/group_a_plus_momentum_fast_exit_final_multi_window_gate_20260706.json`):

- Decision: `candidate_available`
- All three variants (`best_by_final_value`/`best_by_max_drawdown`/`best_by_sharpe`, all identical here since there is only one real candidate): `multi_window_pass`, 6/6

Promotion gate (`results/group_a_plus_momentum_fast_exit_final_promotion_gate_20260706.json`):

- Decision: **`promotion_ready`**
- Metrics gate: `pass` (3/3 formal_upgrade_pass, comparing the 2020 window only -- the only window with a real delta)
- Panel drift gate: `not_required` (this candidate has nothing to do with NCF panels; `--no-require-drift-audit` used)
- Multi-window gate: `pass`

This is the first candidate in this project's history (per prior handoffs:
2008 stress shadow, chip-fallback tuning, NCF2330 switch-rule integration
attempts, GARCH specialist routing) to clear the formal promotion gate
cleanly.

## What This Is Not

- **Not validated on other real crash episodes beyond these six windows.**
  The ma_gap guard's robust range (-0.05..-0.15) was found on exactly the
  data available this session (2008/2011/2015/2018/2020/current live); it is
  not guaranteed to generalize to a crash shape not seen here.
- **This was a real production change**, not a diagnostic-only addition
  (unlike e.g. `market_state.py`'s arbitration design) -- it changes live
  a2118 behavior during any future fast crash. Per
  [[feedback_strategy_promotion_caution]] (this project's standing rule:
  a2214 was reverted after being promoted on Sharpe alone in 2026-07-02),
  clearing the automated gate was treated as necessary, and the user's
  explicit "導入" (implement it) instruction on 2026-07-06 was the actual
  authorization to change the live runner -- not the gate result alone.
- No unit tests were added pinning the 2008-11-03 exclusion / 2020-03-26
  inclusion as regression guards (see Recommended Next Steps).

## Recommended Next Steps

1. ~~Add unit tests pinning the 2008-11-03 exclusion and the 2020-03-26
   inclusion as regression guards~~ -- **done**, see Regression Tests below.
2. Consider testing the guard's robustness on any additional historical
   crash windows if more real/proxy data becomes available, before treating
   the -0.05..-0.15 range as settled.
3. ~~Update `report/group_a_plus/latest/strategy.json`'s `runner_params`~~ --
   **done**. Added `risk_score_lookback_days`/`momentum_fast_exit_min`/
   `momentum_fast_exit_ma_gap_min` to `runner_params`, plus a new
   `switch_rule_2020_covid_fix_20260706` entry under `improvements`
   recording the root causes, params, validation results, and per-window
   impact (matches the file's existing dated-entry convention). Verified:
   `group_a_plus.governance.latest.resolve_latest()` still resolves cleanly,
   and `tests/test_group_a_plus_latest_strategy.py` +
   `test_group_a_plus_strategy_signature.py` + `test_group_a_plus_daily_
   signal_v2.py` + `test_run_ncf_daily_pipeline.py` (73 tests) all still
   pass.

## Regression Tests

`tests/test_backtest_group_a_plus_switch_policy_2020_fix.py` (new, 5 tests,
synthetic price/chip fixtures, no DB access, ~9s):

- `test_entry_never_fires_when_risk_score_and_drawdown_never_align` --
  reproduces the entry-side bug at baseline (no lookback).
- `test_risk_score_lookback_catches_delayed_price_confirmation` -- confirms
  `risk_score_lookback_days=5` fixes it.
- `test_momentum_fast_exit_recovers_earlier_than_ma_gap_on_genuine_rebound`
  -- shallow-pullback/genuine-recovery shape (mirrors 2020-03-26): fast-exit
  releases one trading day earlier than the baseline ma_gap-only exit.
- `test_momentum_fast_exit_ma_gap_guard_blocks_dead_cat_bounce` -- deep-bear
  dead-cat-bounce shape (mirrors 2008-11-03): without the ma_gap guard, the
  bounce's momentum burst causes a costly 4-event whipsaw while the market
  keeps falling; with the guard, stays defensive through the entire
  continued decline (0 whipsaw events). This is the actual regression this
  fix must not reintroduce.
- `test_momentum_fast_exit_is_a_no_op_when_disabled` -- `momentum_fast_exit_
  min=None` (matching every existing caller) is bit-identical to omitting
  the parameter.

All 5 pass. Combined with the existing 130 directly-relevant tests
(a2112/a2118-family/chip-fallback/daily-signal/strategy-signature/etc.):
135 passed.

## Verification

```bash
.venv/bin/python -m py_compile \
  scripts/misc/prepare_2015_china_crash_data_20260706.py \
  scripts/misc/prepare_2018_trade_war_twii_proxy_data_20260706.py \
  scripts/misc/backtest_group_a_plus_latest_vs_golden1_0531_five_crises_20260706.py \
  scripts/misc/evaluate_risk_score_lookback_candidate_20260706.py \
  scripts/misc/evaluate_risk_score_lookback_basket_sweep_20260706.py \
  scripts/misc/evaluate_momentum_fast_exit_candidate_20260706.py \
  scripts/misc/evaluate_momentum_fast_exit_ma_gap_guard_sweep_20260706.py \
  scripts/misc/evaluate_momentum_fast_exit_final_candidate_20260706.py \
  scripts/evaluate/build_risk_score_lookback_multi_window_reports_20260706.py
```

All research scripts run standalone with `PYTHONPATH=.` (no pytest suite
added -- matches this repo's existing convention for one-off crisis-fold
research scripts, e.g. `garch_specialist_routing_2008_fold_20260705.py`, none
of which have companion tests either).

## Files

New:

- `scripts/misc/prepare_2015_china_crash_data_20260706.py`
- `scripts/misc/prepare_2018_trade_war_twii_proxy_data_20260706.py`
- `scripts/misc/backtest_group_a_plus_latest_vs_golden1_0531_five_crises_20260706.py`
- `scripts/misc/evaluate_risk_score_lookback_candidate_20260706.py`
- `scripts/evaluate/build_risk_score_lookback_multi_window_reports_20260706.py`
- `scripts/misc/evaluate_risk_score_lookback_basket_sweep_20260706.py`
- `scripts/misc/evaluate_momentum_fast_exit_candidate_20260706.py`
- `scripts/misc/evaluate_momentum_fast_exit_ma_gap_guard_sweep_20260706.py`
- `scripts/misc/evaluate_momentum_fast_exit_final_candidate_20260706.py`

Key results:

- `results/real_2015_china_crash_prepared_20260706_{prices,chip_features,manifest}.csv/json`
- `results/twii_proxy_2018_trade_war_prepared_20260706_{prices,chip_features,manifest}.csv/json`
- `results/group_a_plus_latest_vs_golden1_0531_five_crises_20260706.json`
- `results/group_a_plus_risk_score_lookback_candidate_20260706.json`
- `results/group_a_plus_risk_score_lookback_multi_window_gate_20260706.json`
- `results/group_a_plus_risk_score_lookback_basket_sweep_20260706.json`
- `results/group_a_plus_momentum_fast_exit_candidate_20260706.json`
- `results/group_a_plus_momentum_fast_exit_ma_gap_guard_sweep_20260706.json`
- `results/group_a_plus_momentum_fast_exit_final_candidate_20260706.json`
- `results/group_a_plus_momentum_fast_exit_final_multi_window_gate_20260706.json`
- `results/group_a_plus_momentum_fast_exit_final_promotion_gate_20260706.json`

All uncommitted, part of the same pending multi-session batch referenced by
`GROUP_A_PLUS_CODE_REVIEW_FIXES_HANDOFF_20260706.md` and
`GROUP_A_PLUS_FINAL_DECISION_MEMO_20260706.md`.

## Current Decision

Implemented. `group_a_plus/runners/a2118.py` (the active strategy per
`report/group_a_plus/latest/strategy.json`) now runs with
`risk_score_lookback_days=5`, `momentum_fast_exit_min=0.10`,
`momentum_fast_exit_ma_gap_min=-0.08` by default. Strategy pointer and model
weights are otherwise unchanged -- this only changes a2118's own
entry/exit timing logic. Full test suite green (639 passed, 9 skipped, 0
failed) after implementation.
