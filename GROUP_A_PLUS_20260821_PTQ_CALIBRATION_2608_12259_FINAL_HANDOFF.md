# GroupA+ 2608.12259 PTQ Calibration Final Handoff - 2026-08-21

## Scope

Paper:

- `C:\Users\isaac\Downloads\2608.12259.pdf`
- `Calibration Bets on the Past: Post-Training Quantization for Financial Time-Series Forecasting`
- arXiv: `2608.12259v1`
- Topic: post-training quantization calibration for financial time-series models.

User questions covered:

- whether the paper has advantages importable into GroupA+ latest strategy
- whether FP32 baseline is needed
- whether missing PTQ pieces can be filled
- whether to continue with better candidates
- whether the paper is fully experimented

## Final Decision

This paper is fully reviewed and experimented for the current GroupA+ context.

Final status:

- `promote_to_live=false`
- `quantized_inference_allowed=false`
- `target_weight_change_allowed=false`
- `auto_rebalance_allowed=false`
- `allow_00631l_add=false`
- `allow_00632r_open=false`
- `daily_signal.py` unchanged
- latest strategy unchanged

Final interpretation:

- Useful as deployment governance.
- Not useful as a trading signal.
- Not an alpha improvement.
- Not a risk-gate improvement for current live strategy.
- Do not continue this paper line unless a future production neural model has a real latency/memory deployment need.

## Primary Handoff And Reports

Core handoff:

- `docs/HANDOFF_2608_12259_PTQ_CALIBRATION_GROUPA_PLUS_REVIEW_20260821.md`

Next-candidate handoff:

- `docs/HANDOFF_2608_12259_NEXT_CANDIDATE_REVIEW_GROUPA_PLUS_20260821.md`

Latest reports:

- `report/group_a_plus/latest/ptq_calibration_readiness_review.md`
- `report/group_a_plus/latest/ptq_calibration_robustness_sweep.md`
- `report/group_a_plus/latest/stockmixer_atfnet_robustness_sweep.md`
- `report/group_a_plus/latest/ppo_runtime_compression_review.md`

Latest JSON artifacts:

- `report/group_a_plus/latest/ptq_calibration_eval.json`
- `report/group_a_plus/latest/ptq_calibration_readiness_review.json`
- `report/group_a_plus/latest/ptq_calibration_robustness_sweep.json`
- `report/group_a_plus/latest/stockmixer_atfnet_robustness_sweep.json`
- `report/group_a_plus/latest/ppo_runtime_compression_review.json`

## Implemented Code

PTQ readiness and ncf_2330 baseline:

- `scripts/evaluate/build_group_a_plus_ptq_calibration_readiness_review.py`
- `scripts/evaluate/build_group_a_plus_ncf_2330_fp32_baseline_for_ptq.py`
- `scripts/evaluate/train_group_a_plus_ncf_2330_torch_ptq_shadow.py`
- `scripts/evaluate/sweep_group_a_plus_ncf_2330_torch_ptq_robustness.py`

Candidate follow-up:

- `scripts/evaluate/sweep_stockmixer_atfnet_robustness.py`
- `scripts/evaluate/build_group_a_plus_ppo_runtime_compression_review.py`

Tests:

- `tests/test_build_group_a_plus_ptq_calibration_readiness_review.py`
- `tests/test_build_group_a_plus_ncf_2330_fp32_baseline_for_ptq.py`
- `tests/test_train_group_a_plus_ncf_2330_torch_ptq_shadow.py`
- `tests/test_sweep_group_a_plus_ncf_2330_torch_ptq_robustness.py`
- `tests/test_sweep_stockmixer_atfnet_robustness.py`
- `tests/test_build_group_a_plus_ppo_runtime_compression_review.py`

## Paper Findings Imported

Imported as governance only:

- activation calibration readiness gate
- calibration envelope monitoring
- W8A8 / W4 weight-only before W4A4
- W4A4 requires percentile calibration sweep
- W4A4 requires layerwise exception review
- static low-bit activation deployment must be blocked when robustness fails

Not imported:

