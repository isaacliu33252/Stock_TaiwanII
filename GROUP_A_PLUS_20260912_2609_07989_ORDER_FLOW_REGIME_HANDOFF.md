# GroupA++ 2609.07989 Order-Flow Regime Handoff - 2026-09-12

## Scope

User provided:

- `C:\Users\isaac\Downloads\2609.07989_regimes_in_the_order_flow.pdf`

Paper:

- arXiv:2609.07989
- `Regimes in the Order Flow`
- Subtitle: `Duration-Aware and Multivariate Bayesian Online Changepoint Detection for High-Frequency Markets`

Question:

- Analyze whether this paper has advantages that can be imported into GroupA++
  and the latest strategy.

Final decision:

- Import only as an execution-advisory shadow.
- Do not change latest strategy target weights.
- Do not change `golden1_0531`.
- Do not change `golden2_0830`.
- Do not create orders.
- Do not use daily OHLCV as a substitute for signed order flow.

## Paper Takeaways

The paper studies high-frequency signed order flow, not daily ETF allocation.

Core inputs:

- Signed market-order flow.
- Aggregated signed volume.
- Volume-clock buckets for univariate tests.
- One-minute synchronized calendar buckets for bivariate tests.
- LOBSTER high-frequency data for AAPL and MSFT.

Positive result:

- Constant-hazard BOCPD assumes geometric regime lengths.
- Order-flow regimes do not appear to have one characteristic timescale.
- A duration-aware BOCPD/BOSD filter with a log-normal run-length hazard
  outperformed the constant-hazard baseline in the univariate order-flow tests.
- Log-normal duration dominated both geometric and Pareto alternatives across
  the paper's tested assets, months, and calibration criteria.

Negative result:

- The multivariate BOCPDMS/BVAR extension did not prove useful on the paper's
  bivariate order-flow test.
- It underperformed two independent univariate filters.
- Pairwise Diebold-Mariano tests did not establish robust superiority.
- The paper attributes the weakness to heavy-tailed innovations and short
  regimes: adaptive multivariate coefficients can overreact to volume spikes.

Important omissions:

- No ETF allocation test.
- No GroupA++-like daily target-weight strategy.
- No transaction-cost-adjusted Sharpe for a trading strategy.
- No Taiwan market data.

## GroupA++ Applicability

Current GroupA++ context:

- Active latest strategy family: `a2118_a2111_ncf_late_bull_deleverage`.
- Current target surface is a small ETF sleeve, not a high-frequency
  stock-level market-making or microstructure model.
- Relevant assets include `0050.TW`, `00631L.TW`, `00632R.TW`,
  `00679B.TWO`, `00713.TW`, `2330.TW`, and cash.
- The live strategy is daily allocation with guarded execution and advisory
  shadows.

Best fit:

- Execution-risk advisory before adding leveraged `00631L.TW` exposure.
- Execution-risk advisory before resizing the `00713.TW` / cash sleeve.
- Monitoring intraday signed-flow breaks when reliable signed transaction data
  exists.

Bad fit:

- Direct latest-strategy target-weight signal.
- Daily OHLCV proxy gate.
- Multivariate BOCPDMS/BVAR live allocation gate.

Reason:

- The paper's causal object is signed high-frequency transaction/order-flow
  data. Daily OHLCV does not preserve trade direction, volume-clock structure,
  or order-flow persistence.
- Without reliable signed-flow data, any direct import would create a false
  sense of microstructure evidence.

## Implemented Review

Files:

- `scripts/evaluate/build_group_a_plus_2609_07989_order_flow_regime_review.py`
- `report/group_a_plus/latest/2609_07989_order_flow_regime_review.json`
- `report/group_a_plus/latest/2609_07989_order_flow_regime_review.md`
- `tests/test_build_group_a_plus_2609_07989_order_flow_regime_review.py`

Review decision:

- `import_mode`: `execution_advisory_shadow_only`
- `advisory_import_allowed`: `True`
- `changes_latest_strategy`: `False`
- `changes_golden1_0531`: `False`
- `changes_golden2_0830`: `False`
- `order_generation_allowed`: `False`
- `live_weight_change_allowed`: `False`

Adoption candidates:

- `duration_aware_intraday_order_flow_changepoint_shadow`
  - Status: `conditional_shadow`
  - Use only with reliable signed intraday order-flow data.
  - Potential value: earlier execution caution around signed-flow breaks.

- `lognormal_duration_prior_for_regime_monitors`
  - Status: `recommended_research_only`
  - Use as a future regime-monitor prior comparison.
  - Potential value: reduce over-fragmentation from constant-hazard assumptions.

- `daily_ohlcv_proxy_order_flow_regime_gate`
  - Status: `do_not_adopt`
  - Reason: daily OHLCV is not signed order flow.

- `multivariate_bocpdms_bvar_live_gate`
  - Status: `reject_for_now`
  - Reason: the paper's own bivariate result is negative/provisional.

Commit:

- `35b98da Add 2609.07989 order-flow regime review`

Validation:

- `.venv/bin/python -m pytest tests/test_build_group_a_plus_2609_07989_order_flow_regime_review.py`
- Result: `3 passed`
- `py_compile` passed for the review builder and tests.

## Implemented Shadow

Files:

- `group_a_plus/integrations/order_flow_regime_shadow.py`
- `scripts/run/build_group_a_plus_2609_07989_order_flow_regime_shadow.py`
- `report/group_a_plus/latest/2609_07989_order_flow_regime_shadow.json`
- `report/group_a_plus/latest/2609_07989_order_flow_regime_shadow.md`
- `tests/test_group_a_plus_2609_07989_order_flow_regime_shadow.py`

Data contract:

- Requires signed intraday transaction/order-flow CSV.
- Default expected input:
  - `results/intraday_signed_order_flow_latest.csv`
- Required columns:
  - `timestamp`
  - `ticker`
  - either `signed_volume`, or `side` plus `volume`
- Accepted side values:
  - buy side: `buy`, `b`, `+1`, `1`
  - sell side: `sell`, `s`, `-1`

Default parameters:

- tickers:
  - `0050.TW`
  - `00631L.TW`
  - `00632R.TW`
  - `00679B.TWO`
  - `00713.TW`
  - `2330.TW`
- bucket: `30min`
- rolling window: `20`
- z-threshold: `2.25`
- log-normal hazard scale: `16.0`
- log-normal hazard sigma: `0.75`

Shadow behavior:

- Buckets signed volume by ticker.
- Computes trailing mean/std from prior buckets only.
- Computes a signed-volume z-score.
- Computes a discrete log-normal duration hazard:
  - `H(r)=P(d=r+1 | d>r)`
- Combines duration hazard with current signed-flow shock into a
  `change_probability_proxy`.
- Flags `regime_break_reference` when the signed-flow shock is large enough.
- Flags `high_stress_execution_reference` only when the latest break is
  sell-pressure dominated.

Safety guarantees:

- `policy`: `execution_advisory_shadow_only`
- `creates_orders`: `False`
- `target_weight_change_allowed`: `False`
- `live_weight_change_allowed`: `False`
- `auto_rebalance_allowed`: `False`
- `latest_strategy_change_allowed`: `False`
- `golden2_0830_change_allowed`: `False`

Missing-data behavior:

- If `results/intraday_signed_order_flow_latest.csv` is absent, the runner
  writes a safe unavailable report:
  - `status`: `unavailable`
  - `reason`: `missing_signed_flow_csv`
- The missing-data case is intentional and non-fatal.
- No daily OHLCV fallback is allowed.

Commit:

- `eac7108 Add 2609.07989 order-flow regime shadow`

Validation:

- `.venv/bin/python -m pytest tests/test_group_a_plus_2609_07989_order_flow_regime_shadow.py tests/test_build_group_a_plus_2609_07989_order_flow_regime_review.py`
- Result: `8 passed`
- `py_compile` passed for:
  - `group_a_plus/integrations/order_flow_regime_shadow.py`
  - `scripts/run/build_group_a_plus_2609_07989_order_flow_regime_shadow.py`
  - `tests/test_group_a_plus_2609_07989_order_flow_regime_shadow.py`
- Runner smoke:
  - `.venv/bin/python scripts/run/build_group_a_plus_2609_07989_order_flow_regime_shadow.py --no-log`
  - Produced unavailable latest report because the signed-flow CSV is not
    currently present.

## Pipeline Wiring

Files:

- `scripts/run/run_ncf_daily_pipeline.py`
- `tests/test_run_ncf_daily_pipeline.py`

Pipeline step:

- `paper_2609_07989_order_flow_regime_shadow`

Command wired:

```bash
python scripts/run/build_group_a_plus_2609_07989_order_flow_regime_shadow.py \
  --input results/intraday_signed_order_flow_latest.csv \
  --output report/group_a_plus/latest/2609_07989_order_flow_regime_shadow.json \
  --markdown report/group_a_plus/latest/2609_07989_order_flow_regime_shadow.md \
  --log results/2609_07989_order_flow_regime_shadow_log.jsonl
```

Best-effort status:

- Added to `BEST_EFFORT_STEP_NAMES`.
- Failure or missing signed-flow input must not block:
  - NCF refresh
  - daily signal
  - execution plan
  - alert state
  - push notification
  - daily status

Commit:

- `3a9ca95 Wire 2609.07989 order-flow shadow into pipeline`

Validation:

- `.venv/bin/python -m pytest tests/test_run_ncf_daily_pipeline.py tests/test_group_a_plus_2609_07989_order_flow_regime_shadow.py`
- Result: `31 passed in 159.81s`
- `py_compile` passed for:
  - `scripts/run/run_ncf_daily_pipeline.py`
  - `tests/test_run_ncf_daily_pipeline.py`

## Current Artifact State

Current latest shadow report:

- `report/group_a_plus/latest/2609_07989_order_flow_regime_shadow.json`
- `report/group_a_plus/latest/2609_07989_order_flow_regime_shadow.md`

Current state:

- `status`: `unavailable`
- `reason`: `missing_signed_flow_csv`
- `input`: `results/intraday_signed_order_flow_latest.csv`

This is expected. The repository does not currently have the required signed
intraday order-flow CSV.

## Non-Goals

Do not do the following without a separate signed review:

- Do not change latest strategy weights based on this paper.
- Do not alter `golden2_0830`.
- Do not alter `golden1_0531`.
- Do not add a daily OHLCV fallback.
- Do not convert this into a hard pre-trade block.
- Do not use the multivariate BOCPDMS/BVAR result as a live gate.
- Do not claim the shadow is validated on Taiwan data before signed-flow data
  exists and a forward test is run.

## Future Work

The only reasonable next step is data-readiness work:

1. Create or import a reliable signed intraday order-flow source for Taiwan
   instruments.
2. Store it as `results/intraday_signed_order_flow_latest.csv` or a stable
   production path with the same required schema.
3. Run the shadow for at least a forward-observation period.
4. Evaluate whether execution caution reduces after-cost slippage, drawdown,
   or poor fills around `00631L.TW` adds and `00713.TW` sleeve resizes.
5. Keep the result advisory-only until a separate promotion review passes.

Minimum promotion evidence before changing any behavior:

- Taiwan signed-flow data provenance documented.
- No look-ahead in timestamp handling.
- Purged forward validation.
- Cost/slippage comparison against current execution guard.
- Explicit check that warnings do not suppress profitable risk-on windows.
- Separate manual signed approval if any live execution behavior is proposed.

## Final Status

As of this handoff:

- Review implemented and committed.
- Shadow implemented and committed.
- Daily pipeline wiring implemented and committed.
- All targeted tests passed.
- All commits pushed to `origin/main`.
- Working tree was clean after the pipeline wiring push.
