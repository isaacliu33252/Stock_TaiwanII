# GroupA+ Recent Paper Import Status - 2026-08-07

## Scope

This addendum covers the recent paper-related work after the
`docs/GROUPA_PLUS_PDF_RESEARCH_DECISION_MATRIX_20260717.md` matrix:

- `C:\Users\isaac\Downloads\2605.24345.pdf`
- `C:\Users\isaac\Downloads\2605.01954.pdf`
- `C:\Users\isaac\Downloads\2603.05862.pdf`

Related prior-research crosscheck:

- `docs/GROUPA_PLUS_SIMILAR_RESEARCH_CROSSCHECK_20260807.md`

Current convergence ranking artifact:

- `report/group_a_plus/latest/paper_convergence_review.json`

Current guarded-monitor artifact:

- `report/group_a_plus/latest/defensive_cash_floor_guarded_monitor.json`

Decision status is unchanged:

- no live target-weight change;
- no automatic rebalance;
- no automatic `00631L.TW` add;
- no automatic `00632R.TW` open;
- `Golden1_0531` remains unchanged;
- all recent imports remain shadow, review-only, guarded-monitoring, or
  execution-review gated.

## Executive Summary

The paper-related implementation work is complete for the current review pass.
Each recent paper has been mapped into GroupA+ as deterministic diagnostics or
governance artifacts, then checked with focused tests or replay/backtest
validation.

No paper item is promoted to live trading because the evidence is either
sample-limited, advisory-only, or still blocked by execution/source-freshness
guards. The imported value is risk control, attribution, and review discipline,
not a new live alpha model.

The current convergence review ranks `defensive_cash_floor_high_risk_state` as
the closest correct use of the paper set. Its score is `0.776`, and the manual
approval validation is now valid for guarded candidate target output only. The
current decision is `candidate_ready_for_guarded_monitoring`, not live
promotion. The guarded monitor currently has `0` trigger rows, so no rollback
condition is active.

## Recent Decision Matrix

| Paper | Imported benefit | Main artifacts | Current validation | Live impact |
| --- | --- | --- | --- | --- |
| `2605.24345` | Adaptive quantile risk posture and defensive cash-floor candidate | `adaptive_quantile_risk_gate_shadow.json`, `defensive_cash_floor_signed_promotion_review.json`, `defensive_cash_floor_signed_approval_validation.json`, `defensive_cash_floor_guarded_candidate.json` | Frame replay `607` rows; defensive cash floor improved return and drawdown on triggered windows, but sparse `27` changed-day evidence; manual approval validation is valid for guarded target output only | Guarded-monitoring candidate / no auto rebalance / no broker order / no live promotion |
| `2605.01954` | Moira-style hierarchical credit attribution, relationship thesis, policy critic, event-aware execution review, compact semantic context | `hierarchical_credit_review_shadow.json`, `relative_exposure_thesis_shadow.json`, `moira_policy_critic_shadow.json`, `moira_policy_critic_validation_shadow.json`, `moira_execution_guard_hard_stop_backtest_shadow.json`, `daily_semantic_context_summary.json` | Relevant tests passed; hard-stop backtest has too few strict actionable triggers for promotion | Review-only / no prompt-driven live policy / no target change |
| `2603.05862` | LETF liquidity feedback watch for `00631L.TW` and large `00632R.TW` hedge adds | `letf_liquidity_feedback_watch_shadow_backtest.json`, liquidity-aware event-quality output | 2015-01-05 to 2026-08-07, `2826` rows, `313` triggers; manual-review candidate only | Liquidity warning only / no automatic block or order |

## 2026-08-31 Addendum - `2606.26625`

`2606.26625` was rechecked against the latest GroupA+ strategy and extended
with a Taiwan ETF CVaR/cost window-split audit.

Artifacts:

- `report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json`
- `report/group_a_plus/latest/2606_26625_cvar_cost_window_split.json`
- `report/group_a_plus/latest/2606_26625_cvar_cost_window_split.md`
- `report/group_a_plus/latest/2606_26625_rolling_tail_no_add_gate.json`
- `report/group_a_plus/latest/2606_26625_rolling_tail_no_add_gate.md`
- `docs/HANDOFF_2606_26625_COMMODITY_ETF_CVAR_TAIL_COST_GROUPA_PLUS_20260718.md`