- no PTQ trading signal
- no target-weight change
- no live quantized model deployment
- no W4A4 default deployment
- no abs-max W4A4 default
- no `00631L` add rule
- no `00632R` open rule

## ncf_2330 Original Baseline

The existing `ncf_2330.py` is not a Torch model.

It is a sklearn / LightGBM / XGBoost / CatBoost ensemble pipeline.

Original-pipeline baseline was recorded anyway:

- source: `results/ncf_2330_latest_20260821.json`
- source panel: `results/ncf_2330_panel_latest_20260821.csv`
- metric: `mean_direction_val_auc_across_horizons`
- baseline metric: `0.6795333333333334`
- H1 AUC: `0.7455`
- H5 AUC: `0.6582`
- H20 AUC: `0.6349`

Decision:

- original `ncf_2330.py` remains better than the Torch student
- do not replace it

## ncf_2330 Torch PTQ Student

A small Torch student was created only so PTQ could be evaluated on a quantizable checkpoint.

Checkpoint:

- `models/ncf_2330_torch_shadow/ncf_2330_torch_shadow_20260821.pt`

Training source:

- `results/ncf_2330_panel_latest_20260821.csv`

Target:

- `actual_fwd_gain_gt5_h20`

One-shot PTQ result:

- FP32 AUC: `0.5800000000000001`
- W8A8 fake-quant AUC: `0.595`
- W4 weight-only fake-quant AUC: `0.6125`
- W4A4 p99 fake-quant AUC: `0.5974999999999999`
- W4A4 abs-max control AUC: `0.6249999999999999`

One-shot gate briefly looked research-ready, but this was not enough.

## ncf_2330 Torch PTQ Robustness

Robustness setup:

- windows: `3`
- seeds: `[1, 2, 3, 42, 101]`
- train rows: `220`
- calibration rows: `55`
- test rows: `55`
- dynamic quant backend smoke: `torch.ao.quantization.quantize_dynamic_qint8_cpu`

Robustness aggregate:

- FP32 mean AUC: `0.48726776989755716`
- W8A8 mean AUC: `0.49367084318360915`
- W8A8 pass rate: `0.9333333333333333`
- W4 weight-only mean AUC: `0.4942672182821119`
- W4 weight-only pass rate: `0.6666666666666666`
- W4A4 mean AUC: `0.4988363278171789`
- W4A4 pass rate: `0.6666666666666666`
- dynamic quant backend available rate: `1.0`

Original comparison:

- original `ncf_2330.py` mean AUC: `0.6795333333333334`
- Torch student FP32 robustness mean AUC: `0.48726776989755716`
- student/original ratio: `0.7170623514630978`

Final PTQ readiness:

- `status=blocked`
- blocker: `ptq_robustness_sweep_failed`

Live blockers:

- `torch_student_underperforms_original_pipeline`
- `test_rows_below_live_minimum`
- `production_quantized_inference_path_not_integrated_or_latency_validated`
- `student_shadow_is_not_authorized_replacement_for_ncf_2330`

Decision:

- reject ncf_2330 Torch PTQ student for live use
- keep as governance evidence only

## StockMixer/ATFNet Follow-Up

Reason for follow-up:

- user asked to pursue better candidates after ncf_2330 PTQ failed
- StockMixer/ATFNet already had a Torch shadow script and cached data

Implemented:

- `scripts/evaluate/sweep_stockmixer_atfnet_robustness.py`
- `report/group_a_plus/latest/stockmixer_atfnet_robustness_sweep.md`

Setup:

- universe: `full50_202606`
- windows: `3`
- seeds: `[1, 2, 3]`
- epochs per run: `25`
- train rows: `900`
- validation rows: `240`
- test rows: `240`
- data source: cached parquet

Robustness result:

- StockMixer accuracy: `0.5081254724111868`
- logistic baseline accuracy: `0.5107426303854875`
- StockMixer IC: `0.005464140939580255`
- logistic baseline IC: `0.008180105098964415`
- persistence IC: `-0.013537556855067698`
- StockMixer weighted return corr: `0.05594683937445735`
- StockMixer weighted long-short Sharpe: `-0.518739566666475`
- logistic weighted long-short Sharpe: `-0.5126682421676413`
- persistence weighted long-short Sharpe: `0.026479546336377446`

