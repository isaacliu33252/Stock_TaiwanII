# Detailed Handoff: 2107.09048 Reduced-Rank Correlation for GroupA+（2026-07-20）

## Executive Decision

`C:\Users\isaac\Downloads\2107.09048.pdf` is research-useful, but not live-ready
for GroupA+.

Final decision:

- keep as research / dashboard context only;
- do not use as a crash predictor;
- do not use as a live execution gate;
- do not change target weights;
- do not rebalance because of this paper;
- do not add `00631L`;
- do not open `00632R`;
- keep `Golden1_0531` / latest GroupA+ strategy unchanged.

The only useful import path found is a confirmation-gated manual-review warning:
reduced-rank proxy must be confirmed by `SIN-lite` or `systemic_bubble` before it
is treated as dashboard context. It is still not a trading signal.

## Paper Summary

Paper:

- arXiv: `2107.09048v2`
- title: `A New Attempt to Identify Long-term Precursors for Endogenous Financial Crises in the Market Correlation Structures`
- authors: Anton J. Heckens, Thomas Guhr
- date: `2022-08-09`

Core idea:

- build rolling `42` trading-day return correlation matrices;
- remove the largest eigenvalue / market-mode component;
- analyze reduced-rank correlation structures;
- monitor reduced-rank mean correlation and averaged matrix distance;
- optionally cluster market states with `k = 2` k-means.

Reason it is not directly importable:

- paper uses `250` US stocks with broad sector coverage;
- GroupA+ live universe is ETF-heavy and much smaller;
- Taiwan/cross-market daily proxy is not paper-equivalent;
- empirical precursor evidence is mixed across crisis windows;
- weak proxy has too many false positives if used standalone.

## Current Strategy Context

Latest GroupA+ estimate for `2026-07-20` remains:

- strategy: `a2118_a2111_ncf_late_bull_deleverage`;
- regime: `golden1`;
- target `0050.TW`: `0.50`;
- target `00631L.TW`: `0.19954000000000002`;
- target `00632R.TW`: `0.0`;
- target `00679B.TWO`: `0.0`;
- cash target: `0.30046000000000006`;
- actual data end used by the new 2107 artifacts: `2026-07-17`.

Manual holdings stance remains:

- `00631L = 500`: keep, do not add;
- `00632R = 0`: do not open;
- `0050` action still depends on actual cash and final `00679B` shares, not on
  this paper.

## Implemented Artifacts

Documentation:

- `docs/2107_09048_REDUCED_RANK_CORRELATION_CRISIS_PRECURSOR_GROUPA_PLUS_REVIEW_20260719.md`
- `docs/HANDOFF_2107_09048_REDUCED_RANK_CORRELATION_GROUPA_PLUS_20260719.md`
- `docs/DETAILED_HANDOFF_2107_09048_REDUCED_RANK_CORRELATION_GROUPA_PLUS_20260720.md`
- `docs/GROUPA_PLUS_PDF_RESEARCH_DECISION_MATRIX_20260717.md`

Readiness:

- `scripts/evaluate/build_group_a_plus_reduced_rank_correlation_readiness_review.py`
- `tests/test_build_group_a_plus_reduced_rank_correlation_readiness_review.py`
- `report/group_a_plus/latest/reduced_rank_correlation_readiness_review.json`
- `report/group_a_plus/reduced_rank_correlation_readiness/history/reduced_rank_correlation_readiness_20260720.json`

Weak proxy:

- `scripts/evaluate/build_group_a_plus_reduced_rank_correlation_proxy.py`
- `tests/test_build_group_a_plus_reduced_rank_correlation_proxy.py`
- `report/group_a_plus/latest/reduced_rank_correlation_proxy.json`
- `report/group_a_plus/reduced_rank_correlation_proxy/history/reduced_rank_correlation_proxy_20260720.json`

Parameter sweep:

- `scripts/evaluate/sweep_group_a_plus_reduced_rank_correlation_proxy_params.py`
- `tests/test_sweep_group_a_plus_reduced_rank_correlation_proxy_params.py`
- `report/group_a_plus/latest/reduced_rank_correlation_proxy_param_sweep.json`
- `report/group_a_plus/reduced_rank_correlation_proxy_param_sweep/history/reduced_rank_correlation_proxy_param_sweep_20260720.json`

Crash-window backtest:

