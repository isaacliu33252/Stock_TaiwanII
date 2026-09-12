# 2608.12259 PTQ Calibration Readiness Review

- Generated: `2026-08-21T14:22:50`
- Status: `blocked`
- Policy: `research_governance_only_no_quantized_live_inference_no_weight_change`
- Recommended use: `deployment_readiness_gate_for_future_neural_model_quantization`

## Decision

- Quantized inference allowed: `False`
- Promote to live: `False`
- Target weight change allowed: `False`
- Auto rebalance allowed: `False`
- Keep latest strategy weights unchanged: `True`

## PTQ Evaluation Summary

- Model name: `ncf_2330_torch_shadow_student`
- Model framework: `torch`
- Model artifact type: `torch_state_dict_checkpoint`
- Torch PTQ applicable: `True`
- Full precision metric: `0.5800000000000001`
- Calibration period: `2026-01-30:2026-05-04`
- Test period: `2026-05-05:2026-07-23`
- Activation calibration: `percentile_p99_with_absmax_control`
- Out-of-envelope rate: `0.0`

## Precision Checks

### W8A8

- Status: `passed`
- Metric: `0.595`
- Damage pct of FP32 signal: `0.0`
- Max allowed damage pct: `0.03`
- Percentile sweep tested: `True`
- Layerwise exception reviewed: `False`

### W4_weight_only

- Status: `passed`
- Metric: `0.6125`
- Damage pct of FP32 signal: `0.0`
- Max allowed damage pct: `0.05`
- Percentile sweep tested: `False`
- Layerwise exception reviewed: `False`

### W4A4

- Status: `passed`
- Metric: `0.5974999999999999`
- Damage pct of FP32 signal: `0.0`
- Max allowed damage pct: `0.05`
- Percentile sweep tested: `True`
- Layerwise exception reviewed: `True`

## Blocking Reasons

- `ptq_robustness_sweep_failed`

## Robustness Summary

- Exists: `True`
- Fake-quant research passed: `False`
- Dynamic quant backend smoke available: `True`
- Student/original: `0.7170623514630978`

## Warning Reasons

- `live_quantized_backend_not_validated`
- `robustness_live_blocker:production_quantized_inference_path_not_integrated_or_latency_validated`
- `robustness_live_blocker:student_shadow_is_not_authorized_replacement_for_ncf_2330`
- `robustness_live_blocker:test_rows_below_live_minimum`
- `robustness_live_blocker:torch_student_underperforms_original_pipeline`

## Import Decision

- Keep this as a future deployment gate only.
- Do not change GroupA+ latest strategy or golden1_0531 weights.
- Do not deploy W4A4 unless percentile calibration, envelope monitoring, and layerwise review all pass.
- No live strategy, target weight, rebalance, or order file was changed.
