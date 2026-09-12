# 2608.12259 PTQ Calibration Review for GroupA+ - 2026-08-21

## Paper

Local file:

- `C:\Users\isaac\Downloads\2608.12259.pdf`

Title:

- `Calibration Bets on the Past: Post-Training Quantization for Financial Time-Series Forecasting`

Topic:

- Post-training quantization (PTQ) for financial time-series forecasting.
- Focus: static activation calibration for low-precision neural inference.
- Test case: cross-sectional S&P 500 five-day-forward volatility forecasting.

## Executive Decision

Do not change GroupA+ latest strategy.

This paper has useful engineering/governance lessons, but it does not provide a trading signal or a target-weight improvement.

Current action:

- No `daily_signal.py` wiring.
- No target-weight change.
- No `00631L.TW` add rule.
- No `00632R.TW` open rule.
- No model retraining.
- No quantized model deployment.

Recommended adoption:

- Add this paper to deployment-readiness guidance for any future low-precision neural model.
- If GroupA+ later deploys INT4/INT8 versions of NCF, PPO, volatility models, or time-series neural shadows, require PTQ calibration validation before using them.

## Paper Summary

The paper studies whether post-training quantization damages financial forecasting models.

Experimental setup:

- S&P 500 current constituents.
- Daily data from 2008 to 2025.
- Cross-sectional five-day-forward volatility forecasting.
- Seven architectures:
  - DLinear
  - TSMixer
  - TimeMixer
  - Transformer
  - PatchTST
  - iTransformer
  - SegRNN
- Eight walk-forward test years: `2018` to `2025`.
- Ten seeds per fold.
- Total trained models: `560`.
- Metric: daily cross-sectional Spearman IC.

Main findings:

- Dynamic INT8, static W8A8, and weight-only W4 mostly preserve predictive skill.
- Static W4A4 with 4-bit activations can severely damage IC.
- Default abs-max activation calibration is often bad at 4 bits.
- Percentile calibration can recover much of the damage for some architectures.
- Transformer and TSMixer are mostly range-recoverable.
- SegRNN and TimeMixer retain material residual damage even after range tuning.
- Calibration preferences shift across market regimes.
- Narrow percentile ranges work better in typical conditions but can fail when test-period dispersion exceeds calibration history.
- Out-of-envelope days under p99 calibration show `1.5x` to `3.6x` larger quantization damage for sensitive architectures.

Important paper numbers:

- W8A8 damage is tiny for most models.
- W4 weight-only damage is also usually small.
- W4A4 abs-max damage:
  - PatchTST: about `11%` of FP32 IC
  - iTransformer: about `12%`
  - TSMixer: about `20%`
  - Transformer: about `25%`
  - SegRNN: about `59%`
  - TimeMixer: about `62%`
- Percentile calibration recovery:
  - Transformer: `94%`
  - TSMixer: `80%`
  - SegRNN: `73%`
  - TimeMixer: `53%`

Paper deployment guidance:

- If W4A4 damage is small, default can be kept.
- If most damage disappears after range tuning, use percentile W4A4.
- If one layer dominates damage, keep that layer at 8 bits.
- If large residual damage remains, use dynamic INT8, W8A8, or weight-only W4.
- If test conditions exceed calibration history, recalibrate or use 8-bit activations.

## Relevance To GroupA+

This is not an alpha paper.

It is relevant only if GroupA+ wants low-precision deployment for:

- NCF models
- PPO/Stable-Baselines portfolio policies
- neural volatility forecasters
- StockMixer/ATFNet-style shadows
- future Transformer/TSMixer/TimeMixer/PatchTST models

Current repo check:

- Existing production/latest strategy appears to use normal Python/FP32 inference paths.
- No active INT4/INT8 PTQ deployment path was identified during review.
- Therefore there is no immediate strategy change to make.

## What Can Be Imported

### 1. PTQ Readiness Gate

Before any low-precision neural model is allowed into GroupA+ production or latest-strategy inference, require a readiness report.

Minimum required fields:

- `full_precision_metric`
- `quantized_metric`
- `quantization_damage`
- `damage_pct_of_fp32_signal`
- `calibration_period`
- `test_period`
- `activation_calibration_method`
- `calibration_envelope`
- `out_of_envelope_rate`
- `fallback_precision`
- `target_weight_change_allowed=false` until passed

Suggested promotion rule:

