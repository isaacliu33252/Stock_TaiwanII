# Handoff: 2511.12476 Asian ETF Tail Analytics for GroupA+（2026-07-19）

## Scope

- Source PDF: `C:\Users\isaac\Downloads\2511.12476.pdf`
- Paper: `Performance and Risk Analytics of Asian Exchange-Traded Funds`
- Target: GroupA+ latest strategy, `Golden1_0531`, 2026-07-20 context
- Import type: ETF tail-risk analytics readiness governance only

## Final Decision

No live strategy change.

- No auto rebalance.
- No target-weight change.
- No new `00631L` add.
- No `00632R` hedge/open.
- Keep `Golden1_0531` unchanged.
- Do not import Markowitz/CVaR optimized weights.
- Do not import long-short leverage.
- Do not use the 29-ETF Asian universe as a GroupA+ allocation.

## Useful Import

Research-only:

- equal-weight ETF benchmark as a comparator;
- CVaR `95%` / `99%` frontier as future validation benchmark;
- Sharpe / Rachev / STARR reward-risk ratios as reporting candidates;
- Hill tail index as an extreme-loss diagnostic candidate;
- explicit blocker for transaction, borrow, financing, and shorting costs before
  any long-short strategy.

## Implemented Artifact

Files:

- `scripts/evaluate/build_group_a_plus_asian_etf_tail_analytics_readiness_review.py`
- `tests/test_build_group_a_plus_asian_etf_tail_analytics_readiness_review.py`
- `report/group_a_plus/latest/asian_etf_tail_analytics_readiness_review.json`
- `report/group_a_plus/asian_etf_tail_analytics_readiness/history/asian_etf_tail_analytics_readiness_20260720.json`
- `docs/2511_12476_ASIAN_ETF_TAIL_ANALYTICS_GROUPA_PLUS_REVIEW_20260719.md`

Pipeline integration:

- best-effort step name:
  `asian_etf_tail_analytics_readiness_review`
- research shadow blocker:
  `asian_etf_tail_analytics_readiness_blocked`
- daily status section:
  `Asian ETF Tail Analytics Readiness`
- latest daily status regenerated:
  `results/group_a_plus_daily_status_20260720.json`
  and `results/group_a_plus_daily_status_20260720.md`

## Current Output

- `status = blocked`
- paper ETF universe: `29`
- available paper ETFs in local DB: `1`
- available paper ETF: `EWT`
- `tail_analytics_ready = false`
- `optimizer_ready = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`
- `keep_golden1_0531_unchanged = true`

Existing component readout:

- CVaR tail diagnostic is still `research_only`.
- `Golden1_0531` proxy STARR 95 is available as research context.
- `Golden1_0531` proxy Rachev 95/95 is available as research context:
  `1.034594033280388`.
- `00631L` Rachev 95/95 is available as research context:
  `0.9502107385766837`.
- `00631L` has positive Hill tail xi, confirming heavy-tail concern.
- market-impact readiness remains blocked.
- rebalance review disallows auto rebalance and target-weight changes.
- LETF tracking-error review disallows both `00631L` add and `00632R` open.

## Improvement Added

Rachev 95/95 reporting was added to the existing CVaR tail diagnostic and
surfaced in the Asian ETF tail analytics readiness / daily status stack.
The readiness review now also maps the comparison into an explicit research
tier:

- tail reward/risk tier: `defensive_preference`;
- `Golden1_0531` Rachev 95/95: `1.034594033280388`;
- `00631L` Rachev 95/95: `0.9502107385766837`;
- warnings:
  `rachev_prefers_golden1_over_00631l`,
  `00631l_rachev_below_one_tail_reward_unfavorable`.

Files changed:

- `scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py`
- `scripts/run/build_group_a_plus_cvar_tail_risk_diagnostic_snapshot.py`
- `scripts/evaluate/build_group_a_plus_asian_etf_tail_analytics_readiness_review.py`
- `scripts/misc/check_group_a_plus_daily_status.py`
- `tests/test_evaluate_cvar_tail_risk_diagnostic_shadow.py`

Latest regenerated outputs:

- `report/group_a_plus/latest/cvar_tail_risk_diagnostic.json`
- `report/group_a_plus/latest/asian_etf_tail_analytics_readiness_review.json`
- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`
- `results/group_a_plus_daily_status_20260720.json`
- `results/group_a_plus_daily_status_20260720.md`

Decision impact:

- reporting quality improved;
- optimizer remains blocked;
- no live strategy change.

## Blocking Reasons

- paper ETF universe not locally available;
- Asian ETF walk-forward validation missing;
- CVaR diagnostic is research-only;
- long-short ETF strategy is not allowed;
- `10%`, `20%`, `30%` leverage levels are not portable to GroupA+;
- transaction, borrow, financing, and shorting costs are missing;
- Rachev/STARR/Hill reporting is available for current GroupA+ exposures, but
  the optimizer and full paper-universe validation are not implemented;
- market impact and rebalance blockers remain active.

## Operational Conclusion

This paper can improve reporting discipline, not trading action.

Do not spend time tuning Markowitz/CVaR weights until:

- the required ETF universe is available;
- a cost model exists;
- STARR/Rachev/Hill monitors are implemented for current GroupA+ exposures;
- Taiwan GroupA+ walk-forward validation beats `Golden1_0531` and SRR-lite
  without raising false positives or turnover.

## Verification

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_asian_etf_tail_analytics_readiness_review.py
```

Result:

- `2 passed`

Pipeline / daily-status integration:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_asian_etf_tail_analytics_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_run_ncf_daily_pipeline.py tests/test_check_group_a_plus_daily_status.py
```

Result:

- `41 passed`

Rachev monitor improvement:

```bash
.venv/bin/python -m pytest tests/test_evaluate_cvar_tail_risk_diagnostic_shadow.py tests/test_build_group_a_plus_asian_etf_tail_analytics_readiness_review.py tests/test_check_group_a_plus_daily_status.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_run_ncf_daily_pipeline.py
```

Result:

- `42 passed`
