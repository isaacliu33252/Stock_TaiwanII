# Handoff: 2605.17307 SAC Global RL for GroupA+

Date: 2026-08-25  
Project root: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main`  
Paper: `C:/Users/isaac/Downloads/2605.17307.pdf`  
Title: `Deep Reinforcement Learning Framework for Diversified Portfolio Management Across Global Equity Markets`  
Scope: GroupA+ / A21.18 import review.

## Final Decision

Do not change live weights.

The latest active strategy remains:

- `a2118_a2111_ncf_late_bull_deleverage`

Do not import:

- full SAC actor-critic optimizer
- LSTM/Transformer policy training
- hierarchical Dirichlet policy as live allocator
- RL-generated target weights
- automatic rebalancing

Global decisions:

- `train_sac_now = false`
- `train_lstm_or_transformer_policy_now = false`
- `allow_rl_generated_target_weights = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `replace_a2118 = false`

Review artifact:

- `report/group_a_plus/latest/2605_17307_sac_global_rl_readiness_review.json`
- `report/group_a_plus/latest/2605_17307_ir2_candidate_scorecard.json`
- `report/group_a_plus/latest/2605_17307_hierarchical_cash_equity_shadow.json`
- `report/group_a_plus/latest/2605_17307_sac_feasibility_smoke.json`
- `report/group_a_plus/latest/2605_17307_adaptive_retraining_cadence_audit.json`
- `report/group_a_plus/latest/2605_17307_cross_market_confirmation_monitor.json`

## Paper Summary

The paper evaluates Soft Actor-Critic portfolio allocation across three global equity markets:

- NASDAQ-100
- Nikkei 225
- EURO STOXX 50

The framework uses:

- daily walk-forward optimization
- 5-year training / 1-year validation / 1-year test
- adaptive retraining based on rolling validation Sharpe
- LSTM or Transformer encoders
- Dirichlet long-only weight generation
- flat or hierarchical equity/cash policy
- transaction cost, turnover, and concentration penalties
- cash-allowed and fully invested configurations

The paper's central hypothesis is only partially confirmed:

- no RL strategy has statistically significant excess returns over Buy & Hold across all markets under HAC/bootstrap tests
- EURO STOXX 50 is the strongest single market
- ensemble portfolios improve IR2 economically but statistical evidence remains limited
- LSTM-based models are more stable than Transformer
- hierarchical equity/cash policy improves volatility and drawdown control
- cash-allowed configurations improve drawdown-adjusted performance

## Reusable Ideas for GroupA+

These ideas are useful as governance or shadow-review design, not as live allocation engines.

1. Walk-forward plus adaptive retraining review
   - Useful for future model-governance checks.
   - Do not retrain daily just because data updated.
   - Reopen training only when validation/live shadow evidence deteriorates enough.

2. Hierarchical equity/cash decision
   - The paper's LSTM_2 separates equity/cash from asset selection and improves risk control.
   - For GroupA+, this maps to existing staged cash/ETF decisions, not a new allocator.

3. Cash-allowed flexible exposure
   - The paper supports cash as a drawdown-control tool.
   - This reinforces current guarded cash-heavy A21.18 behavior.

4. Turnover and concentration penalties
   - The paper penalizes turnover and Herfindahl concentration.
   - GroupA+ already has turnover/cost gates; this paper supports keeping those gates strict.

5. Regime-dependent active allocation
   - RL works better during elevated uncertainty and lower trend persistence.
   - This maps to existing HIGH/EXTREME and specialist-router shadow monitors.

6. Cross-market ensemble diversification
   - The paper's ensemble improves economic IR2.
   - For GroupA+, this is only a monitoring lens for cross-market confirmation, not a reason to add foreign ETFs automatically.

## Why Full SAC Is Not Recommended Now

This is a stop decision, not a missing experiment.

Reasons:

- The paper itself does not show robust statistical outperformance across all markets.
- GroupA+ has a small ETF/cash regime universe, not hundreds of cross-sectional stocks.
- Current A21.18 decisions are constrained by regime, execution cost, and promotion gates.
- Full SAC would add high training cost, unstable hyperparameters, and drift/overfit risk.
- Transformer did not clearly improve over LSTM in the paper.
- The strongest reusable effects are simple: cash flexibility, turnover penalty, and regime-aware evaluation.

