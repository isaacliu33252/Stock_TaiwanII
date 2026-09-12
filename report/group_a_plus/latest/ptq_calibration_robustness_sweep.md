# ncf_2330 Torch PTQ Robustness Sweep

- Generated: `2026-08-21T14:21:57`
- Windows: `3`
- Seeds: `[1, 2, 3, 42, 101]`
- Promote to live: `False`
- Quantized inference allowed: `False`
- Target weight change allowed: `False`

## Aggregate

- FP32 mean AUC: `0.48726776989755716`
- W8A8 mean AUC: `0.49367084318360915` pass_rate=`0.9333333333333333`
- W4 weight-only mean AUC: `0.4942672182821119` pass_rate=`0.6666666666666666`
- W4A4 mean AUC: `0.4988363278171789` pass_rate=`0.6666666666666666`
- Dynamic quant backend available rate: `1.0`

## Original Pipeline Comparison

- Original mean AUC: `0.6795333333333334`
- Student FP32 mean AUC: `0.48726776989755716`
- Student/original ratio: `0.7170623514630978`

## Live Blocking Reasons

- `production_quantized_inference_path_not_integrated_or_latency_validated`
- `student_shadow_is_not_authorized_replacement_for_ncf_2330`
- `test_rows_below_live_minimum`
- `torch_student_underperforms_original_pipeline`

## Decision

- Research robustness can be used as PTQ governance evidence.
- Do not replace the original ncf_2330 pipeline.
- Do not connect the Torch student or quantized variants to latest strategy.
- No live strategy, target weight, rebalance, or order file was changed.
