# Handoff: 1510.08162 Speculative Influence Network for GroupA+（2026-07-19）

## Scope

- Source PDF: `C:\Users\isaac\Downloads\1510.08162.pdf`
- Paper: `Speculative Influence Network during financial bubbles: application to Chinese Stock Markets`
- Target: GroupA+ latest strategy, `Golden1_0531`, 2026-07-20 context
- Import type: speculative-influence-network data-readiness governance only

## Final Decision

No live strategy change.

- No auto rebalance.
- No new `00631L` add.
- No `00632R` hedge/open.
- Keep `Golden1_0531` unchanged.
- Do not import China 2006-2008 bubble parameters.
- Do not use SIN as a live crash detector.
- Do not replace SRR-lite or systemic bubble time-at-risk.

## Useful Import

Imported concepts for research-only governance:

- speculative bubble risk can be networked across sectors and firms;
- HMM bubble-state probability can identify when a node is in speculative
  regime;
- transfer entropy can measure directional influence among bubble-regime nodes;
- NSII can rank net speculative influence;
- max-loss prediction is the right validation target before promotion.

## Implemented Artifact

Research-only:

- `speculative_influence_network_readiness_review`

Files:

- `scripts/evaluate/build_group_a_plus_speculative_influence_network_readiness_review.py`
- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
- `scripts/misc/check_group_a_plus_daily_status.py`
- `scripts/run/run_ncf_daily_pipeline.py`
- `scripts/fetch/backfill_group_a_plus_ticker_metadata.py`
- `scripts/evaluate/build_group_a_plus_sin_lite_proxy.py`
- `scripts/evaluate/evaluate_group_a_plus_sin_lite_crash_window_backtest.py`
- `scripts/evaluate/sweep_group_a_plus_sin_lite_params.py`
- `scripts/evaluate/evaluate_group_a_plus_sin_lite_srr_overlap.py`
- `scripts/evaluate/evaluate_group_a_plus_systemic_bubble_srr_overlap.py`
- `scripts/evaluate/sweep_group_a_plus_systemic_bubble_srr_params.py`
- `tests/test_build_group_a_plus_speculative_influence_network_readiness_review.py`
- `tests/test_build_group_a_plus_research_shadow_decision_snapshot.py`
- `tests/test_check_group_a_plus_daily_status.py`
- `tests/test_run_ncf_daily_pipeline.py`
- `tests/test_backfill_group_a_plus_ticker_metadata.py`
- `tests/test_build_group_a_plus_sin_lite_proxy.py`
- `tests/test_group_a_plus_sin_lite_crash_window_backtest.py`
- `tests/test_sweep_group_a_plus_sin_lite_params.py`
- `tests/test_group_a_plus_sin_lite_srr_overlap.py`
- `tests/test_group_a_plus_systemic_bubble_srr_overlap.py`
- `tests/test_sweep_group_a_plus_systemic_bubble_srr_params.py`
- `report/group_a_plus/latest/ticker_metadata_backfill_report.json`
- `report/group_a_plus/latest/speculative_influence_network_readiness_review.json`
- `report/group_a_plus/latest/sin_lite_proxy.json`
- `report/group_a_plus/latest/sin_lite_crash_window_backtest.json`
- `report/group_a_plus/latest/sin_lite_param_sweep.json`
- `report/group_a_plus/latest/sin_lite_srr_overlap.json`
- `report/group_a_plus/latest/sin_lite_srr_overlap_frame.csv`
- `report/group_a_plus/latest/systemic_bubble_srr_overlap.json`
- `report/group_a_plus/latest/systemic_bubble_srr_overlap_frame.csv`
- `report/group_a_plus/latest/systemic_bubble_param_sweep.json`
- `report/group_a_plus/speculative_influence_network_readiness/history/speculative_influence_network_readiness_20260720.json`
- `report/group_a_plus/sin_lite_crash_window_backtest/history/sin_lite_crash_window_backtest_20260720.json`
- `report/group_a_plus/sin_lite_param_sweep/history/sin_lite_param_sweep_20260720.json`
- `report/group_a_plus/sin_lite_srr_overlap/history/sin_lite_srr_overlap_20260720.json`
- `report/group_a_plus/systemic_bubble_srr_overlap/history/systemic_bubble_srr_overlap_20260720.json`
- `report/group_a_plus/systemic_bubble_param_sweep/history/systemic_bubble_param_sweep_20260720.json`
- `docs/1510_08162_SPECULATIVE_INFLUENCE_NETWORK_GROUPA_PLUS_REVIEW_20260719.md`