Decision:

- `promote_to_live=false`
- `target_weight_change_allowed=false`
- StockMixer/ATFNet does not beat simple logistic baseline
- do not proceed to PTQ because predictive value is not robust

Live blockers:

- `stockmixer_ic_not_above_logistic_baseline`
- `weighted_proxy_sharpe_not_above_logistic_baseline`
- `no_execution_cost_or_turnover_backtest`
- `research_shadow_only_no_live_target_path`

## PPO Runtime/Compression Follow-Up

Reason for follow-up:

- user asked to do all suggested candidate checks
- PPO was considered only for runtime/compression governance

Implemented:

- `scripts/evaluate/build_group_a_plus_ppo_runtime_compression_review.py`
- `report/group_a_plus/latest/ppo_runtime_compression_review.md`

Result:

- `status=blocked`
- `compression_work_allowed=false`
- `latency_measurement_allowed=true`
- `retraining_allowed=false`
- `replace_last_ppo_allowed=false`
- `promote_to_live=false`
- `target_weight_change_allowed=false`

PPO artifacts found:

- `models/portfolio/last_ppo_group_a_100k.zip`
- `models/portfolio/last_ppo_group_a_500k.zip`
- `models/portfolio/last_ppo_group_a_1000k.zip`
- `models/portfolio/group_a_production_2020_2025_100k.zip`

Blockers:

- `runtime_bottleneck_not_demonstrated`
- `ppo_strategy_quality_not_improved_by_compression`
- `last_ppo_production_model_must_not_be_replaced`
- `prior_step_count_and_hnn_experiments_show_oos_tradeoff_risk`
- `no_latency_baseline_or_quantized_backend_benchmark`

Decision:

- do not quantize PPO
- do not replace Last PPO
- only measure latency in the future if runtime is proven to be a bottleneck

## Validation Commands

PTQ/ncf_2330 robustness:

```bash
.venv/bin/python -m pytest -q tests/test_sweep_group_a_plus_ncf_2330_torch_ptq_robustness.py tests/test_train_group_a_plus_ncf_2330_torch_ptq_shadow.py tests/test_build_group_a_plus_ptq_calibration_readiness_review.py tests/test_build_group_a_plus_ncf_2330_fp32_baseline_for_ptq.py
```

Result:

- `6 passed`

StockMixer/PPO candidate checks:

```bash
.venv/bin/python -m pytest -q tests/test_sweep_stockmixer_atfnet_robustness.py tests/test_build_group_a_plus_ppo_runtime_compression_review.py
```

Result:

- `2 passed`

Earlier one-shot PTQ validation:

```bash
.venv/bin/python -m pytest -q tests/test_train_group_a_plus_ncf_2330_torch_ptq_shadow.py tests/test_build_group_a_plus_ptq_calibration_readiness_review.py tests/test_build_group_a_plus_ncf_2330_fp32_baseline_for_ptq.py
```

Result:

- `5 passed`

## Current Worktree Note

Many generated JSON artifacts under `report/group_a_plus/latest/`, `report/group_a_plus/*/history/`, `results/`, and `models/` may be ignored by git status depending on local ignore rules.

Visible new source/report files include:

- this final handoff
- `docs/HANDOFF_2608_12259_PTQ_CALIBRATION_GROUPA_PLUS_REVIEW_20260821.md`
- `docs/HANDOFF_2608_12259_NEXT_CANDIDATE_REVIEW_GROUPA_PLUS_20260821.md`
- PTQ scripts/tests
- StockMixer robustness script/test
- PPO runtime review script/test
- latest Markdown reports

Do not clean unrelated worktree files.

## Next Recommendation

Stop this paper line.

Do not run more `2608.12259` experiments now.

If continuing research, choose a new paper or a live-relevant risk/alpha candidate. The current PTQ work should remain a governance gate for future neural deployment only.

Final current status:

- `2608.12259`: complete
- `ncf_2330_torch_ptq_shadow`: rejected for live
- `StockMixer/ATFNet`: rejected for live
- `PPO compression`: blocked
- `latest_strategy`: unchanged
