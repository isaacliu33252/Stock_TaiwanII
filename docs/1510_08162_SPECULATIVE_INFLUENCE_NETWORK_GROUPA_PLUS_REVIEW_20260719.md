# 1510.08162 Speculative Influence Network GroupA+ Review（2026-07-19）

## Source

- File: `C:\Users\isaac\Downloads\1510.08162.pdf`
- Title: `Speculative Influence Network during financial bubbles: application to Chinese Stock Markets`
- Authors: L. Lin, D. Sornette
- arXiv: `1510.08162v1`
- Date shown in PDF: `2015-10-29`

## Paper Summary

The paper introduces a `Speculative Influence Network` (SIN) to describe
directional speculative influence among sectors and firms during a bubble.

The method has two stages:

1. Estimate a hidden bubble-state probability for each stock or sector using a
   Hidden Markov Model (HMM). The normal state is modeled as GBM, and the bubble
   state uses the Sornette-Andersen stochastic super-exponential bubble model.
2. Conditional on two nodes being in the bubble regime, estimate directional
   transfer entropy from one node to another. The difference between two
   directions defines `Net Speculative Influence Intensity` (NSII).

The empirical test uses Chinese market data from 2006-2008:

- construct SIN during 2006-2007 bubble build-up;
- predict maximum percentage loss during the 2008 crash;
- use sector indices and disaggregated financial firms;
- find that speculative influence metrics have explanatory power for later
  maximum loss.

## GroupA+ Relevance

The idea is relevant to GroupA+ as research governance because it overlaps with:

- systemic bubble time-at-risk;
- ETF coupling / market reflexivity;
- SRR-lite network fragility;
- 2004.01917 illiquidity network readiness;
- crash-risk alert and manual no-add review.

Potentially useful concepts:

- bubble risk should be measured as cross-asset influence, not only as a
  single-index trend;
- a node that speculatively influences many others can later suffer larger
  crash losses;
- sector and financial/non-financial asymmetry should be inspected during
  bubble build-up;
- maximum-loss validation is a useful promotion test before live use.

## Not Directly Portable

Do not directly import:

- China 2006-2008 parameters;
- Sornette-Andersen HMM thresholds;
- transfer entropy / NSII thresholds;
- China sector conclusions;
- any SIN rule that automatically changes target weights;
- any rule that opens `00632R`, adds/reduces `00631L`, or triggers rebalance.

Reasons:

- Current GroupA+ database has only `15` distinct OHLCV tickers, not a broad
  sector/firm universe.
- Sector/style metadata is missing.
- Sector index history is missing.
- HMM bubble-state probability table is missing.
- Transfer entropy / NSII network table is missing.
- Taiwan maximum-loss validation labels are missing.
- Existing systemic bubble and SRR-lite diagnostics already cover the safer
  low-dimensional version of this idea.

## Implemented Artifact

Implemented as research-only readiness review:

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
- `report/group_a_plus/sin_lite_crash_window_backtest/history/sin_lite_crash_window_backtest_20260720.json`
- `report/group_a_plus/sin_lite_param_sweep/history/sin_lite_param_sweep_20260720.json`
- `report/group_a_plus/sin_lite_srr_overlap/history/sin_lite_srr_overlap_20260720.json`
- `report/group_a_plus/systemic_bubble_srr_overlap/history/systemic_bubble_srr_overlap_20260720.json`
- `report/group_a_plus/systemic_bubble_param_sweep/history/systemic_bubble_param_sweep_20260720.json`
- `report/group_a_plus/speculative_influence_network_readiness/history/speculative_influence_network_readiness_20260720.json`

Pipeline integration:

- `run_ncf_daily_pipeline.py` runs
  `speculative_influence_network_readiness_review` as a best-effort research
  readiness step.
- `build_group_a_plus_research_shadow_decision_snapshot.py` consumes the latest
  SIN readiness JSON and adds
  `speculative_influence_network_readiness_blocked` while the inputs remain
  incomplete.
- `check_group_a_plus_daily_status.py` renders a
  `Speculative Influence Network Readiness` section and stores the source path
  in the daily status payload.
- `backfill_group_a_plus_ticker_metadata.py` backfills the minimum static
  ticker metadata needed to clear the sector/style mapping readiness gap for
  the currently known GroupA+ tickers.
- `build_group_a_plus_sin_lite_proxy.py` produces a daily-OHLCV weak proxy for
  correlation density, lagged influence, downside co-movement, concentration,
  and TSMC lead risk. It is research-only and not paper-equivalent.

The artifact checks whether GroupA+ has the minimum data needed to build the
paper's SIN method:

- sector or style mapping;
- broad Taiwan stock OHLCV universe;
- sector index history;
- HMM bubble-state probabilities;
- transfer entropy / NSII network;
- maximum-loss validation labels.

## Current 2026-07-20 Result

Status:

- `blocked`

Actual data end:

- `2026-07-17`

