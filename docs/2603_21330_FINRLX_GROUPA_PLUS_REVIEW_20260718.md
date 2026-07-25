# 2603.21330 FinRL-X Review for GroupA+

## Source

- File: `C:\Users\isaac\Downloads\2603.21330.pdf`
- Title: `FinRL-X: An AI-Native Modular Infrastructure for Quantitative Trading`
- arXiv version in PDF: `2603.21330v1`, dated `2026-03-22`
- Reviewed on: `2026-07-18`
- Strategy context: `a2118_a2111_ncf_late_bull_deleverage`
- Reference estimate context: `2026-07-20`

## Paper Summary

FinRL-X is a trading-system architecture paper, not a new alpha model. Its core
claim is that quantitative trading systems should keep the same target-weight
interface across research, backtesting, paper trading, and live broker execution.

The proposed stack has four layers:

- data layer
- strategy layer
- backtesting layer
- broker-integrated execution layer

The strategy layer is weight-centric. Strategy components produce a target
portfolio weight vector. Downstream backtesting and broker execution consume the
same representation instead of each model emitting broker-specific orders.

The paper structures the strategy pipeline as:

- stock selection
- portfolio allocation
- timing adjustment
- portfolio-level risk overlay

The evaluation is system-level. It emphasizes reproducibility, modularity,
deployment consistency, and operational metrics such as order rejection,
guardrail triggers, and target-versus-realized allocation tracking error.

## Useful Ideas for GroupA+

Useful ideas that fit GroupA+:

- Keep target weights as the canonical strategy interface.
- Preserve the same semantics across research, daily signal, execution plan,
  and live/manual execution.
- Treat execution guards as first-class system outputs, not post-hoc comments.
- Track deployment metrics in addition to return metrics:
  - order rejection / manual block count
  - execution guard trigger count
  - target-vs-realized weight tracking error
  - stale execution-plan age
  - data freshness and source alignment
  - state recovery / rerun readiness
- Use paper/live execution as deployment validation, not as proof of alpha.
- Treat leveraged-product stress events as validation cases for risk modules and
  exposure caps.

## GroupA+ Fit

GroupA+ already matches several FinRL-X principles:

- `daily_signal.py` emits target weights and reference target shares.
- `execution_plan.py` converts target shares into guarded trades.
- pre-trade guards now block `00631L` adds when volatility/compounding regime
  disallows it.
- `ops_health.json`, `daily_status.json`, `signal_alignment.json`, and
  `alert_state.json` separate monitoring from allocation logic.
- The latest 2026-07-18 rebuild keeps NCF outputs, live signal, execution
  guard, and daily status as separate artifacts.

Current latest state after the 2026-07-18 refresh:

- latest data date: `2026-07-17`
- `signal_alignment = wide_divergence`
- leverage suitability: tier `1`, `只適合 0050`
- compounding regime: `MEAN_REVERTING`
- execution plan: `manual_review_required`
- `volatility_gate_no_00631l_add = blocked`
- `compounding_regime_no_00631l_add = blocked`
- final guarded target for `00631L.TW = 0`

## Import Decision

Do not import FinRL-X as a live strategy engine.

Do not import:

- DRL allocator into live GroupA+
- U.S. equity / Alpaca paper-trading performance as Taiwan ETF evidence
- rolling NASDAQ stock selection
- adaptive U.S. multi-asset rotation as a direct allocation rule
- daily turnover paper-trading results as proof that GroupA+ should rebalance
- any automatic `00631L` add or rebalance override

Import only the governance pattern:

- deployment-consistency checklist
- target-weight interface discipline
- target-vs-realized allocation tracking
- execution guard trigger logging
- order/execution readiness metrics
- crash recovery / state persistence review

## Latest Strategy Decision

Keep GroupA+ latest strategy unchanged.

Keep `Golden1_0531` unchanged.

Do not auto-rebalance for `2026-07-20`.

Do not add `00631L`.

Reason:

- This paper improves the system architecture discipline, but provides no
  Taiwan ETF alpha, no validated 00631L timing signal, and no evidence that the
  current `MEAN_REVERTING` / high-volatility guard should be bypassed.
- The current GroupA+ execution guard already blocks new `00631L` exposure.
- The latest `2026-07-20` H1 estimate remains conservative:
  - `00631L` H1 direction: `DOWN`
  - `2330` H1 direction: `DOWN`
  - signal alignment: `wide_divergence`
  - leverage suitability: `0050_only`

## Recommended Next Step

Add a read-only `deployment_consistency_review` artifact for GroupA+.

Suggested checks:

- live signal and execution plan actual data dates align
- target weights and execution plan target shares are reconciled
- pre-trade guards are present and enforced
- blocked guard counts and blocked notional are logged
- current holdings / cash source is explicit
- execution plan is not broker-actionable if cash is missing
- latest daily status and ops health have no hard errors
- target-vs-realized allocation tracking can be computed after real broker
  fills or manual trade confirmations are provided

Promotion rule:

- This review should remain diagnostic only.
- It may block execution or force manual review.
- It must not change target weights.

## Implementation Completed

Added:

- `scripts/evaluate/build_group_a_plus_deployment_consistency_review.py`
- `tests/test_build_group_a_plus_deployment_consistency_review.py`
- `report/group_a_plus/latest/deployment_consistency_review.json`
- `report/group_a_plus/deployment_consistency/history/20260718.json`

Pipeline integration:

- `scripts/run/run_ncf_daily_pipeline.py` now runs
  `deployment_consistency_review` after `daily_status`.
- The step is best-effort and diagnostic only.
- It reads live signal, execution plan, daily status, and ops health.

Current output:

- `status = manual_review_required`
- `broker_actionable = false`
- `blocking_reasons = []`
- warning reasons:
  - `cash_balance_zero_with_nonzero_trades`
  - `execution_plan_not_allowed`
  - `manual_confirmation_required`
- active / blocked guards:
  - `volatility_gate_no_00631l_add`
  - `compounding_regime_no_00631l_add`
- blocked `00631L` buy notional: `21,489.56`

Tested:

- `.venv/bin/python -m pytest tests/test_build_group_a_plus_deployment_consistency_review.py tests/test_run_ncf_daily_pipeline.py`
- Result: `18 passed`

## Current Conclusion

The paper has useful operational design principles, and GroupA+ should absorb
them as governance / monitoring improvements.

No live allocation advantage is available to import.
