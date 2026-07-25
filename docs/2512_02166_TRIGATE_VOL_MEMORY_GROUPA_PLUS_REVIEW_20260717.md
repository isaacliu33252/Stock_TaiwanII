# 2512.02166 Tri-Gate Volatility Memory Review for GroupA+

## Source

- File: `C:\Users\isaac\Downloads\2512.02166.pdf`
- Title: `The Three-Dimensional Decomposition of Volatility Memory`
- Reviewed on: `2026-07-17`
- Strategy context: `a2118_a2111_ncf_late_bull_deleverage`

## Paper Takeaway

The paper decomposes volatility memory into three dimensions:

- `level`: persistence strength / regime gate
- `shape`: long-memory form / fractional-memory gate
- `tempo`: business-time speed / market-activity gate

For equities, the paper reports that regime and tempo gates are more important
than a single fixed GARCH-style memory scale. This is relevant to GroupA+
because `00631L` risk is highly path-dependent and volatility regimes are
already a recurring blocker for leverage adds.

## Imported Ideas

Imported as shadow/governance only:

- split volatility risk into level / shape / tempo dimensions
- treat high volatility persistence as different from transient volatility
  bursts
- include a business-time / activity-speed proxy before trusting leverage adds
- keep simple transparent proxies until a full TG-Vol estimator is validated

## Not Imported

Not imported:

- full TG-Vol QMLE estimator
- G-FIGARCH fractional-order estimation
- SPY / EURUSD parameters
- automatic target-weight changes
- automatic `00631L` add signal

## Implementation

Added:

- `scripts/evaluate/evaluate_group_a_plus_trigate_vol_memory_shadow.py`
- `results/group_a_plus_trigate_vol_memory_shadow_20260717.json`
- `report/group_a_plus/latest/trigate_vol_memory_shadow.json`

The implementation is intentionally transparent:

- level proxy: 00631L 20-day annualized volatility percentile
- shape proxy: rolling autocorrelation of volatility across short/medium lags
- tempo proxy: absolute-return speed plus volume speed versus rolling median

## Decision

This PDF has useful risk-decomposition ideas, but no direct live allocation
advantage for GroupA+.

Current output:

- `state = blocked_for_leverage_add`
- `stress_gate_count = 3`
- level gate: active
  - 00631L 20-day annualized volatility: `0.7395`
  - 252-day percentile: `0.9325`
- shape gate: active
  - memory shape score: `0.8211`
  - 252-day percentile: `0.9762`
- tempo gate: active
  - tempo score: `7.4887`
  - 252-day percentile: `1.0000`
- 60-day 0050/00631L return correlation: `0.9806`

Decision:

- keep GroupA+ latest strategy unchanged
- keep `Golden1_0531` unchanged
- do not auto-rebalance
- do not auto-add `00631L`
- use tri-gate volatility memory only as a research-only shadow diagnostic
