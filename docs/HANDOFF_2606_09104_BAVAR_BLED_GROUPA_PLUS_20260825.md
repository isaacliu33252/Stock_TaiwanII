# Handoff: 2606.09104 BAVAR-BLED for GroupA+

Date: 2026-08-25  
Project root: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main`  
Paper: `C:/Users/isaac/Downloads/2606.09104.pdf`  
Title: `Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman`  
Scope: GroupA+ / A21.18 import review, shadow experiments, and 00631L 4% micro-add follow-up.

## Final Decision

Do not change live weights.

Keep only these items:

- HAR-BAVAR prior as weekly shadow information only.
- Student-t / BLED tail adjustment as a review layer only.
- 00631L 4% micro-add as a weekly shadow monitor only.
- EXTREME-only 00631L staged ladder as manual-review candidate only.
- Daily EXTREME-state monitor inside the normal GroupA+ daily pipeline.

Do not import:

- full BAVAR-BLED-TD3 optimizer
- unconstrained Black-Litterman allocation
- short-selling
- full-allocation / fractional-share assumptions
- Transformer views
- CNN risk-aversion estimator
- auto-rebalance

Global decisions remain:

- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `replace_a2118 = false`
- `train_td3_or_bavar_bled_optimizer_now = false`

Latest active strategy remains:

- `a2118_a2111_ncf_late_bull_deleverage`

Latest context:

- as_of: `2026-08-25`
- market state: `bull_pullback_deep`
- execution regime: `golden1`
- current risk-aversion state from 2606.09104 transparent gate: `HIGH`
- same-day holdings snapshot is available for `2026-08-25`
- promotion/review remains blocked because latest risk-aversion state is `HIGH`, not `EXTREME`
- last EXTREME date: `2026-03-31`, 101 trading days before `2026-08-25`

Current authoritative holdings snapshot:

- source workbook: `taiwan_stock_20260825.xlsx`
- cash balance: `1,500,000`
- in-scope holdings: `0050.TW 4551`, `00631L.TW 580`, `00632R.TW 0`, `00679B.TWO 100`
- excluded positions: `0056.TW`, `00646.TW`, `00713.TW`, `00751B.TWO`, `00878.TW`

Current GroupA+ weights from the live inference snapshot:

- `0050.TW`: `0.23782049947708442`
- `00631L.TW`: `0.010068135054441872`
- `00632R.TW`: `0.0`
- `00679B.TWO`: `0.0012959074499891451`
- cash: `0.7508154580184846`

## Why Full Paper Method Was Not Promoted

The paper's full setup does not match GroupA+:

- paper universe is broad DJIA stocks; GroupA+ live tradable universe is small ETF regime allocation
- paper allows shorting and fractional shares; GroupA+ is long-only ETF/cash governance
- paper uses optimizer-generated weights; GroupA+ requires regime constraints and promotion gates
- paper assumes cost/slippage simplifications that are too loose for current execution governance
- paper's deep stack is expensive and unnecessary unless simpler fixed candidates show stable value

Therefore, the review imported only testable components:

- HAR-style BAVAR prior
- Student-t / elliptical tail review
- dynamic risk-aversion score
- fixed constrained candidate sweeps
- micro-add promotion gating

## Why Full BAVAR-BLED-TD3 Is Not Recommended Now

This is a deliberate stop decision, not an unfinished item.

The simplified experiments already isolated the usable edge:

- `EXTREME-only` is the only risk-aversion state with strong 00631L evidence.
- staged 00631L to `4%` is the best current candidate if and only if the daily monitor shows `EXTREME`.
- the useful operational artifact is a transparent gate plus low-turnover staged target, not an optimizer-generated allocation.

The evidence does not justify the full model:

- HAR-BAVAR prior has weak statistical ranking value but no standalone economic value.
- BAVAR direction filtering made the 00631L 4% candidate slightly worse on return and ES.
- HIGH regime is weak: historical hit rate is below 50%, so a more flexible optimizer may over-allocate in a regime where the fixed candidate is already unstable.
- full Black-Litterman/BLED optimization could produce mathematically low-risk but strategy-meaningless ETF mixes unless heavily constrained.
- current live blocker is `latest_state_not_extreme`, not lack of optimizer complexity.
- adding TD3/CNN/Transformer components would add training, parameter, drift, overfit, and promotion-governance burden without proven incremental economic value.

Full model components should stay closed unless all of these conditions are met:

- daily EXTREME monitor has accumulated enough live/shadow observations after `2026-08-25`
- staged 00631L review has repeated positive live-like shadow value
- same-day holdings and execution cost checks remain clean
- BAVAR/HAR or another paper-derived prior shows incremental OOS value over the transparent EXTREME gate
- a constrained optimizer design is specified that cannot create shorting, inverse/levered offset pairs, or target weights outside GroupA+ regime rules
- promotion governance explicitly approves reopening optimizer research

Until then, the correct action is:

- run the daily monitor
- do not train full BAVAR-BLED-TD3
- do not replace A21.18
- do not auto-rebalance
- only send staged 00631L to manual review when `risk_aversion_state == EXTREME`

## Files Added

Initial 2606.09104 experiments:

- `scripts/evaluate/build_group_a_plus_2606_09104_har_bavar_prior_shadow.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_bled_tail_adjustment_review.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_dynamic_risk_aversion_gate.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_monthly_update_cadence_review.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_risk_aversion_forward_shadow.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_har_horizon_extension_review.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_constrained_bled_allocation_review.py`

00631L micro-add follow-up:

- `scripts/evaluate/build_group_a_plus_2606_09104_00631l_micro_add_forward_shadow.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_00631l_micro_add_cap_sweep.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_00631l_micro_add_promotion_gate.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_0050_00631l_combo_sweep.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_00631l_4pct_weekly_shadow_monitor.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_promotion_gate_freshness_retry.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_00631l_4pct_regime_split.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_00631l_4pct_es_threshold_sensitivity.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_00631l_4pct_bavar_direction_filter.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_00631l_4pct_high_exclusion_gate.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_00631l_4pct_high_skip_comparison.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_00631l_4pct_extreme_only_forward_shadow.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_00631l_4pct_extreme_only_promotion_readiness.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_00631l_stage1_2pct_readiness.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_00631l_staged_ladder_readiness.py`
- `scripts/evaluate/build_group_a_plus_2606_09104_extreme_state_monitor.py`

Each script has a matching test in `tests/`.

## Current Latest Reports

- `report/group_a_plus/latest/2606_09104_har_bavar_prior_shadow.json`
- `report/group_a_plus/latest/2606_09104_bled_tail_adjustment_review.json`
- `report/group_a_plus/latest/2606_09104_dynamic_risk_aversion_gate.json`
- `report/group_a_plus/latest/2606_09104_monthly_update_cadence_review.json`
- `report/group_a_plus/latest/2606_09104_risk_aversion_forward_shadow.json`
- `report/group_a_plus/latest/2606_09104_har_horizon_extension_review.json`
- `report/group_a_plus/latest/2606_09104_constrained_bled_allocation_review.json`
- `report/group_a_plus/latest/2606_09104_00631l_micro_add_forward_shadow.json`
- `report/group_a_plus/latest/2606_09104_00631l_micro_add_cap_sweep.json`
- `report/group_a_plus/latest/2606_09104_00631l_micro_add_promotion_gate.json`
- `report/group_a_plus/latest/2606_09104_0050_00631l_combo_sweep.json`
- `report/group_a_plus/latest/2606_09104_00631l_4pct_weekly_shadow_monitor.json`
- `report/group_a_plus/latest/2606_09104_promotion_gate_freshness_retry.json`
- `report/group_a_plus/latest/2606_09104_00631l_4pct_regime_split.json`
- `report/group_a_plus/latest/2606_09104_00631l_4pct_es_threshold_sensitivity.json`
- `report/group_a_plus/latest/2606_09104_00631l_4pct_bavar_direction_filter.json`
- `report/group_a_plus/latest/2606_09104_00631l_4pct_high_exclusion_gate.json`
- `report/group_a_plus/latest/2606_09104_00631l_4pct_high_skip_comparison.json`
- `report/group_a_plus/latest/2606_09104_00631l_4pct_extreme_only_forward_shadow.json`
- `report/group_a_plus/latest/2606_09104_00631l_4pct_extreme_only_promotion_readiness.json`
- `report/group_a_plus/latest/2606_09104_00631l_stage1_2pct_readiness.json`
- `report/group_a_plus/latest/2606_09104_00631l_staged_ladder_readiness.json`
- `report/group_a_plus/latest/2606_09104_extreme_state_monitor.json`

## Experiment Results

### 1. HAR-BAVAR prior shadow

Report:

- `report/group_a_plus/latest/2606_09104_har_bavar_prior_shadow.json`

Decision:

- `use_as_regime_prior_shadow = true`
- `har_bavar_prior_has_oos_ranking_value = false`
- `train_td3_or_bavar_bled_optimizer_now = false`
- `target_weight_change_allowed = false`

Result:

- Rank IC positive but economic top-minus-bottom was negative.
- The prior is not strong enough to drive weights.

### 2. Student-t / BLED tail review

Report:

- `report/group_a_plus/latest/2606_09104_bled_tail_adjustment_review.json`

Decision:

- `use_as_tail_review_layer = true`
- `promote_bled_optimizer_to_live = false`
- `target_weight_change_allowed = false`

Result:

- Raw A21.18 target tail risk was flagged.
- BLED-like Student-t adjustment is useful for review, not for weight generation.

### 3. Dynamic risk-aversion gate

Report:

- `report/group_a_plus/latest/2606_09104_dynamic_risk_aversion_gate.json`

Decision:

- `allow_increase_risky_weight = false`
- `supports_current_cash_floor = true`
- `train_cnn_risk_aversion_now = false`

Result:

- Latest transparent risk state was `EXTREME` in the original gate report.
- Later cap/weekly reports using data through `2026-08-25` show latest state `HIGH`.
- This gate is useful as review context, but cannot change weights.

### 4. Update cadence review

Report:

- `report/group_a_plus/latest/2606_09104_monthly_update_cadence_review.json`

Decision:

- weekly cadence acceptable for shadow
- monthly cadence acceptable for shadow
- live trading cadence: false for daily, weekly, and monthly

Result:

- Weekly run is acceptable for monitoring.
- No live schedule was authorized.

### 5. Risk-aversion forward shadow

Report:

- `report/group_a_plus/latest/2606_09104_risk_aversion_forward_shadow.json`

High/Extreme result:

- events: `293`
- guarded beats raw hit rate: `0.433447`
- mean guarded 20d return: `0.006101`
- mean raw 20d return: `0.028063`
- guarded minus raw: `-0.021962`
- raw MDD was much worse, but return was better

Decision:

- `risk_aversion_forward_filter_has_economic_value = false`
- `supports_cash_floor_when_high_or_extreme = false`

Interpretation:

The state reduces risk but does not improve 20d return versus raw A21.18. It should not promote a live filter by itself.

### 6. HAR horizon extension

Report:

- `report/group_a_plus/latest/2606_09104_har_horizon_extension_review.json`

Decision:

- `har_horizon_extension_improves_economic_value = false`
- `promote_extended_har_prior_to_live = false`

Result:

- Adding 63d or 252d HAR horizons did not help.
- Keep paper's basic `1/5/22` HAR structure only as shadow reference.

### 7. Constrained BLED allocation review

Report:

- `report/group_a_plus/latest/2606_09104_constrained_bled_allocation_review.json`

Decision:

- `promote_constrained_candidate_to_live = false`
- `allow_00631l_add_from_this_review = false`

Result:

- Raw 70/30 and higher-risk candidates had return appeal, but tail/governance gates blocked them.
- This led to the fixed micro-add tests.

### 8. 00631L 5% micro-add forward shadow

Report:

- `report/group_a_plus/latest/2606_09104_00631l_micro_add_forward_shadow.json`

All-state:

- events: `1593`
- mean 20d excess return: `+0.2079%`
- hit rate: `65.79%`
- mean extra ES loss: `-0.2437%`

High/Extreme:

- events: `294`
- mean 20d excess return: `+0.2204%`
- hit rate: `58.84%`
- mean extra ES loss: `-0.2834%`

Decision:

- all-state value: true
- high/extreme value: false
- 5% rejected because ES extra loss exceeded the `-0.25%` gate

### 9. 00631L cap sweep

Report:

- `report/group_a_plus/latest/2606_09104_00631l_micro_add_cap_sweep.json`

Fixed caps:

- `2.5%`
- `3.0%`
- `4.0%`
- `5.0%`

Best passing high/extreme cap:

- `00631L 4%`
- candidate weights: `0050 30%`, `00631L 4%`, `cash 66%`

High/Extreme result for 4%:

- events: `294`
- mean 20d excess return: `+0.1762%`
- hit rate: `58.84%`
- mean extra MDD: `-0.4327%`
- mean extra ES: `-0.2266%`

Decision:

- `best_cap_for_promotion_review = 0.04`
- `allow_00631l_micro_add_from_this_sweep = false`
- `advance_to_promotion_gate = false`

Interpretation:

4% is the best shadow candidate, but the sweep itself cannot promote it.

### 10. Promotion gate

Report:

- `report/group_a_plus/latest/2606_09104_00631l_micro_add_promotion_gate.json`

Candidate:

- `0050 30%`
- `00631L 4%`
- `cash 66%`

Result:

- status: `blocked`
- after importing the `2026-08-25` workbook, same-day current weights are reliable
- remaining blocker: `micro_add_turnover_exceeds_limit`
- turnover for full target: `0.092111`
- estimated cost: `0.460557` bps

Decision:

- `candidate_ready_for_manual_promotion_review = false`
- `requires_signed_manual_approval = false`
- `allow_00631l_micro_add = false`

Interpretation:

The full target `0050 30% / 00631L 4% / cash 66%` is still blocked. The same-day holdings issue was fixed, but moving current `0050` from about `23.78%` to `30%` makes turnover too high. This is why later staged-ladder tests keep current `0050` unchanged and adjust only `00631L + cash`.

### 11. 0050 / 00631L / cash combo sweep

Report:

- `report/group_a_plus/latest/2606_09104_0050_00631l_combo_sweep.json`

Grid:

- 0050 base: `25%`, `30%`, `35%`, `40%`
- 00631L cap: `2.5%`, `3%`, `4%`, `5%`
- rest cash

Best passing high/extreme combo:

- `0050 30%`
- `00631L 4%`
- `cash 66%`

Result:

- Other higher-return candidates failed tail/MDD constraints.
- The cap sweep result was confirmed.

### 12. 4% weekly shadow monitor

Report:

- `report/group_a_plus/latest/2606_09104_00631l_4pct_weekly_shadow_monitor.json`

All weekly events:

- events: `338`
- mean 20d excess return: `+0.1612%`
- hit rate: `66.27%`
- mean extra ES: `-0.1985%`

Weekly high/extreme:

- events: `63`
- mean 20d excess return: `+0.1594%`
- hit rate: `58.73%`
- mean extra ES: `-0.2397%`

Decision:

- `keep_weekly_shadow_monitor = true`
- `allow_00631l_micro_add_from_monitor = false`
- `advance_to_promotion_gate = false`

Interpretation:

This is the main surviving artifact from the paper review.

### 13. Freshness retry gate

Report:

- `report/group_a_plus/latest/2606_09104_promotion_gate_freshness_retry.json`

Freshness check:

- required as_of: `2026-08-25`
- initial run had holdings snapshot as_of `2026-08-24`
- after importing `taiwan_stock_20260825.xlsx`, same-day holdings became available

Decision:

- `ready_for_manual_promotion_review = false`
- promotion gate still blocked after rerun because full target turnover exceeds limit
- `allow_00631l_micro_add = false`

Interpretation:

Freshness is no longer the main blocker. The remaining issue is target design: full `0050 30 / 00631L 4 / cash 66` is too much turnover from the actual portfolio.

### 14. 4% regime split

Report:

- `report/group_a_plus/latest/2606_09104_00631l_4pct_regime_split.json`

State results:

- LOW: excess return `+0.1949%`, hit rate `70.69%`
- MEDIUM: excess return `+0.1191%`, hit rate `62.50%`
- HIGH: excess return `+0.0492%`, hit rate `46.96%`
- EXTREME: excess return `+0.3797%`, hit rate `77.88%`

Decision:

- `high_extreme_regime_value_observed = true`
- `allow_00631l_micro_add_from_split = false`

Interpretation:

The 4% candidate is not uniformly good across risk states. EXTREME looks strong, but HIGH is weak and has hit rate below 50%. This prevents promotion.

### 15. ES threshold sensitivity

Report:

- `report/group_a_plus/latest/2606_09104_00631l_4pct_es_threshold_sensitivity.json`

Thresholds:

- ES gate `-0.20%`: fail
- ES gate `-0.25%`: pass
- ES gate `-0.30%`: pass

Decision:

- `tail_gate_fragile_to_threshold = true`
- `passes_all_tested_es_thresholds = false`
- `allow_00631l_micro_add_from_sensitivity = false`

Interpretation:

The 4% candidate is close to the tail-risk boundary. It is not robust enough for promotion.

### 16. BAVAR prior direction filter

Report:

- `report/group_a_plus/latest/2606_09104_00631l_4pct_bavar_direction_filter.json`

Baseline on BAVAR prediction dates:

- events: `361`
- mean 20d excess return: `+0.1636%`
- hit rate: `67.04%`
- mean extra ES: `-0.1861%`

BAVAR-allowed subset:

- events: `304`
- mean 20d excess return: `+0.1486%`
- hit rate: `66.12%`
- mean extra ES: `-0.1900%`

Decision:

- `bavar_filter_improves_return = false`
- `bavar_filter_improves_es = false`
- `bavar_direction_filter_has_value = false`
- `allow_00631l_micro_add_from_filter = false`

Interpretation:

HAR-BAVAR prior should not be used as a 00631L add gate. It made both return and ES slightly worse.

### 17. HIGH exclusion / HIGH-skip comparison

Reports:

- `report/group_a_plus/latest/2606_09104_00631l_4pct_high_exclusion_gate.json`
- `report/group_a_plus/latest/2606_09104_00631l_4pct_high_skip_comparison.json`

Decision:

- HIGH regime is not enough to enable 00631L add.
- EXTREME-only is the cleaner candidate.
- `target_weight_change_allowed = false`

Key comparison:

- all-state 4%: mean excess `+0.1663%`, extra ES `-0.1948%`
- skip-HIGH: mean excess `+0.1607%`, extra ES `-0.1688%`
- EXTREME-only active events: mean excess `+0.3797%`, hit rate `77.88%`

Interpretation:

HIGH is weak: it improves tail cost when skipped but does not add enough return confidence. This is why later review requires `risk_aversion_state == EXTREME`.

### 18. EXTREME-only forward shadow

Report:

- `report/group_a_plus/latest/2606_09104_00631l_4pct_extreme_only_forward_shadow.json`

Decision:

- historical EXTREME-only value exists
- latest candidate active today: false
- `target_weight_change_allowed = false`

Result:

- active EXTREME events: `113`
- active-event mean 20d excess return: `+0.3797%`
- hit rate: `77.88%`
- extra ES: about `-0.2237%`

Latest state:

- `2026-08-25`
- risk-aversion score: `65`
- state: `HIGH`

Interpretation:

EXTREME-only is the best surviving signal from the paper, but today is not EXTREME.

### 19. Stage 1 2% readiness

Report:

- `report/group_a_plus/latest/2606_09104_00631l_stage1_2pct_readiness.json`

Decision:

- stage 1 would be low-cost if EXTREME
- today remains blocked because latest state is `HIGH`
- `allow_00631l_stage1_add = false`

Current-to-stage-1 target:

- keep `0050.TW` at `0.23782049947708442`
- raise `00631L.TW` to `0.02`
- keep `00679B.TWO` at `0.0012959074499891451`
- reduce cash to `0.7408835930729265`

Execution review:

- turnover: `0.009932`
- estimated cost: `0.049659` bps
- state: `LOW_COST`

### 20. Staged ladder readiness

Report:

- `report/group_a_plus/latest/2606_09104_00631l_staged_ladder_readiness.json`

Decision:

- any stage ready if EXTREME: true
- best stage cap if EXTREME: `0.04`
- latest state allows stage: false
- `target_weight_change_allowed = false`

Best staged target if EXTREME:

- `0050.TW`: `0.23782049947708442`
- `00631L.TW`: `0.04`
- `00632R.TW`: `0.0`
- `00679B.TWO`: `0.0012959074499891451`
- cash: `0.7208835930729265`

Execution review:

- turnover: `0.029932`
- estimated cost: `0.149659` bps
- state: `LOW_COST`

Interpretation:

This staged 4% target is different from the blocked full target. It keeps current `0050` unchanged and only raises `00631L` from about `1.01%` to `4%`, funded by cash. It becomes a manual-review candidate only when the daily monitor shows `EXTREME`.

### 21. Daily EXTREME-state monitor

Report:

- `report/group_a_plus/latest/2606_09104_extreme_state_monitor.json`

Pipeline placement:

- added to `scripts/run/run_ncf_daily_pipeline.py`
- runs through `run_daily.bat`
- best-effort only; failure does not block daily live signal

Current result:

- as_of: `2026-08-25`
- latest state: `HIGH`
- latest score: `65`
- last EXTREME: `2026-03-31`
- calendar days since last EXTREME: `147`
- trading days since last EXTREME: `101`
- staged ladder best cap if EXTREME: `0.04`

Interpretation:

This is the current operational artifact. The daily question is not whether the paper replaces A21.18; it does not. The daily question is whether `risk_aversion_state == EXTREME` and staged 00631L should be sent to manual review.

## Commands

Run all initial and follow-up tests:

```bash
.venv/bin/python -m pytest \
  tests/test_build_group_a_plus_2606_09104_har_bavar_prior_shadow.py \
  tests/test_build_group_a_plus_2606_09104_bled_tail_adjustment_review.py \
  tests/test_build_group_a_plus_2606_09104_dynamic_risk_aversion_gate.py \
  tests/test_build_group_a_plus_2606_09104_monthly_update_cadence_review.py \
  tests/test_build_group_a_plus_2606_09104_risk_aversion_forward_shadow.py \
  tests/test_build_group_a_plus_2606_09104_har_horizon_extension_review.py \
  tests/test_build_group_a_plus_2606_09104_constrained_bled_allocation_review.py \
  tests/test_build_group_a_plus_2606_09104_00631l_micro_add_forward_shadow.py \
  tests/test_build_group_a_plus_2606_09104_00631l_micro_add_cap_sweep.py \
  tests/test_build_group_a_plus_2606_09104_00631l_micro_add_promotion_gate.py \
  tests/test_build_group_a_plus_2606_09104_0050_00631l_combo_sweep.py \
  tests/test_build_group_a_plus_2606_09104_00631l_4pct_weekly_shadow_monitor.py \
  tests/test_build_group_a_plus_2606_09104_promotion_gate_freshness_retry.py \
  tests/test_build_group_a_plus_2606_09104_00631l_4pct_regime_split.py \
  tests/test_build_group_a_plus_2606_09104_00631l_4pct_es_threshold_sensitivity.py \
  tests/test_build_group_a_plus_2606_09104_00631l_4pct_bavar_direction_filter.py \
  tests/test_build_group_a_plus_2606_09104_00631l_4pct_high_exclusion_gate.py \
  tests/test_build_group_a_plus_2606_09104_00631l_4pct_high_skip_comparison.py \
  tests/test_build_group_a_plus_2606_09104_00631l_4pct_extreme_only_forward_shadow.py \
  tests/test_build_group_a_plus_2606_09104_00631l_4pct_extreme_only_promotion_readiness.py \
  tests/test_build_group_a_plus_2606_09104_00631l_stage1_2pct_readiness.py \
  tests/test_build_group_a_plus_2606_09104_00631l_staged_ladder_readiness.py \
  tests/test_build_group_a_plus_2606_09104_extreme_state_monitor.py
