# 2511.12476 Asian ETF Tail Analytics GroupA+ Review（2026-07-19）

## Paper

- File: `C:\Users\isaac\Downloads\2511.12476.pdf`
- Title: `Performance and Risk Analytics of Asian Exchange-Traded Funds`
- arXiv: `2511.12476v1`
- Date: `2025-11-16`

## Method Summary

The paper studies `29` Asian / emerging-market ETFs from `2014-12-10` to
`2025-01-06`.

Main tools:

- equal-weight ETF benchmark;
- Markowitz efficient frontier;
- CVaR efficient frontier at `95%` and `99%`;
- long-only and long-short portfolios;
- long-short leverage levels of `10%`, `20%`, and `30%`;
- Sharpe ratio;
- Rachev ratio;
- STARR;
- Hill tail-index estimator.

The useful research message is that equal-weight ETF diversification can still
carry heavier tails, and that CVaR / STARR / Rachev / Hill diagnostics are better
governance tools than variance-only optimization.

## GroupA+ Import Decision

Do not import this as a live optimizer.

Useful imports:

- use equal-weight ETF benchmark discipline as a research comparator;
- keep CVaR / STARR / tail diagnostics in the research dashboard;
- use Hill tail index as future extreme-loss diagnostic candidate;
- keep transaction, borrow, financing, and shorting costs as mandatory blockers
  before any long-short idea;
- treat moderate leverage claims from the paper as non-portable to GroupA+.

Not imported:

- 29 US-listed Asian ETF allocation;
- Markowitz live weights;
- CVaR live weights;
- long-short `10%`, `20%`, or `30%` leverage;
- automatic rebalance;
- any `00631L` add permission;
- any `00632R` hedge/open permission.

## Implemented Artifact

Research-only readiness review:

- `scripts/evaluate/build_group_a_plus_asian_etf_tail_analytics_readiness_review.py`
- `tests/test_build_group_a_plus_asian_etf_tail_analytics_readiness_review.py`
- `report/group_a_plus/latest/asian_etf_tail_analytics_readiness_review.json`
- `report/group_a_plus/asian_etf_tail_analytics_readiness/history/asian_etf_tail_analytics_readiness_20260720.json`

Pipeline integration:

- `run_ncf_daily_pipeline.py` runs
  `asian_etf_tail_analytics_readiness_review` as a best-effort research step.
- `build_group_a_plus_research_shadow_decision_snapshot.py` now consumes the
  latest readiness JSON and adds
  `asian_etf_tail_analytics_readiness_blocked` while the review is blocked.
- `check_group_a_plus_daily_status.py` renders an
  `Asian ETF Tail Analytics Readiness` section and stores the source path in the
  daily status payload.
- Latest regenerated files:
  - `report/group_a_plus/latest/research_shadow_decision_snapshot.json`
  - `results/group_a_plus_daily_status_20260720.json`
  - `results/group_a_plus_daily_status_20260720.md`
  - `report/group_a_plus/latest/daily_status.json`

## Current Readiness Result

- `status = blocked`
- `as_of = 2026-07-20`
- local available ticker count: `37`
- paper ETF universe count: `29`
- paper ETF available locally: `1`
- available paper ETF: `EWT`
- paper universe ready: `false`

Existing GroupA+ components:

- CVaR tail diagnostic: `research_only`
- `Golden1_0531` proxy STARR 95: `14.567266529463351`
- `Golden1_0531` proxy Rachev 95/95: `1.034594033280388`
- `00631L` expected shortfall loss 95: `0.0811159172627952`
- `00631L` Rachev 95/95: `0.9502107385766837`
- `00631L` Hill xi 95: `0.36369464063958445`
- market impact readiness: `blocked`
- rebalance review: no auto rebalance, no target-weight change
- LETF tracking error review: no `00631L` add, no `00632R` open

## Improvement Added

Rachev 95/95 was added to the existing CVaR tail-risk diagnostic snapshot:

- `scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py`
- `scripts/run/build_group_a_plus_cvar_tail_risk_diagnostic_snapshot.py`
- `tests/test_evaluate_cvar_tail_risk_diagnostic_shadow.py`

Latest outputs now include:

- `report/group_a_plus/latest/cvar_tail_risk_diagnostic.json`
- `report/group_a_plus/latest/asian_etf_tail_analytics_readiness_review.json`
- `results/group_a_plus_daily_status_20260720.md`

The improvement is reporting-only:

- Rachev monitor is now available for current GroupA+ exposures.
- Tail reward/risk tier is now explicit in the readiness review and daily
  status: `defensive_preference`.
- Current comparison: `Golden1_0531` Rachev 95/95 `1.034594033280388` is above
  `00631L` Rachev 95/95 `0.9502107385766837`.
- Current warnings:
  `rachev_prefers_golden1_over_00631l`,
  `00631l_rachev_below_one_tail_reward_unfavorable`.
- It does not make the optimizer ready.
- It does not unlock `00631L` add or `00632R` open.

## Blocking Reasons

- `asian_29_etf_universe_not_available`
- `asian_etf_walkforward_validation_missing`
- `cvar_tail_risk_diagnostic_research_only`
- `letf_tracking_error_review_disallows_00631l_add`
- `leverage_10_20_30_percent_not_portable_to_group_a_plus`
- `long_short_etf_strategy_not_allowed`
- `market_impact_disallows_auto_rebalance`
- `market_impact_readiness_blocked`
- `rachev_starr_hill_optimizer_not_implemented`
- `rebalance_review_disallows_auto_rebalance`
- `rebalance_review_disallows_target_weight_change`
- `transaction_borrow_financing_costs_missing`

## Strategy Impact

- `tail_analytics_ready = false`
- `optimizer_ready = false`
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`
- `keep_golden1_0531_unchanged = true`

For `2026-07-20`, this paper does not change the GroupA+ latest strategy.

## Conclusion

This paper has useful governance ideas, but no live-ready signal.

Best import:

- keep CVaR / STARR / Rachev / Hill tail diagnostics as research analytics;
- use equal-weight and CVaR frontier ideas only as future benchmark tests.

Do not use it to rebalance, increase `00631L`, open `00632R`, or replace
`Golden1_0531`.

## Verification

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_asian_etf_tail_analytics_readiness_review.py
```

Result:

- `2 passed`

Pipeline / daily-status integration tests:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_asian_etf_tail_analytics_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_run_ncf_daily_pipeline.py tests/test_check_group_a_plus_daily_status.py
```

Result:

- `41 passed`

Rachev monitor improvement tests:

```bash
.venv/bin/python -m pytest tests/test_evaluate_cvar_tail_risk_diagnostic_shadow.py tests/test_build_group_a_plus_asian_etf_tail_analytics_readiness_review.py tests/test_check_group_a_plus_daily_status.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_run_ncf_daily_pipeline.py
```

Result:

- `42 passed`