The correct import is a readiness/governance review, not live RL allocation.

## If Reopened Later

Only consider new experiments in this order:

1. Cheap governance metric
   - Compare current GroupA+ candidates by IR2-like drawdown-adjusted score.
   - No model training.
   - Completed on `2026-08-25`.

2. Hierarchical cash/equity shadow
   - Test whether separating "risk budget/cash" from "ETF selection" improves current A21.18 shadow choices.
   - No SAC.
   - Completed on `2026-08-25`.

3. SAC feasibility smoke
   - Check local SAC dependencies, GroupA+ data panel, action-space requirements, and promotion blockers.
   - No SAC policy training.
   - No backtest.
   - No model file.
   - Completed on `2026-08-25`.

4. Adaptive retraining cadence audit
   - Apply the paper's validation-Sharpe deterioration logic to existing shadow models.
   - Goal: reduce unnecessary retraining, not improve weights.
   - Completed on `2026-08-25`.

5. Cross-market confirmation monitor
   - Use existing cross-market OHLCV panels as confirmation-only features.
   - No foreign ETF allocation unless separately approved.
   - Completed on `2026-08-25`.

6. Full SAC/LSTM
   - Only if the first four show incremental OOS economic value and governance approves training.

## Commands

Build review:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2605_17307_sac_global_rl_readiness_review.py
```

Build IR2-like candidate scorecard:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2605_17307_ir2_candidate_scorecard.py
```

Build hierarchical cash/equity shadow:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2605_17307_hierarchical_cash_equity_shadow.py
```

Build SAC feasibility smoke:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2605_17307_sac_feasibility_smoke.py
```

Build adaptive retraining cadence audit:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2605_17307_adaptive_retraining_cadence_audit.py
```

Build cross-market confirmation monitor:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2605_17307_cross_market_confirmation_monitor.py
```

Run tests:

```bash
.venv/bin/python -m pytest \
  tests/test_build_group_a_plus_2605_17307_sac_global_rl_readiness_review.py \
  tests/test_build_group_a_plus_2605_17307_ir2_candidate_scorecard.py \
  tests/test_build_group_a_plus_2605_17307_hierarchical_cash_equity_shadow.py \
  tests/test_build_group_a_plus_2605_17307_sac_feasibility_smoke.py \
  tests/test_build_group_a_plus_2605_17307_adaptive_retraining_cadence_audit.py \
  tests/test_build_group_a_plus_2605_17307_cross_market_confirmation_monitor.py
```

## Current Result

As of `2026-08-25`:

- latest strategy remains `a2118_a2111_ncf_late_bull_deleverage`
- 2605.17307 is imported as review-layer evidence only
- no target weight changes are allowed
- no SAC/LSTM/Transformer training is recommended now

IR2-like scorecard result:

- raw best by score: `equal_0050_00631l_cash`
- governance interpretation: benchmark-only, not a trade candidate
- best governed candidate: `staged_ladder_00631l_to_4pct`
- active now: false
- blocker: latest risk-aversion state is `HIGH`, not `EXTREME`
- conclusion: supports keeping staged 4% as future manual-review candidate only; no live change

Hierarchical cash/equity shadow result:

- best fixed-grid hierarchical candidate: `raw_a2118_70_30_sleeve_equity_40pct`
- reviewable now: false
- reason: raw A21.18 sleeve is already blocked by existing tail/cost governance, and latest risk-aversion state is `HIGH`
- staged 4% sleeve at 30% equity budget IR2-like: `0.746499`
- conclusion: hierarchical decomposition is useful as an analysis lens, but it does not create a new live target or justify SAC training

SAC feasibility smoke result:

- local dependencies are present:
  - `torch = true`
  - `stable_baselines3 = true`
  - `gymnasium = true`
- local SAC environment smoke can run: `true`
- paper-style SAC training ready: `false`
- GroupA+ panel:
  - start: `2020-01-03`
  - end: `2026-08-25`
  - observations: `1613`
  - missing return ratio: `0.0`
  - paper-style 5y train / 1y validation / 1y test requires about `1764` trading observations
  - shortfall: `151` trading observations