Current OHLCV coverage:

- distinct tickers: `15`
- rows: `29641`
- broad-universe requirement: at least `50` tickers
- broad-universe ready: `false`

Static metadata backfill:

- `ticker_metadata` created/updated with `16` rows.
- Current OHLCV tickers missing metadata: `[]`
- SIN-lite included metadata rows: `14`
- Excluded rows: legacy `0050` alias and `wf` walk-forward artifact.
- `2330.TW` has metadata and external-market OHLCV, but not main `ohlcv`.

SIN-lite proxy:

- usable tickers: `14`
- actual data end: `2026-07-17`
- SIN-lite score: `0.380094`
- state: `normal`
- manual review required by proxy state: `false`
- live status: still `blocked` because the proxy is not validated for live
  weight changes.

SIN-lite crash-window backtest:

- aggregate stress-window watch-or-worse rate: `0.217237`
- aggregate stress-window elevated-or-worse rate: `0.059032`
- non-window watch-or-worse rate: `0.084502`
- non-window elevated-or-worse rate: `0.0`
- all-sample maximum SIN-lite score: `0.647971`

Window details:

| Window | Watch+ rate | Elevated+ rate | Coverage note |
|---|---:|---:|---|
| 2015 China crash | `0.881081` | `0.27027` | limited, min `4` usable tickers |
| 2018 trade-war correction | `0.069388` | `0.0` | limited, min `5` usable tickers |
| 2020 COVID crash | `0.034483` | `0.0` | min `9` usable tickers |
| 2022 rate-hike stress | `0.0` | `0.0` | min `14` usable tickers |
| 2026 Q1/Q2 stress | `0.0` | `0.0` | min `14` usable tickers |
| 2026 recent | `0.0` | `0.0` | min `14` usable tickers |

Interpretation:

- SIN-lite is low false-positive but low recall.
- The strong 2015 result is not reliable enough because ticker coverage is
  limited.
- It misses 2020, 2022, and 2026 stress windows under current thresholds.
- Do not promote SIN-lite to a no-add gate.

Parameter sweep status:

- Sweep scaffold and tests were added.
- The first full implementation was too slow because each candidate reloaded
  and recomputed full rolling scores.
- The optimized sweep now loads the close panel once, caches score grids, and
  samples non-window days every 5 rows while keeping stress windows fully
  represented.
- Reduced grid completed with `18` valid candidates.
- Best sampled candidate:
  `lookback=60`, `min_history=40`, `min_tickers=6`, `edge_threshold=0.2`.
- Best sampled metrics:
  stress-window watch+ `0.515939`, elevated+ `0.197166`;
  non-window watch+ `0.295203`, elevated+ `0.079336`;
  post-2020 minimum watch+ `0.371287`.

Parameter sweep interpretation:

- Lowering thresholds materially improves recall.
- The improved recall comes with frequent watch-level non-window alerts.
- Elevated false positives remain under `10%`, but watch-level noise is too
  high for a no-add gate.
- Do not tune SIN-lite into live strategy rules from this sweep.

SIN-lite vs SRR-lite overlap audit:

- overlap window: `2025-01-02` to `2026-07-16`
- rows: `399`
- SRR frame: `results/srr_lite_shadow_backtest_20250102_20260716_tuned_frame.csv`
- systemic bubble overlap: now run by recomputing the 1212.2833 time-at-risk
  proxy into a daily frame aligned to SRR forward labels.

H10 comparison:

| Signal | Active days | Precision | Recall | FPR |
|---|---:|---:|---:|---:|
| SRR no-add | `8` | `0.5` | `0.03125` | `0.014760147601476014` |
| SIN default watch | `3` | `0.0` | `0.0` | `0.01107011070110701` |
| SIN tuned watch | `219` | `0.3470319634703196` | `0.59375` | `0.5276752767527675` |
| SIN tuned elevated | `66` | `0.2878787878787879` | `0.1484375` | `0.17343173431734318` |
| SRR OR SIN tuned watch | `220` | `0.34545454545454546` | `0.59375` | `0.5313653136531366` |
| SRR AND SIN tuned watch | `7` | `0.5714285714285714` | `0.03125` | `0.01107011070110701` |
| SIN tuned watch without SRR | `212` | `0.33962264150943394` | `0.5625` | `0.5166051660516605` |

Overlap interpretation:

- SIN default is too sparse and misses H10 no-add labels.
- SIN tuned watch adds recall but adds too many false positives.
- SIN tuned elevated still has weaker precision than SRR and materially higher
  false-positive rate.
- SRR/SIN intersection slightly improves precision but does not improve recall
  and has only `7` active days.
- SIN-lite does not add a clean trading-quality signal over SRR-lite.

Systemic bubble vs SRR-lite overlap audit:

- overlap window: `2025-01-02` to `2026-07-16`
- rows: `371`
- artifact: `report/group_a_plus/latest/systemic_bubble_srr_overlap.json`
- frame: `report/group_a_plus/latest/systemic_bubble_srr_overlap_frame.csv`

H10 comparison:

| Signal | Active days | Precision | Recall | FPR |
|---|---:|---:|---:|---:|
| SRR no-add | `8` | `0.5` | `0.03125` | `0.01646090534979424` |
| Systemic watch+ | `270` | `0.31851851851851853` | `0.671875` | `0.757201646090535` |
| Systemic blocked | `39` | `0.41025641025641024` | `0.125` | `0.09465020576131687` |
| Systemic time watch AND coupling elevated | `6` | `0.6666666666666666` | `0.03125` | `0.00823045267489712` |
| SRR OR systemic watch | `271` | `0.3173431734317343` | `0.671875` | `0.7613168724279835` |
| SRR AND systemic watch | `7` | `0.5714285714285714` | `0.03125` | `0.012345679012345678` |
| Systemic watch without SRR | `263` | `0.311787072243346` | `0.640625` | `0.7448559670781894` |

Systemic overlap interpretation:

- Systemic watch+ is too broad for a no-add gate.
- Systemic blocked is cleaner than watch+, but still lower precision and higher
  FPR than SRR no-add.
- The strict `time watch AND coupling elevated` variant improves precision and
  FPR, but only has `6` active days, so it is too small for promotion.
- SRR/systemic intersection slightly improves precision, but only has `7`
  active days and does not improve recall.
- Keep systemic bubble time-at-risk as dashboard/governance context only.

Systemic parameter sweep:

- artifact: `report/group_a_plus/latest/systemic_bubble_param_sweep.json`
- candidates evaluated: `1924`
- best precision candidate:
  `srr_confirmed_by_systemic_blocked`, active `2`, H10 precision `1.0`,
  recall `0.015625`, FPR `0.0`
- best sample-ready candidate:
  `systemic_time_watch_and_reflexivity_elevated`, active `33`, H10 precision
  `0.36363636363636365`, recall `0.09375`, FPR `0.08641975308641975`

Sweep interpretation:

- Precision can be improved only by making the signal extremely sparse.
- The sample-ready candidate does not beat SRR precision.
- Keep all systemic variants as manual-review/dashboard evidence only.

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

Decision:

- `speculative_influence_network_ready = false`
- `hmm_bubble_state_ready = false`
- `transfer_entropy_network_ready = false`
- `maxloss_validation_ready = false`
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`
- `keep_golden1_0531_unchanged = true`

## Relationship To Existing GroupA+ Signals

This paper does not supersede SRR-lite or systemic bubble time-at-risk.

Best mapping:

- HMM bubble probability maps to the existing systemic bubble time-at-risk
  review, but the paper's HMM is not implemented.
- Transfer entropy / NSII maps to a future full-universe influence-network
  diagnostic, but data is not ready.
- Maximum-loss validation maps to a promotion test, not a live trading rule.

Current strategy impact:

- no target-weight change;
- no auto rebalance;
- no `00631L` add;
- no `00632R` open;
- keep `Golden1_0531` unchanged.
- SIN-lite is kept as a dashboard-only research proxy, not a decision gate.
- Parameter sweep does not justify changing 00631L/00632R rules.
- Overlap audit confirms SIN-lite should not replace or widen SRR no-add.

Current generated daily status:

- `results/group_a_plus_daily_status_20260720.json`
- `results/group_a_plus_daily_status_20260720.md`
- `report/group_a_plus/latest/daily_status.json`

The 2026-07-20 status includes the SIN section, but the live signal remains
driven by the existing GroupA+ policy stack.

## Future Work Conditions

Only revisit implementation after:

- broad Taiwan stock universe is available;
- sector/industry/financial-sector metadata is extended beyond the current
  seed table;
- sector index history is available;
- HMM bubble-state probabilities are implemented and validated;
- transfer entropy / NSII network is implemented;
- Taiwan 2015, 2018, 2020, 2022, and 2026 max-loss labels are available;
- incremental value is tested against SRR-lite and systemic bubble time-at-risk
  without materially increasing false positives.

Until then, keep this paper as research-only governance evidence.

## Verification

Focused integration test command:

```bash
.venv/bin/python -m pytest tests/test_backfill_group_a_plus_ticker_metadata.py tests/test_build_group_a_plus_speculative_influence_network_readiness_review.py tests/test_build_group_a_plus_sin_lite_proxy.py tests/test_group_a_plus_sin_lite_crash_window_backtest.py tests/test_sweep_group_a_plus_sin_lite_params.py tests/test_group_a_plus_sin_lite_srr_overlap.py tests/test_group_a_plus_systemic_bubble_srr_overlap.py tests/test_sweep_group_a_plus_systemic_bubble_srr_params.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_check_group_a_plus_daily_status.py tests/test_run_ncf_daily_pipeline.py
```

Result:

- `54 passed`
