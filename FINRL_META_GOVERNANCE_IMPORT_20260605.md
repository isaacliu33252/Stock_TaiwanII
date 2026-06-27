# FinRL-Meta Governance Import 2026-06-05

## Scope

Imported six practical ideas from:

`C:\Users\isaac\Downloads\FinRL-Meta-master\FinRL-Meta-master`

into the local Taiwan strategy project. This does not modify FinRL-Meta-master itself.

## Imported Items

1. `last_action` / previous allocation awareness
   - Implemented in A/B governed diagnostics and rebalance event logs as:
     - `last_group_a_weight`
     - `pre_group_a_weight`
     - `target_group_a_weight`

2. Turnover / cost / trade log
   - A/B governed backtest now outputs a full top-level transfer log:
     - `results/group_ab_meta_governed_hold10_no2884_20240102_20260604_trade_log.csv`
   - Group A live signal now includes:
     - `trade_log_csv`
     - `execution_cost_summary`
     - per-ticker buy/sell notional, commission, ETF sell tax, slippage, total cost estimate.

3. Turbulence / market-stress gate
   - Implemented as a Group A drawdown + 21-day momentum stress gate for A/B allocation.
   - States:
     - `normal`
     - `caution`
     - `risk_off`
   - Risk-off can cap Group A top-level allocation.

4. Cooldown / min-trade threshold
   - Implemented in A/B governed allocator:
     - `cooldown_days`
     - `min_transfer_notional`
     - `drift_threshold`
   - Risk-off target changes can override cooldown.

5. Epoch-by-epoch OOS evaluation scaffold
   - Added scaffold output:
     - `results/group_ab_meta_governed_hold10_no2884_20240102_20260604_epoch_oos_scaffold.json`
   - Purpose: future retraining should freeze normalizer/scaler state after each epoch and evaluate deterministic policy on train + OOS windows.

6. Dataclass parameter governance
   - Added:
     - `finrl_meta_strategy_governance.py`
   - Core dataclasses:
     - `TradeCostParams`
     - `StressGateParams`
     - `ABGovernanceParams`
   - Each config has a deterministic `config_id`.

## New Files

- `finrl_meta_strategy_governance.py`
- `backtest_group_ab_meta_governed.py`
- `FINRL_META_GOVERNANCE_IMPORT_20260605.md`

## Modified Files

- `run_group_a_tdcc_improved_signal.py`

## Validation

Syntax check passed:

```bash
python3 -m py_compile finrl_meta_strategy_governance.py backtest_group_ab_meta_governed.py run_group_a_tdcc_improved_signal.py
```

A/B governed rerun passed:

```bash
python3 backtest_group_ab_meta_governed.py
```

Window: 2024-01-02 to 2026-06-04.

| Variant | Final | Sharpe | Max DD | Events | Cost |
|---|---:|---:|---:|---:|---:|
| dynamic lb126 band0.080 no-stress governance | 5,885,722 | 2.5780 | -19.01% | 7 | 1,866 |
| dynamic lb126 band0.080 with stress gate | 5,757,952 | 2.5626 | -19.01% | 7 | 3,792 |
| dynamic lb126 band0.080 strict cost/stress | 5,667,924 | 2.5182 | -18.95% | 5 | 5,895 |
| dynamic lb126 band0.030 with stress gate | 5,732,655 | 2.5573 | -19.01% | 7 | 4,226 |

## Current Interpretation

The imported governance improves auditability and execution realism.

For 2024-2026, the full stress gate is too conservative and lowers final value. The best practical governed A/B candidate is currently:

`dynamic_lb126_band008_hold10_no2884_no_stress`

This keeps:

- last-weight awareness
- cooldown
- min transfer threshold
- full cost and trade log
- dataclass config tracking
- epoch OOS scaffold

but does not cap Group A through the stress gate during this 2024-2026 regime.

The stress gate should remain available as a 2008/crash-risk option, not the default 2024-2026 return-maximizing setting.