Daily pipeline integration:

- best-effort step name:
  `speculative_influence_network_readiness_review`
- research shadow blocker:
  `speculative_influence_network_readiness_blocked`
- SIN-lite shadow blocker:
  `sin_lite_proxy_blocked`
- daily status section:
  `Speculative Influence Network Readiness`
- additional daily status section:
  `SIN-Lite Proxy`
- latest daily status regenerated:
  `results/group_a_plus_daily_status_20260720.json`
  and `results/group_a_plus_daily_status_20260720.md`

## Current Output

- `status = blocked`
- `actual_data_end = 2026-07-17`
- `speculative_influence_network_ready = false`
- `hmm_bubble_state_ready = false`
- `transfer_entropy_network_ready = false`
- `maxloss_validation_ready = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`
- `keep_golden1_0531_unchanged = true`

Current OHLCV coverage:

- `distinct_tickers = 15`
- broad SIN minimum used by readiness check: `50`
- `broad_universe_ready = false`

Static metadata coverage after backfill:

- `ticker_metadata` rows: `16`
- `sin_lite_included_rows = 14`
- `ohlcv_tickers_missing_metadata = []`
- excluded from SIN-lite: legacy `0050` alias and `wf` walk-forward artifact
- `2330.TW` is mapped in metadata and available from `external_market_ohlcv`,
  but not in main `ohlcv`

SIN-lite proxy after metadata backfill:

- `usable_ticker_count = 14`
- `actual_data_end = 2026-07-17`
- `sin_lite_score = 0.380094`
- `state = normal`
- `manual_review_required = false`
- live status remains blocked because the proxy is not validated for live
  target-weight changes

SIN-lite crash-window backtest:

- aggregate stress-window watch-or-worse rate: `0.217237`
- aggregate stress-window elevated-or-worse rate: `0.059032`
- non-window watch-or-worse rate: `0.084502`
- non-window elevated-or-worse rate: `0.0`
- max score: `0.647971`

Window readout:

- 2015 China crash: watch+ `88.1%`, elevated+ `27.0%`, but only min `4`
  usable tickers.
- 2018 correction: watch+ `6.9%`, elevated+ `0.0%`, limited min `5`
  tickers.
- 2020 COVID: watch+ `3.4%`, elevated+ `0.0%`.
- 2022 rate-hike stress: no watch/elevated trigger.
- 2026 Q1/Q2 and 2026 recent: no watch/elevated trigger.

Blocking reasons:

- `broad_stock_universe_insufficient_for_sin`
- `missing_sector_index_history`
- `missing_hmm_bubble_state_probabilities`
- `missing_transfer_entropy_network`
- `missing_crash_maxloss_validation`
- `sornette_andersen_hmm_not_implemented`
- `transfer_entropy_sin_not_implemented`
- `nsii_maxloss_validation_missing_for_taiwan`
- `china_2006_2008_parameters_not_portable_to_group_a_plus`
- `speculative_influence_signal_not_allowed_to_change_live_weights`

## Practical Impact

This paper supports the current conservative posture:

- SRR-lite remains the more practical shadow no-add tool.
- Systemic bubble time-at-risk remains the safer current bubble governance
  artifact.
- SIN is not data-ready.
- No new live decision is allowed.
- Daily research shadow now records SIN as blocked, so this constraint is
  visible in the combined no-add governance snapshot.
- SIN-lite currently does not show elevated correlation/influence stress, but
  this is only a weak daily proxy; it is not enough to permit leverage add.
- Crash-window backtest confirms SIN-lite has weak recall outside 2015, so do
  not use it as a no-add gate without further parameter sweep and independent
  validation.
- Parameter sweep was optimized enough for reduced-grid research review. Do not
  add it to the daily pipeline; it is still a research job, not a daily
  operational dependency.

## Parameter Sweep Status

Implemented:

- `sweep_group_a_plus_sin_lite_params.py`
- unit tests for candidate ranking and research-only gating
- one-time close-panel load
- cached daily-score grids by `(lookback, min_history, edge_threshold)`
- stress windows fully represented; non-window days sampled every 5 rows

Attempted grids:

- full grid: lookback `60,90,120,180`, min-history `40,60,80`,
  min-tickers `6,8,10`, edge-threshold `0.2,0.3,0.35,0.45`; interrupted for
  runtime.
