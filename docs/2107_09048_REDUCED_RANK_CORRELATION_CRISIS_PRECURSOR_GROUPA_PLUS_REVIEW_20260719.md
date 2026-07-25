# 2107.09048 Reduced-Rank Correlation Crisis Precursors GroupA+ Review（2026-07-19）

## Paper

- File: `C:\Users\isaac\Downloads\2107.09048.pdf`
- Title: `A New Attempt to Identify Long-term Precursors for Endogenous Financial Crises in the Market Correlation Structures`
- arXiv: `2107.09048v2`
- Date: `2022-08-09`

## Method Summary

The paper studies `250` US stocks from `1997-01-02` to `2012-12-31`.

Main tools:

- rolling `42` trading-day return windows;
- standard covariance / correlation matrices;
- subtracting the largest-eigenvalue dyadic market component;
- reduced-rank correlation matrices in covariance and correlation approaches;
- mean reduced-rank covariance / correlation;
- Euclidean distance between reduced-rank correlation matrices;
- averaged distance time series;
- `k = 2` k-means market-state snapshots.

The main idea is to remove the broad market mode and analyze sector / endogenous
correlation structure. The authors find that reduced-rank market states can show
longer-lived structural transitions than standard correlations.

## Evidence From The Paper

Useful findings:

- Reduced-rank matrices can separate broad exogenous market motion from more
  stable sectoral / endogenous structure.
- Averaged distance changes can precede reduced-rank mean-correlation changes in
  the Lehman pre-crash phase.
- A second crisis-like market state was detectable before the Lehman crash using
  only pre-crisis data.
- The paper interprets low reduced-rank mean correlations and sudden averaged
  distance changes as systemic-risk precursor candidates.

Limitations:

- The evidence is strongest for the Lehman pre-phase, weaker for the dot-com
  bubble because much of the structure appears after / around the event.
- The method was tested on `250` stocks with sector coverage, not on a small ETF
  portfolio.
- It requires broad, survivorship-aware stock universe data and sector labels.
- The authors frame the result as one piece of an early-warning puzzle, not a
  fully reliable crash predictor.

## GroupA+ Import Decision

Do not import this as a live trading signal.

Useful imports:

- add reduced-rank correlation state monitoring as a research candidate;
- compare current cross-market / ETF correlation structure against past stable
  regimes;
- track a research-only averaged-distance jump metric;
- use the largest-eigenvalue subtraction idea to separate broad market beta from
  sector / cross-asset endogenous stress;
- treat low reduced-rank mean correlation plus distance jump as a manual-review
  systemic-fragility warning candidate.

Not imported:

- no k-means state transition as an execution gate;
- no automatic crash prediction;
- no target-weight change;
- no `00631L` add permission;
- no `00632R` hedge/open permission;
- no automatic rebalance.

## Current GroupA+ Readiness

Current GroupA+ can only support a weak proxy:

- current GroupA+ tradable universe is too small for the paper's full
  `250`-stock sector-state method;
- local cross-market / ETF data can support a shadow proxy, but it is not
  equivalent to the paper's sectoral S&P 500 universe;
- existing related tools already cover parts of the idea:
  - `cross_market_graph_shadow`;
  - `trigate_vol_memory_shadow`;
  - `systemic_bubble_time_at_risk_review`;
  - `illiquidity_network_readiness_review`;
  - `sin_lite_proxy`.

Recommended implementation level:

- research-only readiness review first;
- no promotion until there is walk-forward validation over Taiwan crash windows
  and enough cross-sectional breadth.

## Implemented Artifact（2026-07-19）

Implemented a research-only readiness review:

- script:
  `scripts/evaluate/build_group_a_plus_reduced_rank_correlation_readiness_review.py`;
- test:
  `tests/test_build_group_a_plus_reduced_rank_correlation_readiness_review.py`;
- latest output:
  `report/group_a_plus/latest/reduced_rank_correlation_readiness_review.json`;
- history output:
  `report/group_a_plus/reduced_rank_correlation_readiness/history/reduced_rank_correlation_readiness_20260720.json`;
