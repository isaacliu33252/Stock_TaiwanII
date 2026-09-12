# 2602.24037 SCR Readiness Review for GroupA+

Paper: `C:\Users\isaac\Downloads\2602.24037.pdf`  
Title: `Portfolio Reinforcement Learning with Scenario-Context Rollout`  
Authors: `Vanya Priscillia Bendatu; Yao Lu`  
arXiv: `2602.24037v1`, PDF date `2026-02-27`  
DOI: `https://doi.org/10.48550/arXiv.2602.24037`

## Paper Summary

The paper proposes macro-conditioned Scenario-Context Rollout (SCR) for
portfolio reinforcement learning. SCR generates plausible next-day multivariate
return scenarios under macro/stress contexts.

The paper's important warning is that using scenario rewards while bootstrapping
from tape-realized historical continuations creates a reward-transition
mismatch in temporal-difference learning. The authors address this by mixing in
a counterfactual continuation for the critic target.

Reported paper evidence:

- FinRL U.S. stocks/ETFs, 2009-2023;
- chronological split: train 2009-2017, validation 2018-2019, test 2020-2023;
- 31 universes across Market-Proxy, High-Vol, Low-Vol, and General groups;
- SCR-PPO-Full improved Market-Proxy Sharpe from `0.492` to `1.004`;
- Market-Proxy max drawdown improved from `0.370` to `0.179`;
- ablation `Gap_final` improved from `0.526` to `0.0001`;
- beta sensitivity favored a moderate `beta_cf`, with `0.50` strongest in the
  reported table.

## GroupA+ Mapping

Useful idea:

- scenario-context rollout is useful as a future RL/shadow-training readiness
  diagnostic;
- reward-transition mismatch should become a hard governance warning before any
  scenario reward is used with historical tape continuation;
- `beta_cf = A / (A + B)` can be used as a diagnostic for how much
  counterfactual continuation mixing would be implied by mismatch versus
  scenario variance.

Not imported:

- no SCR-PPO training;
- no PPO retraining;
- no model training;
- no target weights;
- no automatic rebalance;
- no direct `00631L`, `00632R`, or `00679B` trading rule.

Reason:

The paper's experiments are U.S. stock/ETF universes and require full RL
training. GroupA+ needs a Taiwan ETF OOS readiness audit first, especially
because existing governance has repeatedly blocked live RL/model promotion
without signed approval and independent OOS evidence.

## Implementation

Added:

- `scripts/evaluate/build_group_a_plus_2602_24037_scr_readiness_review.py`
- `tests/test_build_group_a_plus_2602_24037_scr_readiness_review.py`
- `report/group_a_plus/latest/2602_24037_scr_readiness_review.json`
- `report/group_a_plus/latest/2602_24037_scr_readiness_review.md`
- `report/group_a_plus/2602_24037_scr_readiness_review/history/2602_24037_scr_readiness_review_20260828.json`

Method:

- read paper metadata locally with `pypdf`;
- load `0050.TW`, `00631L.TW`, `00632R.TW`, `00679B.TWO` close data;
- read current `report/group_a_plus/latest/live_signal.json` target weights;
- create a simple market-context feature set:
  - `0050.TW` 1-day return;
  - `0050.TW` 20-day realized volatility;
  - `0050.TW` 5-day momentum;
  - `0050.TW` 60-day drawdown;
  - 60-day rolling correlations versus comparison ETFs;
- for each OOS date from `2024-01-02`, retrieve the nearest historical contexts;
- compare nearest-neighbor scenario mean next-day portfolio return with realized
  next-day portfolio return;
- compute scenario variance, mismatch MSE, and the paper-inspired
  `beta_cf = A / (A + B)` proxy.

This is not a paper-equivalent replication. It is a Taiwan ETF readiness audit
for whether SCR-style shadow work is even coherent enough to consider later.

## Real-Data Result

As of `2026-08-28`:

- status: `available_for_shadow_review`;
- OOS days: `643`;
- mean absolute scenario-real gap: `0.007926`;
- median absolute gap: `0.004396`;
- P90 absolute gap: `0.014028`;
- mean scenario variance: `0.0004747737`;
- mismatch MSE: `0.0015854717`;
- beta_cf proxy: `0.769555`;
- scenario-real gap gate passed: `true`;
- beta_cf moderate-range check: `false`.