- reduced grid: lookback `60,120`, min-history `40,80`, min-tickers `6,10`,
  edge-threshold `0.2,0.35,0.45`; completed after optimization with `18`
  valid candidates.

Best reduced-grid candidate:

- params: `lookback=60`, `min_history=40`, `min_tickers=6`,
  `edge_threshold=0.2`
- stress-window watch+ rate: `0.515939`
- stress-window elevated+ rate: `0.197166`
- non-window watch+ rate: `0.295203`
- non-window elevated+ rate: `0.079336`
- post-2020 minimum watch+ rate: `0.371287`

Interpretation:

- Lower threshold improves recall across 2020/2022/2026.
- The cost is high watch-level noise outside stress windows.
- This is acceptable for dashboard color but not for a trading gate.
- No parameter change should be applied to live GroupA+.

## SIN-Lite vs SRR Overlap

Artifact:

- `report/group_a_plus/latest/sin_lite_srr_overlap.json`
- `report/group_a_plus/latest/sin_lite_srr_overlap_frame.csv`

Window:

- `2025-01-02` to `2026-07-16`
- rows: `399`

H10 readout:

| Signal | Active days | Precision | Recall | FPR |
|---|---:|---:|---:|---:|
| SRR no-add | `8` | `0.5` | `0.03125` | `0.014760147601476014` |
| SIN default watch | `3` | `0.0` | `0.0` | `0.01107011070110701` |
| SIN tuned watch | `219` | `0.3470319634703196` | `0.59375` | `0.5276752767527675` |
| SIN tuned elevated | `66` | `0.2878787878787879` | `0.1484375` | `0.17343173431734318` |
| SRR OR SIN tuned watch | `220` | `0.34545454545454546` | `0.59375` | `0.5313653136531366` |
| SRR AND SIN tuned watch | `7` | `0.5714285714285714` | `0.03125` | `0.01107011070110701` |
| SIN tuned watch without SRR | `212` | `0.33962264150943394` | `0.5625` | `0.5166051660516605` |

Interpretation:

- SIN default is too sparse.
- SIN tuned watch is too broad and would swamp SRR with false positives.
- SIN tuned elevated is still lower precision and higher FPR than SRR.
- SRR AND SIN tuned watch is slightly cleaner, but sample is only `7` days and
  recall is unchanged.
- Do not replace SRR-lite and do not widen SRR no-add with SIN-lite.

## Systemic Bubble vs SRR Overlap

Artifact:

- `report/group_a_plus/latest/systemic_bubble_srr_overlap.json`
- `report/group_a_plus/latest/systemic_bubble_srr_overlap_frame.csv`

Window:

- `2025-01-02` to `2026-07-16`
- rows: `371`

H10 readout:

| Signal | Active days | Precision | Recall | FPR |
|---|---:|---:|---:|---:|
| SRR no-add | `8` | `0.5` | `0.03125` | `0.01646090534979424` |
| Systemic watch+ | `270` | `0.31851851851851853` | `0.671875` | `0.757201646090535` |
| Systemic blocked | `39` | `0.41025641025641024` | `0.125` | `0.09465020576131687` |
| Systemic time watch AND coupling elevated | `6` | `0.6666666666666666` | `0.03125` | `0.00823045267489712` |
| SRR OR systemic watch | `271` | `0.3173431734317343` | `0.671875` | `0.7613168724279835` |
| SRR AND systemic watch | `7` | `0.5714285714285714` | `0.03125` | `0.012345679012345678` |
| Systemic watch without SRR | `263` | `0.311787072243346` | `0.640625` | `0.7448559670781894` |

Interpretation:

- Systemic watch+ is too broad and would swamp SRR with false positives.
- Systemic blocked is still weaker than SRR no-add on H10 precision/FPR.
- The strict `time watch AND coupling elevated` variant is the best improvement
  candidate, but only has `6` active days and should remain manual-review only.
- SRR AND systemic watch is slightly cleaner, but sample is only `7` days and
  recall is unchanged.
- Do not replace SRR-lite and do not widen SRR no-add with systemic bubble
  time-at-risk.

## Systemic Parameter Sweep

Artifact:

- `report/group_a_plus/latest/systemic_bubble_param_sweep.json`

Readout:

- candidates evaluated: `1924`
- best precision candidate:
  `srr_confirmed_by_systemic_blocked`, active `2`, H10 precision `1.0`,
  recall `0.015625`, FPR `0.0`