- weak proxy script:
  `scripts/evaluate/build_group_a_plus_reduced_rank_correlation_proxy.py`;
- weak proxy output:
  `report/group_a_plus/latest/reduced_rank_correlation_proxy.json`;
- weak proxy history:
  `report/group_a_plus/reduced_rank_correlation_proxy/history/reduced_rank_correlation_proxy_20260720.json`;
- weak proxy parameter sweep:
  `report/group_a_plus/latest/reduced_rank_correlation_proxy_param_sweep.json`;
- weak proxy parameter sweep history:
  `report/group_a_plus/reduced_rank_correlation_proxy_param_sweep/history/reduced_rank_correlation_proxy_param_sweep_20260720.json`;
- crash-window backtest:
  `report/group_a_plus/latest/reduced_rank_correlation_crash_window_backtest.json`;
- crash-window backtest history:
  `report/group_a_plus/reduced_rank_correlation_crash_window_backtest/history/reduced_rank_correlation_crash_window_backtest_20260720.json`;
- confirmation overlap backtest:
  `report/group_a_plus/latest/reduced_rank_confirmation_overlap_backtest.json`;
- confirmation overlap frame:
  `report/group_a_plus/latest/reduced_rank_confirmation_overlap_backtest_frame.csv`;
- confirmation overlap history:
  `report/group_a_plus/reduced_rank_confirmation_overlap_backtest/history/reduced_rank_confirmation_overlap_backtest_20260720.json`;
- aggregator integration:
  `report/group_a_plus/latest/research_shadow_decision_snapshot.json`.

Readiness result for `as_of = 2026-07-20`:

- status: `blocked`;
- actual data end: `2026-07-17`;
- local ticker count: `15`;
- external market ticker count: `22`;
- weak cross-market proxy ready: `true`;
- paper-equivalent readiness: `false`;
- reduced-rank correlation matrix implemented: `false`;
- averaged-distance transition monitor implemented: `false`;
- k-means market-state snapshot implemented: `false`;
- Taiwan crash-window walk-forward validation: `false`.

Decision from artifact:

- `promote_to_live = false`;
- `target_weight_change_allowed = false`;
- `auto_rebalance_allowed = false`;
- `allow_00631l_add = false`;
- `allow_00632r_open = false`;
- `keep_golden1_0531_unchanged = true`.

The research shadow snapshot now includes
`reduced_rank_correlation_readiness_blocked`, so this paper's idea is recorded
as a governance blocker for leverage add, not as a trading alpha.

Weak proxy result for `as_of = 2026-07-20`:

- status: `available_for_manual_review`;
- actual data end: `2026-07-17`;
- usable ticker count after stale-ticker filtering: `35`;
- rolling window: `42` trading days;
- snapshot count: `211`;
- latest snapshot date: `2026-07-17`;
- latest first-eigenmode share: `0.362646`;
- latest reduced-rank mean correlation: `-0.004794`;
- latest averaged distance: `0.030205`;
- latest distance percentile: `0.695238`;
- state: `normal`;
- manual review required by proxy itself: `false`.

Important caveats:

- This proxy uses daily close data and cross-market calendar filling, not the
  paper's `250`-stock sector universe.
- Stale tickers are excluded; the old unsuffixed `0050` series ending
  `2026-05-04` is not allowed to pollute the `2026-07-20` proxy.
- The proxy remains shadow-only even when its state is `normal`.

Parameter sweep result:

- candidate count: `24`;
- available candidate count: `24`;
- state counts: `normal = 16`, `watch = 8`, `elevated_fragility = 0`;
- manual-review candidate count: `8`;
- best candidate:
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

Improvement conclusion:

- Useful improvement: yes, it improves research governance by adding parameter
  stability evidence around the weak proxy.
- Live strategy improvement: not proven. The sweep has no elevated-fragility
  majority and no Taiwan crash-window validation, so it cannot justify changing
  weights, adding `00631L`, opening `00632R`, or forcing deleverage.