Latest result:

- `dynamic_cvar_tail_cost_readiness_review.status = blocked`;
- `2606_26625_cvar_cost_window_split.status = blocked_for_live_promotion`;
- valid windows: `5`;
- latest loses to `no_00631l_to_cash` on ES95 or MDD: `5/5`;
- latest loses to `no_letf_to_cash` on ES95 or MDD: `4/5`;
- parent readiness blocker is now
  `cvar_cost_window_split_2606_26625_failed`, not merely missing validation;
- `2606_26625_rolling_tail_no_add_gate.status = available_for_shadow_monitoring`
  (rolling 63/126/252-day CVaR+Hill no-add dashboard, wired into the daily
  pipeline as its own shadow gate, separate from the fixed-window audit above);
- rolling gate: `allow_00631l_add = false` (blocked in `3/3` windows on ES95
  gap and/or Hill tail index), `allow_00632r_open = true` (`0/3` windows
  blocked).

Live impact:

- research/shadow governance only;
- no live strategy change;
- no target-weight change;
- no automatic rebalance;
- no `00631L.TW` add;
- no `00632R.TW` open;
- no `00679B.TWO` add;
- no CVaR optimizer, ARMA-GARCH copula optimizer, PPO, or model promotion.

## 2026-08-31 Addendum - `2604.08356`