- `scripts/evaluate/evaluate_group_a_plus_reduced_rank_correlation_crash_window_backtest.py`
- `tests/test_group_a_plus_reduced_rank_correlation_crash_window_backtest.py`
- `report/group_a_plus/latest/reduced_rank_correlation_crash_window_backtest.json`
- `report/group_a_plus/reduced_rank_correlation_crash_window_backtest/history/reduced_rank_correlation_crash_window_backtest_20260720.json`

Confirmation-gated overlap:

- `scripts/evaluate/evaluate_group_a_plus_reduced_rank_confirmation_overlap_backtest.py`
- `tests/test_group_a_plus_reduced_rank_confirmation_overlap_backtest.py`
- `report/group_a_plus/latest/reduced_rank_confirmation_overlap_backtest.json`
- `report/group_a_plus/latest/reduced_rank_confirmation_overlap_backtest_frame.csv`
- `report/group_a_plus/reduced_rank_confirmation_overlap_backtest/history/reduced_rank_confirmation_overlap_backtest_20260720.json`

Aggregator:

- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
- `tests/test_build_group_a_plus_research_shadow_decision_snapshot.py`
- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`

## Readiness Result

Readiness artifact:

- file: `report/group_a_plus/latest/reduced_rank_correlation_readiness_review.json`
- status: `blocked`;
- actual data end: `2026-07-17`;
- local ticker count: `15`;
- external market ticker count: `22`;
- weak proxy ready for research: `true`;
- paper-equivalent ready: `false`;
- reduced-rank matrix implementation: not paper-equivalent;
- averaged-distance transition monitor: weak proxy only;
- k-means market-state snapshot: not implemented;
- Taiwan crash-window walk-forward validation: failed for standalone weak proxy.

Blocking reasons:

- local universe is below paper-equivalent breadth;
- not using broad sector stock universe;
- not using k-means market-state snapshots;
- standalone proxy false positives are too high;
- no live execution use allowed.

## Weak Proxy Result

Weak proxy artifact:

- file: `report/group_a_plus/latest/reduced_rank_correlation_proxy.json`
- status: `available_for_manual_review`;
- actual data end: `2026-07-17`;
- usable ticker count after stale filtering: `35`;
- rolling window: `42`;
- snapshot count: `211`;
- latest date: `2026-07-17`;
- first eigenmode share: `0.362646`;
- reduced-rank mean correlation: `-0.004794`;
- averaged distance: `0.030205`;
- distance percentile: `0.695238`;
- state: `normal`;
- manual review required by proxy itself: `false`.

Important data-quality detail:

- stale tickers are excluded;
- old unsuffixed `0050` ending `2026-05-04` is excluded from the `2026-07-20`
  proxy, so it does not contaminate the result.

## Parameter Sweep Result

Sweep artifact:

- file: `report/group_a_plus/latest/reduced_rank_correlation_proxy_param_sweep.json`
- candidate count: `24`;
- available candidate count: `24`;
- `normal`: `16`;
- `watch`: `8`;
- `elevated_fragility`: `0`;
- manual-review candidate count: `8`.

Best candidate:

- window: `42`;
- min history: `63`;
- analysis lookback: `504`;
- min tickers: `12`;
- stale filter: `10` days;
- state: `normal`;
- usable tickers: `35`;
- snapshot count: `463`;
- distance percentile: `0.692641`;
- reduced-rank mean correlation: `-0.005076`.

Interpretation:

- parameter stability is acceptable for shadow review;
- no elevated-fragility majority;
- no evidence to change live weights.

## Crash-Window Backtest Result

Crash-window artifact:

- file: `report/group_a_plus/latest/reduced_rank_correlation_crash_window_backtest.json`
- total scored days: `4621`;
- stress-window days: `912`;
- non-window days: `3709`;
- stress-window watch-or-worse rate: `0.246711`;
- stress-window elevated-or-worse rate: `0.016447`;
- non-window watch-or-worse rate: `0.424373`;
- non-window elevated-or-worse rate: `0.197358`.

Window details:

- 2015 China crash: watch-or-worse `0.233503`, elevated `0.030457`;
- 2018 trade-war correction: watch-or-worse `0.226923`, elevated `0.023077`;
- 2020 COVID crash: watch-or-worse `0.348837`, elevated `0.015504`;
- 2022 rate-hike stress: watch-or-worse `0.25`, elevated `0.00463`;
- 2026 Q1/Q2 stress: watch-or-worse `0.21875`, elevated `0.0`;
- 2026 recent: watch-or-worse `0.152174`, elevated `0.0`.

Conclusion:

- standalone weak reduced-rank proxy fails as a live risk trigger;
- non-window warning rate is higher than stress-window warning rate;
- false positives are too high;
- do not use standalone proxy for deleverage or no-add decisions.

## Confirmation-Gated Overlap Result

Confirmation artifact:

- file: `report/group_a_plus/latest/reduced_rank_confirmation_overlap_backtest.json`
- frame: `report/group_a_plus/latest/reduced_rank_confirmation_overlap_backtest_frame.csv`
- confirmation sources: `SIN-lite watch-or-worse`, `systemic_bubble watch-or-worse`.

Base standalone reduced-rank:

- stress watch-or-worse: `0.246711`;
- non-window watch-or-worse: `0.424373`;
- stress/non ratio: `0.581353`.

Confirmed reduced-rank:

- active days: `491`;
- stress active days: `176`;
- non-window active days: `315`;
- stress watch-or-worse: `0.192982`;
- non-window watch-or-worse: `0.084929`;
- stress/non ratio: `2.272292`.

Strict confirmation, requiring both SIN-lite and systemic-bubble:

- active days: `60`;
- stress active days: `25`;
- non-window active days: `35`;
- stress watch-or-worse: `0.027412`;
- non-window watch-or-worse: `0.009437`;
- sample is too sparse for operational use.

Interpretation:

- confirmation gate materially reduces false positives;
- non-window warning rate falls from `42.4%` to `8.5%`;
- stress-window recall falls from `24.7%` to `19.3%`;
- this is acceptable only as manual-review dashboard context;
- still not sufficient for live execution.

## Research Snapshot Integration

The consolidated research snapshot includes:

- `reduced_rank_correlation_readiness_blocked`;
- `reduced_rank_proxy_status`;
- `reduced_rank_proxy_state`;
- `reduced_rank_proxy_sweep_state_counts`;
- `reduced_rank_crash_backtest_stress_watch_rate`;
- `reduced_rank_crash_backtest_non_window_watch_rate`;
- `reduced_rank_confirmed_stress_watch_rate`;
- `reduced_rank_confirmed_non_window_watch_rate`;
- `reduced_rank_confirmed_stress_to_non_ratio`.

The snapshot remains:

- status: `blocked`;
- `allow_00631l_add = false`;
- `target_weight_change_allowed = false`;
- `auto_rebalance_allowed = false`.

## Tests Run

Focused tests:

```bash
.venv/bin/python -m pytest \
  tests/test_group_a_plus_reduced_rank_confirmation_overlap_backtest.py \
  tests/test_group_a_plus_reduced_rank_correlation_crash_window_backtest.py \
  tests/test_sweep_group_a_plus_reduced_rank_correlation_proxy_params.py \
  tests/test_build_group_a_plus_reduced_rank_correlation_proxy.py \
  tests/test_build_group_a_plus_reduced_rank_correlation_readiness_review.py \
  tests/test_build_group_a_plus_research_shadow_decision_snapshot.py