- W8A8 or W4 weight-only can be considered if damage is negligible.
- W4A4 requires explicit percentile sweep and stress-period check.
- W4A4 must not be promoted if it loses more than a small fraction of FP32 signal versus model advantage over classical baseline.

### 2. Calibration Envelope Monitor

The paper's most useful monitoring idea is the calibration envelope:

- Measure whether current market dispersion exceeds the calibration period.
- If current conditions exceed the envelope, static low-bit activation ranges may be stale.

For GroupA+, possible envelope variables:

- 0050 return dispersion versus calibration period
- cross-asset return dispersion across GroupA+ ETF/proxy pool
- 0050 realized volatility percentile
- 2330/0050 dispersion
- SOXX/TWII dispersion if external proxies are involved

Use:

- advisory only
- trigger recalibration review
- do not directly change target weights

### 3. Prefer Safer Precision Choices

Practical rule from the paper:

- Prefer FP32 unless there is a real latency/memory constraint.
- If compression is needed, try W8A8 first.
- If more compression is needed, prefer W4 weight-only before W4A4.
- Treat W4A4 activations as risky unless validated.

This is especially relevant for GroupA+ because:

- The live asset universe is small, so inference cost is unlikely to justify fragile 4-bit activation quantization.
- Prediction errors can directly affect live portfolio decisions.
- The project already prioritizes tail-risk control over marginal speedups.

### 4. Layerwise Exception Review

The paper shows that one layer can dominate W4A4 damage.

If future GroupA+ neural models are quantized:

- run layerwise ablation
- keep sensitive input/token/recurrent layers at 8-bit or FP32
- only quantize robust layers to 4-bit

## What Should Not Be Imported

Do not:

- Treat PTQ as a trading signal.
- Change GroupA+ weights because of this paper.
- Quantize existing live models to W4A4 without validation.
- Use abs-max W4A4 activation calibration by default.
- Deploy static low-bit activation ranges without monitoring distribution shift.
- Use test-period outcomes to pick percentile ranges.
- Claim a latency/memory win unless hardware/backend inference is actually measured.

## GroupA+ Strategy Impact

No strategy impact now.

Reason:

- The paper is about model deployment precision, not market behavior.
- It does not improve alpha, risk gating, re-entry, or allocation weights.
- GroupA+ current latest strategy does not require low-precision neural deployment.

Current decision:

- `promote_to_live=false`
- `target_weight_change_allowed=false`
- `auto_rebalance_allowed=false`
- `allow_00631l_add=false`
- `allow_00632r_open=false`

## Recommended Next Step

No immediate model experiment is required unless the user wants to quantize a specific model.

Implemented governance follow-up on `2026-08-21`:

- `scripts/evaluate/build_group_a_plus_ptq_calibration_readiness_review.py`
- `tests/test_build_group_a_plus_ptq_calibration_readiness_review.py`
- `report/group_a_plus/latest/ptq_calibration_readiness_review.md`
- `report/group_a_plus/latest/ptq_calibration_readiness_review.json`
- `report/group_a_plus/ptq_calibration_readiness/history/ptq_calibration_readiness_review_20260821.json`

Current generated readiness status:

- `status=blocked`
- `quantized_inference_allowed=false`
- `target_weight_change_allowed=false`
- `auto_rebalance_allowed=false`
- `allow_00631l_add=false`
- `allow_00632r_open=false`

Blocking reasons:

- no `ptq_calibration_eval.json`
- no W8A8 result
- no W4 weight-only result
- no W4A4 result
- no W4A4 percentile sweep
- no W4A4 layerwise exception review
- no quantized precision passed readiness gate

Validation:

- `.venv/bin/python -m pytest -q tests/test_build_group_a_plus_ptq_calibration_readiness_review.py`
- Result: `2 passed`

Follow-up for user question `FP32 要做?`:

- Yes, a baseline is required before any PTQ comparison.
- Implemented `ncf_2330` original-pipeline baseline builder:
  - `scripts/evaluate/build_group_a_plus_ncf_2330_fp32_baseline_for_ptq.py`
  - `tests/test_build_group_a_plus_ncf_2330_fp32_baseline_for_ptq.py`
  - `report/group_a_plus/latest/ptq_calibration_eval.json`
  - `report/group_a_plus/ptq_calibration_eval/history/ncf_2330_fp32_baseline_for_ptq_20260821.json`
- Source outputs:
  - `results/ncf_2330_latest_20260821.json`
  - `results/ncf_2330_panel_latest_20260821.csv`