- action design:
  - assets: `0050.TW`, `00631L.TW`, `00632R.TW`, `00679B.TWO`, `cash`
  - action dimension: `5`
  - paper uses Dirichlet simplex allocation
  - Stable-Baselines3 SAC uses native `Box` actions, so GroupA+ still needs a custom long-only, sum-to-one action wrapper before any real SAC training
- active context:
  - latest strategy remains `a2118_a2111_ncf_late_bull_deleverage`
  - latest 2606 risk-aversion state is `HIGH`
  - staged ladder is not ready now
- blockers:
  - `insufficient_history_for_paper_style_5y_1y_1y_walk_forward`
  - `stable_baselines3_sac_uses_box_action_not_native_dirichlet_simplex_policy`
  - `groupa_plus_needs_custom_long_only_sum_to_one_action_projection_before_any_sac_training`
  - `no_sac_oos_promotion_gate_exists_for_groupa_plus_live_weights`
- decision:
  - `train_sac_now = false`
  - `minimal_sac_training_trial_recommended_now = false`
  - `allow_sac_generated_target_weights = false`
  - `target_weight_change_allowed = false`
  - `replace_a2118 = false`

Interpretation:

- The environment is not the blocker.
- The blocker is research/governance readiness.
- A future SAC experiment should first build a constrained simplex action wrapper and a pure shadow OOS promotion gate. Until then, SAC must not produce target weights.

Adaptive retraining cadence audit result:

- imported idea: only retrain when validation/shadow evidence deteriorates
- today result: no retraining trigger fires
- `train_any_model_now = false`
- `models_requiring_retraining_review = []`
- `promotion_reviews_open_now = []`
- `target_weight_change_allowed = false`
- audited items:
  - `a2118_seed_averaging_preferred_ensemble_42_43_44`
    - forward rows: `2`
    - minimum forward rows: `20`
    - parity pass rate: `0.0`
    - minimum parity pass rate: `0.95`
    - decision: continue daily forward shadow until minimum rows; do not retrain yet
  - `2605_17307_sac_candidate`
    - local SAC smoke can run, but paper-style SAC is not ready
    - decision: do not schedule training until simplex wrapper, OOS gate, and WFO history are ready
  - `2606_09104_risk_aversion_prior_monitor`
    - latest risk-aversion state: `HIGH`
    - decision: continue monitoring; only open staged 00631L review if `EXTREME`
  - `2411_19649_downside_diversification_forecast_shadow`
    - decision: keep as shadow gate only until realized bucket value is stable

Interpretation:

- The paper's adaptive retraining idea is useful, but today it says "do not train."
- Seed averaging should accumulate forward evidence first.
- SAC should not be started merely because dependencies exist.
- Latest strategy remains `a2118_a2111_ncf_late_bull_deleverage`.

Cross-market confirmation monitor result:

- imported idea: use cross-market context as confirmation-only evidence
- state: `WEAK`
- reason: `directed_graph_shadow_stale_for_daily_confirmation`
- production effect: `none`
- `can_confirm_new_risk_adds = false`
- `blocks_live_trade = false`
- `target_weight_change_allowed = false`
- `foreign_etf_allocation_allowed = false`
- source freshness:
  - max watched source stale days: `1`
  - missing watched sources: none
  - SOXX/QQQ/NVDA/TSM latest: `2026-08-24`
  - 0050/00631L/2330 latest: `2026-08-25`
- TSI stress:
  - alarm active: `false`
  - TSI percentile: `0.6218`
  - TSI memory percentile: `0.8052`
- Mingle exposure graph:
  - end: `2026-08-21`
  - stale days: `4`
  - promotion allowed: `false`
- directed graph:
  - generated at: `2026-07-15T17:44:53`
  - source end: `2026-07-15`
  - stale days: `41`
  - latest action: `NO_ADD`
  - NO_ADD probability: `0.5921`
  - NO_ADD active: `false` because it is below the existing `0.65` alert threshold
  - NO_ADD AUC: `0.5320`
  - REENTER AUC: `0.4846`

Interpretation:

- Cross-market data itself is fresh enough.
- Cross-market stress is not currently alarming.
- But the directed graph model is too stale for strong daily confirmation.
- Therefore this monitor cannot confirm new risk adds today.
- It still does not block live trading because it is confirmation-only.
