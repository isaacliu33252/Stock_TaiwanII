# Handoff: 2512.10913 RL Financial Decision Systematic Review for GroupA+（2026-07-20）

## Decision

`2512.10913.pdf` is useful as RL governance evidence, not as a trading strategy.

Import only:

- explainability requirement;
- robustness / non-stationarity requirement;
- standardized benchmarking requirement;
- implementation-quality over algorithm-complexity principle;
- deployment feasibility and auditability discipline;
- risk-management-first RL promotion rules.

Do not import:

- RL allocator;
- market-making policy;
- high-frequency order-book assumptions;
- cryptocurrency RL conclusions;
- automatic rebalance;
- `00631L` add permission;
- `00632R` open permission.

## Current Strategy

No change to `2026-07-20` GroupA+ stance:

- strategy: `a2118_a2111_ncf_late_bull_deleverage`;
- regime: `golden1`;
- `Golden1_0531`: unchanged;
- `00631L = 500`: do not add;
- `00632R = 0`: do not open;
- no automatic rebalance.

## Why No Live Import

- The paper is a systematic review, not a validated Taiwan ETF model.
- Strongest RL evidence is market making / crypto, not daily ETF allocation.
- Portfolio optimization benefits appear mature / limited relative to
  implementation quality.
- GroupA+ lacks high-frequency market-making data and should not add live
  exploration risk.
- Existing GroupA+ blockers already prevent leverage add and automatic RL
  promotion.

## Existing GroupA+ Coverage

The paper's useful points are already largely represented by:

- `deployment_consistency_review.json`
- `market_impact_readiness_review.json`
- `intervention_fatigue_risk_budget_readiness_review.json`
- `synthetic_augmentation_validation_readiness_review.json`
- `dynamic_cvar_tail_cost_readiness_review.json`
- `research_shadow_decision_snapshot.json`
- `ops_health.json`
- `daily_status.json`

## Artifacts

- `docs/2512_10913_RL_FINANCIAL_DECISION_SYSTEMATIC_REVIEW_GROUPA_PLUS_REVIEW_20260720.md`
- `docs/HANDOFF_2512_10913_RL_FINANCIAL_DECISION_SYSTEMATIC_REVIEW_GROUPA_PLUS_20260720.md`
- `docs/DETAILED_HANDOFF_2512_10913_RL_GOVERNANCE_GROUPA_PLUS_20260720.md`
- `docs/GROUPA_PLUS_PDF_RESEARCH_DECISION_MATRIX_20260717.md`
- `scripts/evaluate/build_group_a_plus_rl_governance_readiness_review.py`
- `tests/test_build_group_a_plus_rl_governance_readiness_review.py`
- `report/group_a_plus/latest/rl_governance_readiness_review.json`
- `report/group_a_plus/rl_governance_readiness/history/rl_governance_readiness_20260720.json`
- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`

## Implemented Status

`rl_governance_readiness_review.json` is implemented and connected to the
research shadow snapshot.

Latest output:

- status: `blocked`;
- `rl_governance_ready = false`;
- `rl_component_promotable = false`;
- `live_rl_allocator_allowed = false`;
- `target_weight_change_allowed = false`;
- `auto_rebalance_allowed = false`;
- `allow_00631l_add = false`;
- `allow_00632r_open = false`;

The research shadow snapshot now includes:

- `rl_governance_status = blocked`;
- `rl_governance_ready = false`;
- `rl_component_promotable = false`;
- `live_rl_allocator_allowed = false`;
- `rl_governance_allow_00631l_add = false`.

Focused tests:

- `.venv/bin/python -m pytest tests/test_build_group_a_plus_rl_governance_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py`
- result: `4 passed`

## Next Candidate Work

Default recommendation:

- do not build new RL strategy;
- do not tune live weights from this paper;
- keep this paper as a governance reference only.