- best sample-ready candidate:
  `systemic_time_watch_and_reflexivity_elevated`, active `33`, H10 precision
  `0.36363636363636365`, recall `0.09375`, FPR `0.08641975308641975`

Interpretation:

- The cleanest improvement is too sparse.
- The sample-ready candidate does not beat SRR no-add.
- No systemic parameter change should be promoted to live.

## Relationship To Prior Work

Compared with `2004.01917` illiquidity network:

- `2004.01917` focuses on illiquidity contagion during crash days and needs
  high-frequency bid/ask / failure-event data.
- `1510.08162` focuses on speculative bubble influence before the crash and
  needs sector/firm universe, HMM bubble probabilities, and transfer entropy.
- Both are research-only and blocked for live use.

Compared with SRR-lite:

- SRR-lite is already implemented as conservative shadow no-add / crash-watch.
- SIN would be a richer full-universe influence network, but it is not ready.
- Do not modify SRR thresholds from this paper.

## Data Backfill Needed

Minimum tables:

- `ticker_metadata` exists as a seed table; extend it when adding more Taiwan
  tickers
- `sector_index_ohlcv`
- `hmm_bubble_state_probabilities`
- `transfer_entropy_network`
- `crash_window_maxloss_labels`

Validation:

- Taiwan 2015, 2018, 2020, 2022, 2026 stress windows;
- compare against SRR-lite and systemic bubble time-at-risk;
- reject if false-positive rate rises materially;
- keep all China thresholds separate from Taiwan-calibrated thresholds.

## Final Archive Update

Final synchronization:

- `docs/GROUPA_PLUS_PDF_RESEARCH_DECISION_MATRIX_20260717.md` was updated for
  `1510.08162`.
- The matrix now records that SIN-lite and systemic bubble overlap audits were
  completed and retained only as manual-review evidence.
- The matrix explicitly says:
  - no SIN gate;
  - no systemic gate;
  - no SRR-lite replacement;
  - no SRR-lite widening;
  - no live weight change.

Latest archived artifacts:

- `report/group_a_plus/latest/speculative_influence_network_readiness_review.json`
- `report/group_a_plus/latest/ticker_metadata_backfill_report.json`
- `report/group_a_plus/latest/sin_lite_proxy.json`
- `report/group_a_plus/latest/sin_lite_crash_window_backtest.json`
- `report/group_a_plus/latest/sin_lite_param_sweep.json`
- `report/group_a_plus/latest/sin_lite_srr_overlap.json`
- `report/group_a_plus/latest/sin_lite_srr_overlap_frame.csv`
- `report/group_a_plus/latest/systemic_bubble_srr_overlap.json`
- `report/group_a_plus/latest/systemic_bubble_srr_overlap_frame.csv`
- `report/group_a_plus/latest/systemic_bubble_param_sweep.json`

Operational conclusion for handoff:

- `1510.08162` is fully reviewed for the current GroupA+ scope.
- The only acceptable import is research governance / manual-review context.
- Do not spend more effort tuning daily proxies unless a broader Taiwan stock
  universe, sector index history, HMM bubble probabilities, transfer-entropy
  network, and max-loss labels are added.
- If this paper is revisited, start from the missing-data list above, not from
  live parameter tuning.

## Verification

Focused tests:

```bash
.venv/bin/python -m pytest tests/test_backfill_group_a_plus_ticker_metadata.py tests/test_build_group_a_plus_speculative_influence_network_readiness_review.py tests/test_build_group_a_plus_sin_lite_proxy.py tests/test_group_a_plus_sin_lite_crash_window_backtest.py tests/test_sweep_group_a_plus_sin_lite_params.py tests/test_group_a_plus_sin_lite_srr_overlap.py tests/test_group_a_plus_systemic_bubble_srr_overlap.py tests/test_sweep_group_a_plus_systemic_bubble_srr_params.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_check_group_a_plus_daily_status.py tests/test_run_ncf_daily_pipeline.py
```

Result:

- `54 passed`

Additional matrix-sync check:

```bash
.venv/bin/python -m pytest tests/test_sweep_group_a_plus_systemic_bubble_srr_params.py tests/test_group_a_plus_systemic_bubble_srr_overlap.py tests/test_group_a_plus_sin_lite_srr_overlap.py
```

Result:

- `7 passed`