Interpretation:

The Taiwan ETF nearest-neighbor scenario audit is not broken: the average
scenario-real gap is below the `0.01` daily threshold. That supports retaining
the paper's SCR idea as a future shadow-training readiness diagnostic.

However, the beta_cf proxy is slightly above the paper's moderate range
(`0.25` to `0.75`). That is a warning that the current approximation leans too
heavily toward counterfactual continuation, so this review does not permit
training or live promotion.

## Decision

Best import:

`scr_readiness_and_mismatch_guard_only`

Final decision:

- has importable advantage: `true`;
- keep as research/shadow diagnostic only;
- SCR shadow training allowed by this review: `false`;
- PPO training allowed: `false`;
- model training allowed: `false`;
- promote to live: `false`;
- target weight change allowed: `false`;
- auto rebalance allowed: `false`;
- `00631L.TW` add allowed: `false`;
- `00632R.TW` open allowed: `false`;
- `00679B.TWO` add allowed: `false`;
- keep `Golden1_0531` unchanged: `true`.

## Validation

Commands run:

```bash
.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_2602_24037_scr_readiness_review.py tests/test_build_group_a_plus_2602_24037_scr_readiness_review.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_2602_24037_scr_readiness_review.py
.venv/bin/python scripts/evaluate/build_group_a_plus_2602_24037_scr_readiness_review.py
```

Result:

- syntax check passed;
- pytest passed: `3 passed`;
- real-data report generated successfully.

## Robustness Sweep Addendum

User asked to continue after the first SCR readiness audit. A robustness sweep
was added to test whether the scenario-to-real conclusion depends on a single
`eval_start`, `min_history`, or `k_neighbors` setting.

Implemented:

- `scripts/evaluate/sweep_group_a_plus_2602_24037_scr_readiness_robustness.py`
- `report/group_a_plus/latest/2602_24037_scr_readiness_robustness.json`
- `report/group_a_plus/latest/2602_24037_scr_readiness_robustness.md`
- `report/group_a_plus/2602_24037_scr_readiness_robustness/history/2602_24037_scr_readiness_robustness_20260828.json`

Sweep grid:

- `eval_start`: `2023-01-03`, `2024-01-02`, `2025-01-02`
- `min_history`: `252`, `504`
- `k_neighbors`: `15`, `30`, `60`
- total runs: `18`

Real-data robustness result:

- valid runs: `18`
- gap gate pass runs: `18/18`
- beta moderate runs: `4/18`
- gap gate pass rate: `1.0`
- beta moderate rate: `0.222222`
- mean absolute gap range: `0.006586` to `0.008189`
- beta_cf proxy range: `0.114012` to `0.773133`
- gap readiness robust: `true`
- beta_cf moderate robust: `false`

Interpretation:

The nearest-neighbor scenario audit is robust enough as a shadow readiness
diagnostic: all tested settings keep the average scenario-real gap below the
`0.01` threshold. However, the paper-inspired `beta_cf` stability is not robust;
only `4/18` settings sit inside the moderate `0.25`-`0.75` range.

This strengthens the current decision: the SCR idea is useful for diagnostics
and future training governance, but it still does not authorize SCR-PPO
training, PPO retraining, target-weight output, or live promotion.

Updated validation:

```bash
.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_2602_24037_scr_readiness_review.py scripts/evaluate/sweep_group_a_plus_2602_24037_scr_readiness_robustness.py tests/test_build_group_a_plus_2602_24037_scr_readiness_review.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_2602_24037_scr_readiness_review.py
.venv/bin/python scripts/evaluate/sweep_group_a_plus_2602_24037_scr_readiness_robustness.py
```

Result:

- syntax check passed;
- pytest passed: `5 passed`;
- robustness report generated successfully.

Decision unchanged:

- best import remains `scr_readiness_and_mismatch_guard_only`;
- no SCR-PPO training;
- no PPO/model training;
- no target-weight change;
- no auto rebalance;
- no `00631L.TW` add;
- no `00632R.TW` open;
- no `00679B.TWO` add;
- keep `Golden1_0531` unchanged.

## Stress Window Split Addendum

User asked to continue after the robustness sweep. A stress-window split was
added to check whether SCR scenario-to-real readiness holds during major market
stress or recent active-policy windows.

Implemented:

- `scripts/evaluate/evaluate_group_a_plus_2602_24037_scr_readiness_window_split.py`
- `report/group_a_plus/latest/2602_24037_scr_readiness_window_split.json`
- `report/group_a_plus/latest/2602_24037_scr_readiness_window_split.md`
- `report/group_a_plus/2602_24037_scr_readiness_window_split/history/2602_24037_scr_readiness_window_split_20260828.json`

Windows:

- `covid_2020`: `2020-02-03` to `2020-06-30`
- `rate_hike_2022`: `2022-01-03` to `2022-12-30`
- `post_2023`: `2023-01-03` to `2026-08-28`
- `recent_2024_2026`: `2024-01-02` to `2026-08-28`
- `active_2025_2026`: `2025-01-02` to `2026-08-28`

Real-data stress-window result:

- valid windows: `5`
- gap gate pass windows: `5/5`
- beta moderate windows: `2/5`
- mean absolute gap range: `0.005605` to `0.007926`
- beta_cf proxy range: `0.128685` to `0.769555`
- stress gap readiness passed: `true`
- stress beta_cf moderate passed: `false`

Window detail:

- `covid_2020`: OOS days `101`, mean gap `0.006513`, P90 gap `0.013808`,
  beta_cf `0.654876`, gap pass `true`, beta moderate `true`
- `rate_hike_2022`: OOS days `246`, mean gap `0.005605`, P90 gap `0.011187`,
  beta_cf `0.597332`, gap pass `true`, beta moderate `true`
- `post_2023`: OOS days `882`, mean gap `0.006688`, P90 gap `0.012090`,
  beta_cf `0.766949`, gap pass `true`, beta moderate `false`
- `recent_2024_2026`: OOS days `643`, mean gap `0.007926`, P90 gap `0.014028`,
  beta_cf `0.769555`, gap pass `true`, beta moderate `false`
- `active_2025_2026`: OOS days `401`, mean gap `0.006936`, P90 gap `0.014957`,
  beta_cf `0.128685`, gap pass `true`, beta moderate `false`

Interpretation:

The scenario-to-real mismatch gate remains robust across all tested stress and
recent windows. This supports keeping SCR as a useful diagnostic layer. The
counterfactual continuation mixing signal is not stable enough, though: only
the 2020 COVID and 2022 rate-hike windows land in the paper's moderate beta_cf
range.

Decision unchanged:

- keep as shadow readiness guard only;
- no SCR-PPO training;
- no PPO/model training;
- no target-weight change;
- no auto rebalance;
- no `00631L.TW` add;
- no `00632R.TW` open;
- no `00679B.TWO` add;
- keep `Golden1_0531` unchanged.

## Latest Scenario Stress Score Addendum

User asked to continue after confirming the stress-window result. A latest-only
SCR scenario stress score was added to answer a narrower operational question:
given the current `live_signal.json` target weights, what do similar historical
scenario contexts imply for next-session downside pressure?

Implemented:

- `scripts/evaluate/build_group_a_plus_2602_24037_scr_scenario_stress_score.py`
- `report/group_a_plus/latest/2602_24037_scr_scenario_stress_score.json`
- `report/group_a_plus/latest/2602_24037_scr_scenario_stress_score.md`
- `report/group_a_plus/2602_24037_scr_scenario_stress_score/history/2602_24037_scr_scenario_stress_score_20260828.json`

Method:

- use the same 0050 / 00631L / 00632R / 00679B feature panel as the SCR
  readiness audit;
- take the latest available context date, `2026-08-28`;
- standardize current context against prior history;
- select the `60` nearest historical contexts after at least `504` observations;
- apply current target weights from `report/group_a_plus/latest/live_signal.json`;
- summarize the next-session portfolio return distribution with P10, VaR, ES,
  probability of loss, worst and best scenario returns.

Real-data latest score:

- status: `available_for_shadow_monitoring`
- as of: `2026-08-28`
- scenario count: `60`
- mean next return: `0.000666`
- median next return: `0.000027`
- P10 next return: `-0.005023`
- VaR 5% next return: `-0.006251`
- ES 5% next return: `-0.009360`
- probability loss: `0.483333`
- worst next return: `-0.010844`
- best next return: `0.016194`
- downside warning threshold: `-0.020000`
- downside warning active: `false`

Interpretation:

The current SCR-nearest scenario distribution does not show a large downside
cluster. The 5% expected shortfall is about `-0.936%`, which is above the
`-2.0%` warning threshold. This is useful as a daily shadow stress monitor, but
it still does not create orders, target weights, model training permission, or
live-promotion permission.

Updated validation:

```bash
.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_2602_24037_scr_scenario_stress_score.py tests/test_build_group_a_plus_2602_24037_scr_readiness_review.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_2602_24037_scr_readiness_review.py
.venv/bin/python scripts/evaluate/build_group_a_plus_2602_24037_scr_scenario_stress_score.py
```

Result:

- syntax check passed;
- pytest passed: `9 passed`;
- latest scenario stress score generated successfully.

Decision unchanged:

- best import remains shadow diagnostics only:
  `scr_readiness_and_mismatch_guard_only` plus
  `latest_scr_scenario_downside_stress_score_only`;
- no SCR-PPO training;
- no PPO/model training;
- no target-weight change;
- no auto rebalance;
- no `00631L.TW` add;
- no `00632R.TW` open;
- no `00679B.TWO` add;
- keep `Golden1_0531` unchanged.

## Final Detailed Record

Final state recorded on `2026-08-30` after the user's "OK, leave detailed
record" request.

Completed experiment set:

- paper analysis and GroupA+ applicability review;
- Taiwan ETF scenario-to-real SCR readiness audit;
- parameter robustness sweep;
- stress-window split across COVID 2020, 2022 rate-hike, post-2023, 2024-2026,
  and 2025-2026 windows;
- latest-only scenario downside stress score using current `live_signal.json`
  target weights as of `2026-08-28`.

Final evidence summary:

- scenario-to-real gap is consistently acceptable as a diagnostic:
  base audit passed, robustness sweep passed `18/18`, stress-window split passed
  `5/5`;
- `beta_cf` proxy is not stable enough for training governance:
  base audit was slightly high at `0.769555`, robustness sweep had only `4/18`
  moderate values, stress-window split had only `2/5` moderate values;
- latest scenario stress score did not trigger a downside warning:
  ES 5% `-0.009360` versus warning threshold `-0.020000`.

Final decision:

This paper's best usable contribution for GroupA+ is now closed as:

- `SCR readiness / mismatch guard`;
- `SCR latest scenario downside stress score`;
- both remain shadow diagnostics only.

Explicitly not approved:

- no SCR-PPO training;
- no PPO or other model retraining;
- no target-weight generation;
- no live allocation import;
- no automatic rebalance;
- no `00631L.TW` add;
- no `00632R.TW` open;
- no `00679B.TWO` add;
- no change to `Golden1_0531`.

Final validation:

```bash
.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_2602_24037_scr_readiness_review.py scripts/evaluate/sweep_group_a_plus_2602_24037_scr_readiness_robustness.py scripts/evaluate/evaluate_group_a_plus_2602_24037_scr_readiness_window_split.py scripts/evaluate/build_group_a_plus_2602_24037_scr_scenario_stress_score.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_2602_24037_scr_readiness_review.py
```

Result: syntax check passed; pytest passed `9 passed`.

## 2026-08-31 Recheck for GroupA+ Latest Strategy

User asked whether `C:\Users\isaac\Downloads\2602.24037.pdf` has advantages
that can be imported into GroupA+ latest strategy.