`2604.08356` ("Measuring Strategy-Decay Risk: Minimum Regime Performance and
the Durability of Systematic Investing", Alexander & Fabozzi) was reviewed
for the first time this session (previously unreviewed -- found among 9
Downloads PDFs with no trace in docs/registry/memory).

Full handoff:
`docs/HANDOFF_2604_08356_MRP_STRATEGY_DECAY_GROUPA_PLUS_20260831.md`.

Imported concept: MRP1 (worst realized Sharpe across one exhaustive-search
split of a return series) as a periodic shadow-governance robustness
diagnostic, not a live switch trigger.

Artifacts:

- `scripts/evaluate/evaluate_group_a_plus_2604_08356_mrp_strategy_decay.py`
- `report/group_a_plus/latest/2604_08356_mrp_strategy_decay.json`
- `report/group_a_plus/latest/2604_08356_mrp_strategy_decay.md`

Result (`as_of = 2026-08-18`, production switch-policy equity curve):

- production `switch_ma80_dd11`: full-sample Sharpe `1.159`, MRP1 `0.307`;
- `golden1_0531` alone: full-sample Sharpe `1.115`, MRP1 `0.217`;
- defensive basket alone: full-sample Sharpe `1.112`, MRP1 `0.155`;
- production strictly dominates both baselines on the paper's decay-risk
  frontier (higher Sharpe AND higher MRP1) -- a positive, independently
  derived confirmation that the switch policy is more robust in its own
  worst historical regime, not just higher-Sharpe on average.

Live impact: none. Diagnostic/governance only, intentionally not wired into
the daily pipeline yet (no actionable threshold, just a robustness
statistic; revisit once there is a second data point to show a trend). No
target-weight change, no orders, no rebalance.

Side finding (not investigated further, flagged for a future session):
`results/group_a_plus_switch_policy_backtest_longhist_rebalmonthly_20150401_20260810_curve.csv`
has a `switch_risk_ma80_dd11_total6_hold5_eg015_xg015` column that is
byte-identical to `golden1_0531_1m` for its entire 2017-2026 history -- a
stale/mis-generated report artifact, not a live-strategy bug (confirmed the
real production backtest curve does switch correctly).

## 2605.24345 - Adaptive Quantile Risk MDP

Implemented:

- `group_a_plus/integrations/adaptive_quantile_risk_gate.py`
- adaptive quantile risk-gate builder and backtests;
- defensive cash-floor sweep, validation, fold ablation, signed-promotion
  package, and disabled guarded-candidate wrapper.

Key result:

- Initial saved-signal replay improved total return, max drawdown, and worst day
  on limited saved snapshots.
- Full latest-runner frame replay showed the original 00631L cap had almost no
  room to act because the latest runner already has little or no `00631L.TW`.
- The stronger candidate is `cash55_risk7_tail1`: in defensive high-risk states,
  raise cash floor to `55%` when `total_risk_score >= 7` or
  `tail_risk_score >= 1`.

Why not live:

- evidence is concentrated in only `27` changed days;
- 2024 folds have no trigger days and are evidence-neutral;
- manual approval validation is valid only for guarded candidate target output;
- the current 2026-08-07 signal does not trigger the rule because the execution
  regime is `golden1`, not `group_a_plus_defensive`;
- the guarded monitor is implemented and will evaluate the first `10` actual
  trigger days against the raw target;
- guarded candidate output does not modify the live runner, does not auto
  rebalance, and does not create broker orders.

## 2605.01954 - Moira

Implemented:

- `hierarchical_credit_review_shadow`
- `relative_exposure_thesis_shadow`
- `event_aware_execution_quality_shadow`
- `moira_policy_critic_shadow`
- `moira_policy_critic_validation_shadow`
- `moira_execution_guard_hard_stop_backtest_shadow`
- `daily_semantic_context_summary`

Current useful outputs:

- forecast-vs-actual attribution separates stale data, selection error,
  execution error, risk-guard error, and market noise;
- relationship thesis checks whether `0050.TW`, `00631L.TW`, `00632R.TW`, bond,
  and cash posture is coherent;
- policy critic proposes rule text only under an immutable contract;
- validation keeps a trigger ledger so proposals can be replayed before any
  guarded review;
- daily semantic context reduces noisy input for future review modules.

Why not live:

- Moira's original setting is U.S. stock pair trading, not Taiwan ETF allocation;
- `0050/00631L` is leverage/path dependency, not a market-neutral pair;
- the policy critic is explicitly forbidden from editing code, weights, or
  orders;
- only the execution-guard hard-stop proposal had enough replay triggers for a
  first formal shadow backtest, and it still did not meet promotion thresholds.

## 2603.05862 - LETF/Futures Liquidity Feedback

Implemented:

- `group_a_plus/integrations/letf_liquidity_feedback.py`
- `scripts/evaluate/backtest_group_a_plus_letf_liquidity_feedback_watch_shadow.py`
- tests for the module and CLI;
- daily-pipeline step `letf_liquidity_feedback_watch_shadow_backtest`;
- liquidity-feedback input into `event_aware_execution_quality_shadow`.

Current backtest:

- date range: `2015-01-05` to `2026-08-07`;
- rows: `2826`;
- triggers: `313`;
- recommendation: `manual_review_shadow_candidate`;
- `00631L.TW` trigger days had positive average forward returns but large
  forward drawdown risk;
- `00632R.TW` trigger days had poor 5/10/20-day forward return behavior and a
  `74.242424%` 20-day negative forward-return rate.

Why not live:

- the paper is artificial-market simulation, not direct Taiwan ETF evidence;
- current GroupA+ proxy uses daily data rather than order-book depth/tightness;
- it supports staging and manual review for large LETF/inverse trades, not an
  automatic allocation rule.

## Pipeline Status

The recent paper modules are wired into the daily pipeline as best-effort or
review-only steps. The latest dry-run after the `2603.05862` integration
completed with `97` commands.

Important pipeline points:

- `letf_liquidity_feedback_watch_shadow_backtest` runs after LETF tracking-error
  readiness and before Asian ETF tail analytics readiness.
- Moira-related review steps run as deterministic diagnostics and do not mutate
  strategy state.
- Event-aware execution quality can now consume liquidity feedback, but its
  output remains advisory-only.

## Open Research-Only Items

These are not unfinished basic implementation work; they are promotion blockers
or future validation work:

- collect more saved live-signal and execution-plan snapshots for Moira proposal
  replay;
- add quote/order-book data if available to replace daily liquidity proxies for
  LETF liquidity feedback;
- run deeper crisis-window validation for the defensive cash-floor candidate;
- keep signed approval required before any guarded candidate can affect live
  targets;
- continue preserving `Golden1_0531` as the unchanged baseline.

## Bottom Line

For the current paper batch, the transferable advantages have been imported into
GroupA+ as shadow/review modules. The implementation is complete enough for
daily review, but not complete enough for live promotion. The correct next
paper-related step is more validation data and signed-review governance, not
automatic trading-rule activation.