```

Result:

- `12 passed`

## Do Not Do Next

Do not:

- tune weak proxy thresholds further to force a bullish or bearish conclusion;
- promote weak proxy to live gate;
- use standalone reduced-rank `watch` to reduce `0050`;
- use standalone reduced-rank `normal` to add `00631L`;
- use reduced-rank output to open `00632R`;
- overwrite `Golden1_0531` because of this paper;
- rerun the same weak-proxy parameter search without adding new data breadth.

## Only Valid Future Work

Continue only if the goal is paper-equivalent research:

- add broad Taiwan stock universe, preferably `100+` liquid stocks;
- add reliable sector / industry metadata;
- build paper-equivalent `42`-day reduced-rank correlation matrices;
- add k-means state snapshots;
- validate on Taiwan crash/stress windows with false-positive audit;
- compare against existing `SIN-lite`, `systemic_bubble`, `tri-gate`,
  `illiquidity`, and `Asian ETF tail analytics`.

Even then, promotion must require separate evidence and should start as
manual-review only.

## Final Status

2107.09048 work is complete for the current GroupA+ weak-proxy scope.

Final operational stance:

- no live strategy change;
- no rebalance;
- no `00631L` add;
- no `00632R` open;
- keep as research context only;
- if referenced, use only the confirmation-gated dashboard interpretation.
