# Group A FinRL-X Gap Checklist

Date: 2026-05-24
Scope: Group A only
Purpose: clarify which FinRL-X capabilities are already absorbed into Group A, and which framework-level pieces are still separate.

## 1. Bottom Line

Group A already includes most of the strategy/runtime logic that matters for trading behavior:

- PVA/SJM overlay
- DCA
- inverse hedge rules
- LLM sentiment gate
- dividend handling
- next-open execution timing
- payload-driven signal replay

Evidence:

- Core Group A env/runtime knobs are built directly into [`train_dual_group_2024_2026.py`](train_dual_group_2024_2026.py) at lines covering Group A defaults and `PortfolioEnv` runtime args:
  - `DEFAULT_GROUP_A_*` settings at [`train_dual_group_2024_2026.py:52`](train_dual_group_2024_2026.py#L52)
  - env args at [`train_dual_group_2024_2026.py:1010`](train_dual_group_2024_2026.py#L1010)
  - exposure caps at [`train_dual_group_2024_2026.py:1261`](train_dual_group_2024_2026.py#L1261)
  - payload export blocks at [`train_dual_group_2024_2026.py:3943`](train_dual_group_2024_2026.py#L3943)
- Signal generation reads those runtime settings back from payload, instead of going through FinRL-X strategy interfaces:
  - [`generate_dual_group_signal.py:160`](generate_dual_group_signal.py#L160)

What is not integrated is the FinRL-X framework layer:

- `StrategyResult` / `BaseStrategy` / `RLCachedStrategy`
- weight-centric `BacktestEngine`
- FinRL-X `main.py` / `settings.py` / dashboard / trade executor path

The FinRL canonical README already separates these lanes:

- existing discrete PPO scripts remain the main workflow
- FinRL-X style backtesting is a separate path
- see [`FinRL/README.md:16`](FinRL/README.md#L16)

## 2. Already In Group A

These are effectively done and do not need another migration:

1. Runtime strategy logic
   Evidence:
   - [`train_dual_group_2024_2026.py:1017`](train_dual_group_2024_2026.py#L1017) to [`train_dual_group_2024_2026.py:1115`](train_dual_group_2024_2026.py#L1115)
   - includes DCA, PVA, inverse hold rules, sentiment thresholds, leverage caps.

2. Group A payload schema
   Evidence:
   - [`train_dual_group_2024_2026.py:3943`](train_dual_group_2024_2026.py#L3943) to [`train_dual_group_2024_2026.py:4057`](train_dual_group_2024_2026.py#L4057)
   - current canonical defensive example: [`results/group_a_runtime_payload_defensive_cap20_20260524.json`](results/group_a_runtime_payload_defensive_cap20_20260524.json)

3. Payload-to-runtime replay for signals
   Evidence:
   - [`generate_dual_group_signal.py:163`](generate_dual_group_signal.py#L163) to [`generate_dual_group_signal.py:250`](generate_dual_group_signal.py#L250)

4. Signal-side decision export
   Evidence:
   - [`generate_dual_group_signal.py:624`](generate_dual_group_signal.py#L624)

## 3. Must Connect

These are the missing pieces if the goal is to make Group A truly usable through the FinRL-X interface, not just to reuse isolated logic.

1. `Group A -> StrategyResult` adapter
   Current state:
   - Missing.
   - FinRL-X expects strategies to output `StrategyResult(weights=...)`, defined in [`FinRL/strategies/base_strategy.py:17`](FinRL/strategies/base_strategy.py#L17).
   - Group A currently outputs payload JSON and signal JSON, not `StrategyResult`.
   Why it matters:
   - Without this adapter, Group A cannot plug into the common FinRL-X backtest/live execution interface.
   Recommended implementation:
   - Add `group_a_finrlx_strategy.py` that wraps the current Group A model + payload replay and emits:
     - `weights`
     - `metadata["prices"]`
     - `metadata["weights_full"]`
     - decision/runtime context

2. `Group A -> FinRL-X BacktestEngine` adapter
   Current state:
   - Missing.
   - FinRL-X backtesting expects a `StrategyResult` and runs a weight-centric engine, see [`FinRL/backtesting/backtest_engine.py:73`](FinRL/backtesting/backtest_engine.py#L73).
   - Group A backtests currently run inside `PortfolioEnv` replay, not through `FinRLXBacktestEngine`.
   Why it matters:
   - Right now Group A performance numbers are not generated through the same backtest interface used by FinRL-X demo paths.
   Recommended implementation:
   - Export Group A replay weights to a daily/rebalance weight frame.
   - Feed that frame to `FinRL.backtesting.backtest_engine.BacktestEngine`.
   - Keep existing `PortfolioEnv` replay as the authoritative strategy simulator; use FinRL-X backtest as a comparison/reporting layer.

3. `Group A` dedicated FinRL-X entry script
   Current state:
   - Missing.
   - FinRL-X demo usage exists for cached models in [`FinRL/finrlx_demo_backtest.py:23`](FinRL/finrlx_demo_backtest.py#L23), but nothing equivalent exists for Group A triplet payloads.
   Why it matters:
   - Even if adapter classes exist, there is still no stable command to run Group A through the FinRL-X path.
   Recommended implementation:
   - Add a script such as `finrlx_group_a_backtest.py`:
     - input: payload path, model path override optional, date range
     - output: `StrategyResult` + `BacktestEngine` result + JSON summary

## 4. Good To Add

These are useful, but not required to claim that Group A has absorbed FinRL-X trading logic.

1. Payload-to-settings bridge
   Current state:
   - Missing.
   - FinRL-X app config is Pydantic-based in [`Stock_TaiwanII_FinRLX/src/config/settings.py:1`](Stock_TaiwanII_FinRLX/src/config/settings.py#L1).
   - Group A uses JSON payloads as runtime source of truth.
   Recommendation:
   - Do not replace payloads.
   - Add a thin translator if you want `main.py backtest` style entrypoints later.

2. FinRL-X smoke test for Group A
   Current state:
   - Missing.
   Recommendation:
   - Add one smoke test that verifies:
     - payload loads
     - adapter returns valid `StrategyResult`
     - `BacktestEngine.run()` succeeds on a short window

3. Dashboard/reporting hook
   Current state:
   - Missing.
   - FinRL-X `main.py` exposes dashboard/backtest/trade commands, see [`Stock_TaiwanII_FinRLX/src/main.py:21`](Stock_TaiwanII_FinRLX/src/main.py#L21).
   Recommendation:
   - Only do this if you actually need a UI on top of Group A.

## 5. Not Recommended

These are the parts I would not force into Group A unless the project direction changes.

1. Replace Group A `PortfolioEnv` replay with FinRL-X generic backtest as the canonical truth
   Reason:
   - Group A is not just a static weight generator.
   - It has stateful cooldown, inverse holding rules, PVA overlays, DCA flows, and next-open execution assumptions.
   - Those behaviors are already modeled in `PortfolioEnv`; reducing the strategy to pure weight playback risks semantic drift.

2. Force Group A into Alpaca trade execution path
   Reason:
   - The FinRL-X trade executor is currently wired around Alpaca-style execution flow, see [`Stock_TaiwanII_FinRLX/src/trading/trade_executor.py:28`](Stock_TaiwanII_FinRLX/src/trading/trade_executor.py#L28).
   - That is not the current operational path for this Taiwan ETF workflow.

3. Rewrite Group A control plane to be YAML/settings-first
   Reason:
   - Current canonical workflow is payload-first, and `generate_dual_group_signal.py` already depends on that contract.
   - Replacing it now adds migration cost without improving strategy quality.

## 6. Practical Answer

If the question is:

- "Did FinRL-X strategy logic make it into Group A?"
  - Mostly yes.
- "Can Group A already run as a first-class FinRL-X strategy/backtest/trade module?"
  - No.

The shortest real gap list is:

1. add `StrategyResult` adapter for Group A
2. add `BacktestEngine` bridge for Group A replay weights
3. add one dedicated FinRL-X entry script for Group A
4. optionally add smoke tests

Everything else is optional or not worth forcing right now.