- Baseline metric:
  - `full_precision_metric_name=mean_direction_val_auc_across_horizons`
  - `full_precision_metric=0.6795333333333334`
  - H1 AUC `0.7455`
  - H5 AUC `0.6582`
  - H20 AUC `0.6349`
- Important caveat:
  - Current `ncf_2330.py` is a sklearn/LightGBM/XGBoost/CatBoost ensemble pipeline.
  - It does not expose a Torch FP32 checkpoint/state_dict.
  - Therefore true INT8/INT4 PTQ is not applicable to current `ncf_2330`.
  - Real PTQ would require selecting/training a Torch neural checkpoint first.

Updated generated readiness status after baseline:

- `missing_ptq_calibration_eval` is resolved.
- `status=blocked` remains correct.
- New blocker: `torch_ptq_not_applicable_for_current_model_framework`
- Remaining blockers:
  - no W8A8 result
  - no W4 weight-only result
  - no W4A4 result
  - no W4A4 percentile sweep
  - no W4A4 layerwise exception review
  - no quantized precision passed readiness gate

Validation after baseline:

- `.venv/bin/python -m pytest -q tests/test_build_group_a_plus_ptq_calibration_readiness_review.py tests/test_build_group_a_plus_ncf_2330_fp32_baseline_for_ptq.py`
- Result: `4 passed`

Follow-up for user question `補齊?`:

Implemented a real Torch shadow/student so PTQ can be evaluated on a quantizable checkpoint:

- `scripts/evaluate/train_group_a_plus_ncf_2330_torch_ptq_shadow.py`
- `tests/test_train_group_a_plus_ncf_2330_torch_ptq_shadow.py`
- `models/ncf_2330_torch_shadow/ncf_2330_torch_shadow_20260821.pt`
- `report/group_a_plus/latest/ptq_calibration_eval.json`
- `report/group_a_plus/ptq_calibration_eval/history/ncf_2330_torch_ptq_shadow_eval_20260821.json`
- refreshed `report/group_a_plus/latest/ptq_calibration_readiness_review.json`
- refreshed `report/group_a_plus/latest/ptq_calibration_readiness_review.md`

Method:

- Trained a small Torch MLP student from `results/ncf_2330_panel_latest_20260821.csv`.
- Target label: `actual_fwd_gain_gt5_h20`.
- Features: existing `ncf_2330` panel probabilities/risk scores/confidence fields.
- Temporal split:
  - train `2025-01-02` to `2026-01-29`
  - calibration `2026-01-30` to `2026-05-04`
  - test `2026-05-05` to `2026-07-23`
- Test rows: `57`
- Calibration rows: `56`
- This is a student shadow, not a replacement for `ncf_2330.py`.

PTQ shadow results:

- FP32 Torch shadow AUC: `0.5800000000000001`
- W8A8 fake-quant AUC: `0.595`
- W4 weight-only fake-quant AUC: `0.6125`
- W4A4 p99 fake-quant AUC: `0.5974999999999999`
- W4A4 abs-max control AUC: `0.6249999999999999`
- W4A4 layerwise review completed.
- W4A4 most sensitive layer candidate: `out`

Updated readiness gate:

- `status=research_ready`
- `promotable_precisions_for_research_review=["W8A8", "W4_weight_only", "W4A4"]`
- `quantized_inference_allowed=false`
- `promote_to_live=false`
- `target_weight_change_allowed=false`
- `auto_rebalance_allowed=false`
- `allow_00631l_add=false`
- `allow_00632r_open=false`
- warning: `live_quantized_backend_not_validated`

Interpretation:

- Research gap is now filled for a small Torch shadow.
- It still does not authorize live deployment because the quantization backend is fake-quant CPU shadow only.
- FP32 AUC is only `0.58`, so the student is a governance/quantization testbed, not a superior trading model.
- No live strategy, target weight, rebalance, or order file was changed.

Validation after Torch PTQ shadow:

- `.venv/bin/python -m pytest -q tests/test_train_group_a_plus_ncf_2330_torch_ptq_shadow.py tests/test_build_group_a_plus_ptq_calibration_readiness_review.py tests/test_build_group_a_plus_ncf_2330_fp32_baseline_for_ptq.py`
- Result: `5 passed`

Follow-up for user request `下一步` / `都做`:

Implemented robustness, original-pipeline comparison, backend smoke, and expanded promotion gate:

- `scripts/evaluate/sweep_group_a_plus_ncf_2330_torch_ptq_robustness.py`
- `tests/test_sweep_group_a_plus_ncf_2330_torch_ptq_robustness.py`
- `report/group_a_plus/latest/ptq_calibration_robustness_sweep.json`
- `report/group_a_plus/latest/ptq_calibration_robustness_sweep.md`
- `report/group_a_plus/ptq_calibration_robustness/history/ncf_2330_torch_ptq_robustness_sweep_20260821.json`
- updated `scripts/evaluate/build_group_a_plus_ptq_calibration_readiness_review.py` so latest readiness consumes the robustness sweep.
- refreshed `report/group_a_plus/latest/ptq_calibration_readiness_review.json`
- refreshed `report/group_a_plus/latest/ptq_calibration_readiness_review.md`

Robustness setup:

- Windows: `3`
- Seeds: `[1, 2, 3, 42, 101]`
- Window shape:
  - train rows `220`
  - calibration rows `55`
  - test rows `55`
- Dynamic quant backend smoke:
  - `torch.ao.quantization.quantize_dynamic_qint8_cpu`
  - available rate `1.0`
  - caveat: PyTorch emitted a deprecation warning for `torch.ao.quantization`; this is still adequate as a smoke check but not as a production backend decision.

Robustness aggregate:

- FP32 mean AUC: `0.48726776989755716`
- W8A8 mean AUC: `0.49367084318360915`
- W8A8 pass rate: `0.9333333333333333`
- W4 weight-only mean AUC: `0.4942672182821119`
- W4 weight-only pass rate: `0.6666666666666666`
- W4A4 mean AUC: `0.4988363278171789`
- W4A4 pass rate: `0.6666666666666666`

Original pipeline comparison:

- Original `ncf_2330.py` mean AUC: `0.6795333333333334`
- Torch student FP32 robustness mean AUC: `0.48726776989755716`
- Student/original ratio: `0.7170623514630978`
- Interpretation: Torch student is not a viable replacement for current `ncf_2330.py`.

Final readiness after robustness:

- `status=blocked`
- blocker: `ptq_robustness_sweep_failed`
- `quantized_inference_allowed=false`
- `promote_to_live=false`
- `target_weight_change_allowed=false`
- `auto_rebalance_allowed=false`
- `allow_00631l_add=false`
- `allow_00632r_open=false`

Live blocking reasons:

- `torch_student_underperforms_original_pipeline`
- `test_rows_below_live_minimum`
- `production_quantized_inference_path_not_integrated_or_latency_validated`
- `student_shadow_is_not_authorized_replacement_for_ncf_2330`

Final interpretation:

- The one-shot PTQ shadow looked acceptable, but the multi-seed/multi-window robustness sweep failed.
- This confirms the governance rule is useful: a single calibration pass is not enough.
- Keep this only as PTQ governance evidence.
- Do not connect the Torch student or any quantized variant to latest strategy.
- No live strategy, target weight, rebalance, or order file was changed.

Validation after robustness:

- `.venv/bin/python -m pytest -q tests/test_sweep_group_a_plus_ncf_2330_torch_ptq_robustness.py tests/test_train_group_a_plus_ncf_2330_torch_ptq_shadow.py tests/test_build_group_a_plus_ptq_calibration_readiness_review.py tests/test_build_group_a_plus_ncf_2330_fp32_baseline_for_ptq.py`
- Result: `6 passed`

If a future model is selected for PTQ, the correct next experiment is:

1. Choose one concrete model/checkpoint.
2. Run FP32 baseline on a walk-forward split.
3. Run W8A8, W4 weight-only, and W4A4.
4. Sweep activation calibration percentiles.
5. Compare against the model's own FP32 output and a classical baseline.
6. Check stress-period envelope exceedance.
7. Approve only if predictive damage is small and stable.

Most likely candidates if this is revisited:

- NCF 2330 checklist model, if there is a Torch checkpoint and quantization path.
- StockMixer/ATFNet shadow, if actively used for inference.
- PPO policy, but only for deployment engineering, not for strategy improvement.

## Final Conclusion

This paper has a useful deployment-governance lesson:

- Activation calibration is a first-class risk control for 4-bit PTQ financial models.

But it has no direct GroupA+ latest-strategy trading advantage today.

Final verdict:

- Keep as deployment-readiness guidance.
- Do not implement in live strategy.
- Do not alter latest strategy weights.
- Revisit only if GroupA+ actually deploys quantized neural inference.