- Current operational use: retain as a shadow context field inside
  `research_shadow_decision_snapshot.json`.

Crash-window backtest result:

- total scored days: `4621`;
- stress-window days: `912`;
- non-window days: `3709`;
- stress-window watch-or-worse rate: `0.246711`;
- stress-window elevated-or-worse rate: `0.016447`;
- non-window watch-or-worse rate: `0.424373`;
- non-window elevated-or-worse rate: `0.197358`;
- all-state counts:
  - `normal`: `2821`;
  - `watch`: `1052`;
  - `elevated_fragility`: `747`;
  - `unavailable`: `1`.

Window details:

- 2015 China crash window: watch-or-worse `0.233503`, elevated `0.030457`;
- 2018 trade-war correction: watch-or-worse `0.226923`, elevated `0.023077`;
- 2020 COVID crash: watch-or-worse `0.348837`, elevated `0.015504`;
- 2022 rate-hike stress: watch-or-worse `0.25`, elevated `0.00463`;
- 2026 Q1/Q2 stress: watch-or-worse `0.21875`, elevated `0.0`;
- 2026 recent window: watch-or-worse `0.152174`, elevated `0.0`.

Backtest conclusion:

- The weak reduced-rank proxy is not useful enough as a live risk trigger.
- Non-window watch/elevated rates are higher than stress-window rates, so the
  current proxy has a false-positive problem.
- Keep it as low-priority research context only. It should not be used to
  deleverage, add `00631L`, open `00632R`, or override `Golden1_0531`.

Confirmation-gated overlap result:

- confirmation sources: `SIN-lite watch-or-worse`,
  `systemic_bubble watch-or-worse`;
- base reduced-rank stress watch-or-worse: `0.246711`;
- base reduced-rank non-window watch-or-worse: `0.424373`;
- confirmed reduced-rank stress watch-or-worse: `0.192982`;
- confirmed reduced-rank non-window watch-or-worse: `0.084929`;
- confirmed stress/non rate ratio: `2.272292`;
- strict confirmation, requiring both SIN-lite and systemic confirmation:
  - stress watch-or-worse: `0.027412`;
  - non-window watch-or-worse: `0.009437`;
  - too sparse for operational use.

Improvement from confirmation:

- The confirmation gate materially reduces false positives: non-window warning
  rate falls from `42.4%` to `8.5%`.
- Stress-window recall falls from `24.7%` to `19.3%`, which is acceptable for
  a manual-review context but still too weak for live execution.
- This is the only useful reduced-rank import path found so far: use it as a
  dashboard confirmation field, not as a standalone signal.

## Strategy Impact

Latest 2026-07-20 GroupA+ estimate remains unchanged:

- strategy: `a2118_a2111_ncf_late_bull_deleverage`;
- execution regime: `golden1`;
- target weights:
  - `0050.TW`: `0.50`;
  - `00631L.TW`: `0.19954000000000002`;
  - `00632R.TW`: `0.0`;
  - `00679B.TWO`: `0.0`;
  - cash: `0.30046000000000006`;
- execution allowed by refreshed source checks: `true`;
- actual data date: `2026-07-17`;
- daily status remains `warn` because `2026-07-20` is an estimate using latest
  formal data through `2026-07-17`.

Manual holdings / execution stance remains unchanged:

- keep `00631L` at `500` shares under current guards;
- do not open `00632R`;
- do not add `00631L`;
- 0050 buy/sell decision still depends on actual cash and final `00679B` shares.

## Conclusion

This paper has a useful research idea for GroupA+: reduced-rank correlation
state monitoring can become another systemic-fragility dashboard input.

It is not live-ready for GroupA+ because the paper needs a broad sector stock
universe and has mixed precursor reliability across crises. Import it only as
research governance:

- build a reduced-rank correlation state readiness review;
- maintain the weak cross-market proxy only as manual-review evidence;
- if used at all, require SIN-lite or systemic-bubble confirmation;
- keep all outputs manual-review only.

No live strategy change is justified.