Re-ran the existing SCR evaluators against the current workspace state:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2602_24037_scr_readiness_review.py
.venv/bin/python scripts/evaluate/sweep_group_a_plus_2602_24037_scr_readiness_robustness.py
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_2602_24037_scr_readiness_window_split.py
.venv/bin/python scripts/evaluate/build_group_a_plus_2602_24037_scr_scenario_stress_score.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_2602_24037_scr_readiness_review.py
```

Latest validation:

- pytest result: `9 passed`;
- base SCR readiness audit: gap gate passed;
- OOS days: `643`;
- mean absolute scenario-real gap: `0.001249`;
- P90 absolute scenario-real gap: `0.002558`;
- mean scenario variance: `0.0000027934`;
- beta_cf proxy: `0.520325`;
- beta_cf candidate is inside the paper's moderate range;
- robustness sweep: `18/18` valid runs passed the gap gate and `18/18` had
  moderate beta_cf;
- stress-window split: `5/5` windows passed the gap gate, while `4/5` windows
  had moderate beta_cf;
- latest SCR scenario stress score as of `2026-08-28`: scenario count `60`,
  mean next return `0.000053`, VaR 5% `-0.002896`, ES 5% `-0.004503`,
  probability of loss `0.483333`;
- downside warning active: `false`.

Decision after recheck:

- the paper has importable value for GroupA+ as a shadow SCR readiness and
  scenario-risk diagnostic;
- keep `scr_readiness_and_mismatch_guard_only`;
- keep `latest_scr_scenario_downside_stress_score_only`;
- do not train SCR-PPO;
- do not retrain PPO or other models from this paper;
- do not promote to live;
- do not change GroupA+ latest target weights;
- do not trigger auto-rebalance;
- do not add `00631L.TW`;
- do not open `00632R.TW`;
- do not add `00679B.TWO`;
- keep `Golden1_0531` and frozen `golden2_0830` unchanged.

Final 2026-08-31 answer:

`2602.24037` is useful and already importable as a GroupA+ research/shadow
guard. Its current Taiwan ETF evidence is good enough to monitor SCR
scenario-to-real mismatch and latest downside scenario pressure. It is not
strong enough to become a live allocation, rebalance, leverage, inverse, hedge,
or SCR-PPO training rule by itself.

## 2026-08-31 Daily Pipeline Import

After the recheck, the import was advanced from manual/latest report generation
to daily best-effort shadow refresh.

Code changes:

- added four `2602.24037` SCR steps to `scripts/run/run_ncf_daily_pipeline.py`:
  - `scr_readiness_review_2602_24037`;
  - `scr_readiness_robustness_2602_24037`;
  - `scr_readiness_window_split_2602_24037`;
  - `scr_scenario_stress_score_2602_24037`;
- marked all four steps best-effort, so a failure cannot block live signal,
  execution plan, alert state, deployment summary, or promotion governance;
- wired all four latest JSON outputs into `daily_status`;
- added a `SCR Readiness / Scenario Stress` markdown section to
  `scripts/misc/check_group_a_plus_daily_status.py`;
- wired all four SCR outputs into
  `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`;
- updated `tests/test_run_ncf_daily_pipeline.py` for command ordering,
  best-effort membership, evaluator paths, and daily-status arguments.

Validation:

```bash
.venv/bin/python -m py_compile scripts/run/run_ncf_daily_pipeline.py scripts/misc/check_group_a_plus_daily_status.py tests/test_run_ncf_daily_pipeline.py tests/test_check_group_a_plus_daily_status.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_2602_24037_scr_readiness_review.py
.venv/bin/python -m pytest tests/test_check_group_a_plus_daily_status.py
.venv/bin/python -m pytest tests/test_run_ncf_daily_pipeline.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_research_shadow_decision_snapshot.py
.venv/bin/python scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py
.venv/bin/python scripts/misc/check_group_a_plus_daily_status.py --output-prefix /tmp/group_a_plus_daily_status_scr_smoke --canonical-output '' --skip-managed-report
```

Results:

- syntax check passed;
- `tests/test_build_group_a_plus_2602_24037_scr_readiness_review.py`: `9 passed`;
- `tests/test_check_group_a_plus_daily_status.py`: `27 passed`;
- `tests/test_run_ncf_daily_pipeline.py`: `22 passed`.
- `tests/test_build_group_a_plus_research_shadow_decision_snapshot.py`:
  `2 passed`;
- research shadow decision snapshot generated successfully and remains
  blocked by existing non-SCR research gates;
- daily status smoke test generated `/tmp/group_a_plus_daily_status_scr_smoke.md`
  with `SCR Readiness / Scenario Stress`, mean/P90 gap `0.001249` / `0.002558`,
  and downside warning `False`.

Production boundary remains unchanged:

- no live strategy weight change;
- no SCR-PPO training;
- no PPO/model retraining;
- no order generation;
- no automatic rebalance;
- no `00631L.TW` add;
- no `00632R.TW` open;
- no `00679B.TWO` add;
- no change to `Golden1_0531`;
- no change to frozen `golden2_0830`.

## Final Archive Note on 2026-08-31

This section is the detailed record requested after the user confirmed the
2602.24037 experiments were complete.

Scope that is considered complete:

- local paper review for `C:\Users\isaac\Downloads\2602.24037.pdf`;
- GroupA+ applicability mapping;
- Taiwan ETF SCR readiness review;
- SCR parameter robustness sweep;
- SCR stress-window split;
- latest SCR scenario stress score;
- daily NCF pipeline integration;
- daily status markdown/JSON integration;
- research shadow decision snapshot integration;
- regression tests for the new SCR pipeline hooks.

Latest archived artifacts:

- `report/group_a_plus/latest/2602_24037_scr_readiness_review.json`
- `report/group_a_plus/latest/2602_24037_scr_readiness_review.md`
- `report/group_a_plus/latest/2602_24037_scr_readiness_robustness.json`
- `report/group_a_plus/latest/2602_24037_scr_readiness_robustness.md`
- `report/group_a_plus/latest/2602_24037_scr_readiness_window_split.json`
- `report/group_a_plus/latest/2602_24037_scr_readiness_window_split.md`
- `report/group_a_plus/latest/2602_24037_scr_scenario_stress_score.json`
- `report/group_a_plus/latest/2602_24037_scr_scenario_stress_score.md`

Latest metrics from the archived `2026-08-31` reports:

- readiness status: `available_for_shadow_review`;
- readiness OOS days: `644`;
- readiness mean absolute scenario-real gap: `0.007888`;
- readiness median absolute scenario-real gap: `0.004341`;
- readiness P90 absolute scenario-real gap: `0.013895`;
- readiness mean scenario variance: `0.000485573`;
- readiness mismatch MSE: `0.0016239856`;
- readiness beta_cf proxy: `0.769822`;
- readiness gap gate passed: `true`;
- readiness beta_cf moderate range: `false`;
- robustness total runs: `18`;
- robustness valid runs: `18`;
- robustness gap gate pass runs: `18/18`;
- robustness beta moderate runs: `4/18`;
- robustness gap pass rate: `1.0`;
- robustness beta moderate rate: `0.222222`;
- window split valid windows: `5`;
- window split gap gate pass windows: `5/5`;
- window split beta moderate windows: `2/5`;
- scenario stress scenario count: `60`;
- scenario stress mean next return: `0.000382`;
- scenario stress P10 next return: `-0.005284`;
- scenario stress VaR 5% next return: `-0.007166`;
- scenario stress ES 5% next return: `-0.010803`;
- scenario stress probability loss: `0.466667`;
- scenario stress worst next return: `-0.014428`;
- scenario stress best next return: `0.015489`;
- scenario stress downside warning active: `false`.

Governance decision archived as final:

- `review_complete`: `true`;
- `has_importable_advantage`: `true`;
- best import: `scr_readiness_and_mismatch_guard_only`;
- stress score import: `latest_scr_scenario_downside_stress_score_only`;
- SCR usage: shadow diagnostic and monitoring only;
- SCR shadow training allowed: `false`;
- PPO training allowed: `false`;
- model training allowed: `false`;
- promote to live: `false`;
- target weight change allowed: `false`;
- auto rebalance allowed: `false`;
- allow `00631L.TW` add: `false`;
- allow `00632R.TW` open: `false`;
- allow `00679B.TWO` add: `false`;
- keep `Golden1_0531` unchanged: `true`.

Important interpretation:

The SCR idea is useful because it gives GroupA+ an independent scenario
coherence and downside stress diagnostic. The gap gate is stable enough for
monitoring. The beta_cf behavior is not stable enough to authorize training or
live allocation changes. Therefore the paper is fully processed, but its output
is deliberately constrained to research/shadow governance.

Production boundary:

- the daily pipeline may refresh these SCR reports;
- daily status may display their metrics;
- research shadow snapshot may include their decision fields;
- failed SCR refreshes are best-effort and must not block normal live signal
  generation;
- SCR reports must not create orders;
- SCR reports must not change `report/group_a_plus/latest/strategy.json`;
- SCR reports must not overwrite target weights from
  `a2118_a2111_ncf_late_bull_deleverage`;
- SCR reports must not be interpreted as signed approval for model training,
  SCR-PPO, PPO retraining, leverage adds, inverse opens, bond adds, or live
  promotion.

Related later operational note:

On `2026-08-31`, `golden2_0830` was separately refreshed for `2026-09-01`
prediction with `actual_data_date = 2026-08-31`. That was a data-date refresh
of the Golden2 snapshot, not a change caused by 2602.24037 and not an SCR live
promotion.
