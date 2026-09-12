# 2605.20636 Continuous Timing Review for GroupA+

Date: 2026-08-29  
Paper: `C:\Users\isaac\Downloads\2605.20636.pdf`  
Title: `Continuous Timing Signals for Growth-Defensive Style Allocation: Factor Attribution, Risk Matching, and Out-of-Sample Evidence`  
arXiv: `2605.20636v2`, paper date `2026-05-29`  
Author: Zheli Xiong

## Decision

Do not import the paper's continuous smooth-score allocation into GroupA+ latest strategy.

Do not change live target weights.

Do not open or increase `00632R.TW`.

Do not unlock `00631L.TW`.

Keep `Golden1_0531` unchanged.

The only adopted benefit is process-level validation discipline.

## Paper Summary

The paper allocates between a US growth/technology ETF basket and a US
defensive income/value ETF basket. It replaces discrete regime rules with a
continuous smooth score built from macro-market signals, then maps that score to
growth/defensive weights through a tanh function and EWMA smoothing.

The paper's stated goal is style timing, not discovery of a new standalone alpha
factor. Its useful engineering contribution is not the exact asset allocation
rule, but the validation discipline: matched benchmarks, walk-forward tests,
post-2022 robustness, crisis-independence checks, and transaction-cost
sensitivity.

## GroupA+ Applicability

Direct strategy import is blocked by asset-universe mismatch:

- paper universe: US growth/technology ETFs versus US defensive income/value ETFs;
- GroupA+ universe: `0050.TW`, `00631L.TW`, `00632R.TW`, `00679B.TWO`, cash;
- the paper does not solve leveraged ETF compounding, inverse ETF hedge
  eligibility, Taiwan liquidity, or GroupA+ live execution constraints.

Closest GroupA+ analogue:

- `A21.19 continuous defensive tilt`
- implemented in `scripts/evaluate/evaluate_a2119_continuous_defensive_tilt_shadow.py`
- detailed history in `GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md`

Final A21.19 state:

- continuous smooth-score replacement was not promoted;
- growth-crowding penalty was tested and rejected;
- HYG-SHY credit stress and VIX-credit interaction had some interesting shadow
  evidence but still remained unpromoted;
- no production target weights changed.

## What Was Imported

Adopted:

- multi-window OOS validation;
- walk-forward expanding / rolling discipline;
- crisis-independence check;
- transaction-cost / parameter sensitivity sweep;
- incremental-OOS admission rule for new signals and interaction terms.

Artifact:

- `GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`

This is process-only. It does not change weights or execution.

## What Was Rejected

Rejected for live import:

- continuous tanh-mapped growth/defensive timing score;
- replacing GroupA+ discrete regime state with this paper's smooth score;
- growth-crowding penalty as a live risk-off input;
- credit/VIX-credit components as live target-weight inputs;
- any immediate change to `00631L.TW`, `00632R.TW`, `00679B.TWO`, or cash.

## Latest Strategy Context

Latest reviewed preview:

- file: `results/group_a_plus_latest_strategy_predict_20260831_from_20260828_total1000000.json`
- requested date: `2026-08-31`
- actual data date: `2026-08-28`

Preview target weights:

- `0050.TW = 0.470000`
- `00631L.TW = 0.100388`
- `00632R.TW = 0.164782`
- `00679B.TWO = 0.000000`
- `cash = 0.264830`

2605.20636 does not validate changing these weights.

## Artifact

Implemented:

- `scripts/evaluate/build_group_a_plus_2605_20636_continuous_timing_review.py`
- `tests/test_build_group_a_plus_2605_20636_continuous_timing_review.py`
- `report/group_a_plus/latest/2605_20636_continuous_timing_review.json`
- `report/group_a_plus/latest/2605_20636_continuous_timing_review.md`
- `report/group_a_plus/2605_20636_continuous_timing_review/history/2605_20636_continuous_timing_review_20260828.json`

Command run:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2605_20636_continuous_timing_review.py --as-of 2026-08-28
```

Test run:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_2605_20636_continuous_timing_review.py
```

Result: `4 passed`.

## Experiment Scope Decision

For GroupA+ importability, the experiments/review are complete enough to make
the strategy decision.

This is not a full replication of every table in the paper. The unreproduced
parts are the author's exact US ETF basket backtests, factor-attribution suite,
and benchmark grid. Those validate the paper's growth/defensive US ETF universe,
not GroupA+'s `0050.TW` / `00631L.TW` / `00632R.TW` / `00679B.TWO` / cash
allocation rule.

GroupA+ evidence used:

- local PDF extraction and method review;
- existing A21.19 continuous defensive tilt lineage review;
- validation checklist adoption confirmation;
- latest strategy target-weight cross-check;
- live-promotion blocker audit.

Decision:

- `groupa_plus_importability_complete = true`
- `full_paper_replication_complete = false`
- `full_paper_replication_required_for_strategy_decision = false`
- `promote_continuous_score_to_live = false`

## Taiwan ETF Sensitivity Addendum

User asked whether a Taiwan ETF backtest is useful. It is useful for GroupA+,
and more relevant than reproducing the paper's US ETF tables.

Implemented a narrow Taiwan ETF endpoint sensitivity:

- script:
  `scripts/evaluate/evaluate_group_a_plus_2605_20636_taiwan_etf_sensitivity.py`
- report:
  `report/group_a_plus/latest/2605_20636_taiwan_etf_sensitivity.json`
- markdown:
  `report/group_a_plus/latest/2605_20636_taiwan_etf_sensitivity.md`

Tested endpoints:

- `0050_cash`: `0050.TW = 40%`, cash `60%`
- `0050_00679b_cash`: `0050.TW = 40%`, `00679B.TWO = 30%`, cash `30%`
- `0050_00631l_cash`: `0050.TW = 50%`, `00631L.TW = 10%`, cash `40%`

Windows:

- `2017-01-03..2026-08-28`
- `2020-01-02..2020-12-31`
- `2022-01-03..2022-12-30`
- `2024-01-02..2026-08-28`

Result:

- `0050_cash`: `0/4` triple-pass windows, average final-value delta
  `-139164.78`, average Sharpe delta `-0.364008`, average turnover delta
  `25.859151`
- `0050_00679b_cash`: `0/4` triple-pass windows, average final-value delta
  `-176700.52`, average Sharpe delta `-0.398113`, average turnover delta
  `55.516191`
- `0050_00631l_cash`: `0/4` triple-pass windows, average final-value delta
  `-115341.54`, average Sharpe delta `-0.347761`, average turnover delta
  `10.632059`

Best endpoint by the script's score is `0050_00631l_cash`, but it is only
least bad, not promotable. It still has `0/4` triple-pass windows, negative
average final-value delta, negative average Sharpe delta, and positive turnover
delta.

Decision unchanged:

- Taiwan ETF backtest is useful evidence.
- Continuous defensive timing still fails GroupA+ promotion.
- Do not change live target weights.
- Do not unlock `00631L.TW`.
- Do not open or increase `00632R.TW`.
- Keep `Golden1_0531` unchanged.

## Friction-Control Sweep Addendum

Because the Taiwan ETF sensitivity failed mainly through worse Sharpe and higher
turnover, a second shadow sweep tested whether friction controls could repair the
best endpoint (`0050_00631l_cash`).

Implemented:

- script:
  `scripts/evaluate/sweep_group_a_plus_2605_20636_taiwan_etf_friction_controls.py`
- report:
  `report/group_a_plus/latest/2605_20636_taiwan_etf_friction_controls.json`
- markdown:
  `report/group_a_plus/latest/2605_20636_taiwan_etf_friction_controls.md`

Sweep:

- endpoint: `0050_00631l_cash`
- no-trade band: `0.005`, `0.02`, `0.05`, `0.10`
- tilt update frequency: `1`, `5`, `10` trading days
- windows: same four Taiwan ETF sensitivity windows
- total runs: `48`

Result:

- all `12` band/frequency combinations were `0/4` triple-pass;
- best combo: `band0.1_freq5`;
- best average final-value delta: `81633.59`;
- best average Sharpe delta: `-0.206229`;
- best minimum MaxDD delta: `-0.044307`;
- best average turnover delta: `1.352798`.

Interpretation:

The friction controls reduce the damage and can make average final value
positive, but they still do not fix the core problem: Sharpe remains negative,
drawdown can still worsen, and no combination passes all windows. This turns the
`2605.20636` / A21.19 Taiwan ETF mapping from "failed endpoint" into "failed
after endpoint and friction-control rescue attempts."

Best-combo window diagnosis (`band0.1_freq5`):

- `full_available`: final-value delta `-53740.93`, Sharpe delta `-0.405702`,
  MaxDD delta `-0.044307`, turnover delta `0.444908`
- `covid_2020`: final-value delta `-22456.32`, Sharpe delta `-0.005760`,
  MaxDD delta `0.013733`, turnover delta `0.151103`
- `rate_hike_2022`: final-value delta `-14757.71`, Sharpe delta `-0.154759`,
  MaxDD delta `-0.006605`, turnover delta `0.730367`