```

Run surviving weekly monitor:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2606_09104_00631l_4pct_weekly_shadow_monitor.py
```

Run promotion freshness retry:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2606_09104_promotion_gate_freshness_retry.py
```

Run promotion gate after same-day authoritative holdings are imported:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2606_09104_00631l_micro_add_promotion_gate.py
```

Run staged ladder readiness:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2606_09104_00631l_staged_ladder_readiness.py
```

Run daily EXTREME-state monitor only:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2606_09104_extreme_state_monitor.py
```

Normal daily pipeline:

```bat
C:\Users\isaac\Downloads\Stock_taiwan2-main\Stock_taiwan2-main\run_daily.bat
```

The daily pipeline now includes these 2606.09104 best-effort steps:

- `paper_2606_09104_00631l_regime_split`
- `paper_2606_09104_00631l_staged_ladder_readiness`
- `paper_2606_09104_extreme_state_monitor`

## What To Do Next

Only do these:

1. Keep weekly shadow monitor running for `0050 30% / 00631L 4% / cash 66%`.
2. Import same-day authoritative holdings when available.
3. Rerun freshness retry.
4. Rerun promotion gate only if freshness passes.
5. Require signed manual approval even if promotion gate later becomes ready.

Do not do these unless explicitly reopened:

- BAVAR direction filter
- longer HAR horizons
- 5% 00631L micro-add
- higher 0050/00631L combo candidates
- full BAVAR-BLED optimizer
- Transformer/CNN/TD3 implementation

## Bottom Line

The only useful portfolio candidate discovered from this paper is:

- `0050.TW 30%`
- `00631L.TW 4%`
- `cash 66%`

It remains shadow-only because:

- promotion gate is blocked by stale holdings
- HIGH regime performance is weak
- ES threshold sensitivity is fragile
- BAVAR prior filter does not improve return or tail risk

Latest strategy is unchanged.
