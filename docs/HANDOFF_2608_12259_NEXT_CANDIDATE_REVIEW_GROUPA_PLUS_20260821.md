# 2608.12259 Next Candidate Review for GroupA+ - 2026-08-21

## Question

User asked whether item 3 from the next-step list can be done:

- return to better candidates after the `ncf_2330` Torch PTQ student failed robustness.

## Decision

Yes, but do not continue with `ncf_2330_torch_ptq_shadow`.

Recommended candidate order:

1. `StockMixer/ATFNet` shadow review
2. PPO policy runtime/compression governance only
3. new alpha/risk-gate paper search/review

Do not promote any candidate without fresh robustness evidence.

## Candidate 1: StockMixer/ATFNet

Existing local script:

- `scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py`

Existing cached result files:

- `results/stockmixer_atfnet_full50_min1200_weighted_shadow_20260702.json`
- `results/stockmixer_atfnet_top75_candidate_min1200_weighted_shadow_20260702.json`

Existing result summary:

Full50 weighted result:

- stockmixer accuracy: `0.5062358276643991`
- logistic baseline accuracy: `0.5062925170068027`
- stockmixer IC: `0.02578458697206316`
- logistic IC: `0.0212189079122516`
- weighted 0050 proxy return corr: `-0.09959718634190197`
- weighted long-short Sharpe: `-2.0590466647135224`

Top75 weighted result:

- stockmixer accuracy: `0.5188356164383562`
- logistic baseline accuracy: `0.5173896499238965`
- stockmixer IC: `0.023073207405046803`
- logistic IC: `0.01794176628774462`
- weighted 0050 proxy return corr: `0.06787119221755775`
- weighted long-short Sharpe: `-1.8884230971933442`

Interpretation:

- Cross-sectional signal is slightly positive.
- It is not yet a portfolio/trading improvement.
- Weighted 0050 proxy execution is weak or negative.
- This is a better research candidate than `ncf_2330_torch_ptq_shadow`, but still not live-ready.

Recommended next experiment if continued:

- add a robustness wrapper around `evaluate_stockmixer_atfnet_shadow.py`
- run multi-seed and multi-window tests using cached parquet data
- produce a promotion gate that compares:
  - StockMixer/ATFNet
  - own-history logistic baseline
  - persistence baseline
  - weighted 0050 proxy
- block live unless:
  - IC/RankIC lift is stable across windows
  - weighted 0050 proxy correlation is positive across windows
  - long-short/long-flat proxy is not worse than baseline
  - no target-weight path is touched

PTQ note:

- This script uses Torch and is more naturally quantizable than current `ncf_2330.py`.
- But PTQ is not the first step here.
- First prove the model has stable predictive/trading value.
- Only then run PTQ.

## Candidate 2: PPO Runtime/Compression

Existing relevant context:

- `models/portfolio/last_ppo_group_a_100k.zip`
- `docs/HANDOFF_LAST_PPO_INTRODUCTION_AND_STEP_COUNT_ABLATION_20260814.md`
- `scripts/optimize/optimize_group_a_runtime.py`
- `scripts/run/check_model_weight_health.py`

Interpretation:

- PPO is already central to GroupA+ history.
- Prior step-count and HNN experiments show instability/tradeoff concerns.
- Compression is not likely to improve strategy quality.
- It can only be considered for runtime/deployment governance.

Recommended use:

- do not retrain
- do not replace Last PPO
- only measure model loading/inference time and checkpoint health if runtime becomes a real bottleneck

## Candidate 3: New Alpha/Risk-Gate Paper

This remains the highest-upside path if the goal is strategy improvement.

Reason:

- PTQ mainly improves deployment efficiency.
- GroupA+ current bottleneck is not inference latency.
- The useful research target is still alpha/risk gating, robustness, execution, or regime detection.

## Final Recommendation

Proceed only with Candidate 1 if the user wants more experiments:

- build `StockMixer/ATFNet` robustness wrapper
- keep it shadow-only
- do not touch latest strategy
- do not change target weights
- do not open 00632R or add 00631L from this line

Final current status:

- `ncf_2330_torch_ptq_shadow`: rejected for live, keep as governance evidence
- `StockMixer/ATFNet`: feasible next research candidate, but currently weak
- `PPO compression`: lower priority, runtime-only
- `latest_strategy`: unchanged

## Follow-Up: User Requested `都做`

Completed on `2026-08-21`.

Implemented StockMixer/ATFNet robustness:

- `scripts/evaluate/sweep_stockmixer_atfnet_robustness.py`
- `tests/test_sweep_stockmixer_atfnet_robustness.py`
- `report/group_a_plus/latest/stockmixer_atfnet_robustness_sweep.json`
- `report/group_a_plus/latest/stockmixer_atfnet_robustness_sweep.md`
- `report/group_a_plus/stockmixer_atfnet_robustness/history/stockmixer_atfnet_robustness_sweep_full50_202606_20260821.json`

StockMixer robustness setup:

- universe: `full50_202606`
- windows: `3`
- seeds: `[1, 2, 3]`
- epochs per run: `25`
- train rows: `900`
- validation rows: `240`
- test rows: `240`
- data source: cached parquet, no fresh download

StockMixer robustness aggregate:

- StockMixer accuracy: `0.5081254724111868`
- Logistic baseline accuracy: `0.5107426303854875`
- StockMixer IC: `0.005464140939580255`
- Logistic baseline IC: `0.008180105098964415`
- Persistence IC: `-0.013537556855067698`
- StockMixer weighted return corr: `0.05594683937445735`
- StockMixer weighted long-short Sharpe: `-0.518739566666475`
- Logistic weighted long-short Sharpe: `-0.5126682421676413`
- Persistence weighted long-short Sharpe: `0.026479546336377446`

StockMixer decision:

- `promote_to_live=false`
- `target_weight_change_allowed=false`
- `auto_rebalance_allowed=false`
- `allow_00631l_add=false`
- `allow_00632r_open=false`

StockMixer live blockers:

- `stockmixer_ic_not_above_logistic_baseline`
- `weighted_proxy_sharpe_not_above_logistic_baseline`
- `no_execution_cost_or_turnover_backtest`
- `research_shadow_only_no_live_target_path`

Interpretation:

- StockMixer/ATFNet does not pass robustness.
- The multi-window result is weaker than the earlier cached single-run impression.
- It has a small positive weighted return correlation, but IC and Sharpe do not beat the simple logistic baseline.
- Do not continue to PTQ for StockMixer/ATFNet because predictive value is not robust enough.

Implemented PPO runtime/compression governance review:

- `scripts/evaluate/build_group_a_plus_ppo_runtime_compression_review.py`
- `tests/test_build_group_a_plus_ppo_runtime_compression_review.py`
- `report/group_a_plus/latest/ppo_runtime_compression_review.json`
- `report/group_a_plus/latest/ppo_runtime_compression_review.md`
- `report/group_a_plus/ppo_runtime_compression_review/history/ppo_runtime_compression_review_20260821.json`

PPO runtime/compression decision:

- `status=blocked`
- `compression_work_allowed=false`
- `latency_measurement_allowed=true`
- `retraining_allowed=false`
- `replace_last_ppo_allowed=false`
- `promote_to_live=false`
- `target_weight_change_allowed=false`
- `auto_rebalance_allowed=false`
- `allow_00631l_add=false`
- `allow_00632r_open=false`

PPO blockers:

- `runtime_bottleneck_not_demonstrated`
- `ppo_strategy_quality_not_improved_by_compression`
- `last_ppo_production_model_must_not_be_replaced`
- `prior_step_count_and_hnn_experiments_show_oos_tradeoff_risk`
- `no_latency_baseline_or_quantized_backend_benchmark`

Validation:

- `.venv/bin/python -m pytest -q tests/test_sweep_stockmixer_atfnet_robustness.py tests/test_build_group_a_plus_ppo_runtime_compression_review.py`
- Result: `2 passed`

Final candidate status after `都做`:

- `ncf_2330_torch_ptq_shadow`: rejected for live
- `StockMixer/ATFNet`: rejected for live after robustness
- `PPO compression`: blocked; runtime-only if a real latency bottleneck appears
- `latest_strategy`: unchanged