- `recent_2024_2026`: final-value delta `417489.32`, Sharpe delta
  `-0.258695`, MaxDD delta `0.034425`, turnover delta `4.084816`

This confirms the rescue sweep is not a balanced improvement. The average
final-value gain comes from the recent bull/deleveraging window, while the
full-history, COVID, and 2022 windows remain negative on final value. Sharpe is
negative in every best-combo window.

Decision unchanged:

- `friction_controls_repair_signal = false`
- `promote_to_live = false`
- no target-weight change

## Blocking Reasons

- `a2119_shadow_candidate_not_promoted`
- `asset_universe_mismatch_growth_defensive_us_etfs_vs_groupa_plus_taiwan_letf_bond_cash`
- `continuous_score_replacement_of_discrete_regime_not_validated_for_latest_strategy`
- `credit_and_vix_credit_components_remain_shadow_only`
- `growth_crowding_penalty_tested_and_rejected`
- `high_turnover_risk_from_continuous_timing_style`
- `research_only_review_no_target_weight_change`

## Final Archive Record

User accepted the conclusion on 2026-08-30 and requested detailed records.

Final status:

- `archive_status = closed_for_groupa_plus_import`
- `recommended_default_next_action = do_not_rerun`
- `only_retained_benefit = validation_checklist_only`
- `live_strategy_change = none`
- `latest_strategy_weight_change_allowed = false`

Completed work:

- extracted and reviewed local PDF metadata/text;
- mapped the paper's continuous growth/defensive timing idea to the closest
  GroupA+ lineage, `A21.19`;
- confirmed prior A21.19 work had already tested and rejected the direct
  continuous smooth-score idea, no-trade-band rescue, lower update frequency,
  growth-crowding penalty, credit stress, and VIX-credit confirmation terms;
- created a formal 2605.20636 review artifact and tests;
- added explicit experiment-scope decision separating GroupA+ importability from
  full paper replication;
- ran a narrow Taiwan ETF endpoint sensitivity over `0050_cash`,
  `0050_00679b_cash`, and `0050_00631l_cash`;
- ran a friction-control rescue sweep over `48` Taiwan ETF shadow backtests;
- added best-combo window diagnosis and machine-readable failure diagnosis.

Artifacts to keep:

- `report/group_a_plus/latest/2605_20636_continuous_timing_review.json`
- `report/group_a_plus/latest/2605_20636_continuous_timing_review.md`
- `report/group_a_plus/latest/2605_20636_taiwan_etf_sensitivity.json`
- `report/group_a_plus/latest/2605_20636_taiwan_etf_sensitivity.md`
- `report/group_a_plus/latest/2605_20636_taiwan_etf_friction_controls.json`
- `report/group_a_plus/latest/2605_20636_taiwan_etf_friction_controls.md`
- `scripts/evaluate/build_group_a_plus_2605_20636_continuous_timing_review.py`
- `scripts/evaluate/evaluate_group_a_plus_2605_20636_taiwan_etf_sensitivity.py`
- `scripts/evaluate/sweep_group_a_plus_2605_20636_taiwan_etf_friction_controls.py`
- `tests/test_build_group_a_plus_2605_20636_continuous_timing_review.py`

Final empirical read:

- Taiwan ETF endpoint sensitivity: all three endpoints were `0/4` triple-pass;
- friction-control rescue: all `12` band/frequency combinations were `0/4`
  triple-pass;
- best rescue combo `band0.1_freq5` had positive average final-value delta but
  failed because Sharpe stayed negative, drawdown worsened in important windows,
  and the gain was concentrated in `2024-2026`;
- the best combo still lost final value in full-history, 2020 COVID, and 2022
  rate-hike windows.

Do not promote:

- continuous tanh-mapped defensive timing;
- replacement of GroupA+ discrete regime state;
- growth-crowding penalty;
- credit stress / VIX-credit interaction as live target-weight inputs;
- any automatic `00631L.TW` unlock;
- any automatic `00632R.TW` open/increase.

Reopen only if at least one of these changes:

- a new live failure specifically points to overly discrete defensive switching
  and cannot be handled by existing A21.18/A21.11/NCF controls;
- new Taiwan ETF data materially changes the 2020/2022/full-history result;
- a new candidate can reduce turnover and improve Sharpe without depending only
  on the `2024-2026` bull/deleveraging window;
- the user explicitly requests a fresh Taiwan ETF sensitivity run with new
  windows or a new endpoint.

## Final Answer

This paper has a useful advantage for GroupA+: its validation framework.

It does not currently have a useful live strategy component for GroupA+ latest
strategy. The continuous allocation idea has already been tested through A21.19
and remains rejected/unpromoted. Keep it as research/process guidance only.
