#!/usr/bin/env python3
"""Research-only: M6 — reconcile a2118's own backtest against FinRL's engine.

Context (2026-07-02 Fable 5 audit, M6): a2118's Sharpe/MDD have only ever
been computed by this project's own `_simulate_costed_curve`
(`backtest_group_a_plus_defensive_basket.py`), never cross-checked against
`FinRL/backtesting/backtest_engine.py`'s independent weight-driven engine
(`bt`-library based) for the *same* regime/weight sequence. This script
feeds a2118's actual daily target weights (regime -> base_weights, resolved
day by day exactly as `_simulate_costed_curve` would use them) into that
second engine and compares the resulting P&L/metrics.

This does NOT touch any live/production file -- it only reads a2118's
report/frame output and reloads prices for the comparison run.

Known methodological differences from the start (not implementation bugs
if the results diverge for these reasons -- see the printed caveats):
  - FinRL's BacktestEngine (`_cost_fn`) does not model slippage at all;
    a2118's own curve includes `slippage_rate=0.0005` on every trade.
  - FinRL's BacktestEngine applies one `tax_rate` to every ticker; a2118
    distinguishes equity-ETF sell tax (0.001) from bond-ETF sell tax (0.0).
    This script sets `tax_rate=0.001` (closer to the equity-ETF side) as
    the best single-parameter approximation.
  - `bt`'s `WeighTarget` + `Rebalance` algos decide their own execution-day
    semantics for reaching a target weight, which may not exactly match
    `_simulate_costed_curve`'s own share-tracked rebalancing logic.
  - Cash is modeled as a zero-return, constant-price synthetic instrument
    (price=1.0 every day) since FinRL's engine needs a priced column for
    every non-zero weight; this matches a2118's own zero-return cash
    assumption.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/evaluate/evaluate_a2118_finrl_dual_engine_reconciliation.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from backtest_group_a_plus_defensive_basket import _load_total_return_prices
from backtest_group_a_plus_switch_policy import DB_PATH
from FinRL.backtesting.backtest_engine import BacktestConfig, BacktestEngine
from FinRL.strategies.base_strategy import StrategyResult
from group_a_plus.runners.a2118 import CHIP_DATA_FALLBACK_MAX_STALE_DAYS, _resolve_end_date, run_a2118

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_H20_MAX = 0.33
PRODUCTION_CONF_MIN = 0.55
PRODUCTION_H5_REENTRY_MIN = 0.55
# Explicit, not just inherited from run_a2118's default: pin to whatever
# strategy.json's production runner_params actually use, so this
# reconciliation can't silently start reflecting a different chip-data-outage
# policy than production just because a2118.py's own default changed (2026-07-06).
PRODUCTION_CHIP_DATA_FALLBACK_MAX_STALE_DAYS = CHIP_DATA_FALLBACK_MAX_STALE_DAYS


def _daily_weights_from_regime(frame: pd.DataFrame, base_weights: dict[str, dict[str, float]]) -> pd.DataFrame:
    """Resolve each day's target weights from its execution_regime, exactly
    the same lookup `_simulate_costed_curve` performs (weights_by_regime[regime])."""
    rows = []
    for day, regime in frame["execution_regime"].items():
        weights = base_weights.get(str(regime))
        if weights is None:
            raise KeyError(f"No base_weights entry for regime={regime!r} on {day}")
        rows.append(weights)
    return pd.DataFrame(rows, index=frame.index).fillna(0.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260630.csv"))
    parser.add_argument("--output", default="results/a2118_m6_dual_engine_reconciliation_20260703.json")
    args = parser.parse_args()

    resolved_end = _resolve_end_date(Path(DB_PATH), "latest")

    report, frame = run_a2118(
        start="2025-01-02",
        end=resolved_end,
        initial_value=1_000_000.0,
        db=DB_PATH,
        ncf_panel_631l_path=args.panel,
        h20_max=PRODUCTION_H20_MAX,
        conf_min=PRODUCTION_CONF_MIN,
        h5_reentry_min=PRODUCTION_H5_REENTRY_MIN,
        chip_data_fallback_max_stale_days=PRODUCTION_CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    )

    daily_weights = _daily_weights_from_regime(frame, report["base_weights"])

    prices, _dividend_coverage = _load_total_return_prices(DB_PATH, frame.index)
    prices = prices.copy()
    if "cash" in daily_weights.columns and "cash" not in prices.columns:
        prices["cash"] = 1.0

    strategy_result = StrategyResult(
        strategy_name="a2118_finrl_bridge",
        weights=daily_weights,
        metadata={"prices": prices},
    )

    engine = BacktestEngine(
        BacktestConfig(
            start_date=str(frame.index[0].date()),
            end_date=str(frame.index[-1].date()),
            initial_capital=1_000_000.0,
            brokerage_fee=0.001425,
            tax_rate=0.001,  # approximation -- see module docstring
            risk_free_rate=0.0,  # match _metrics()'s own convention, not FinRL's 0.02 default
            benchmark_tickers=["0050.TW"],
        )
    )
    finrl_result = engine.run(strategy_result)

    a2118_metrics = report["metrics"]
    finrl_metrics = finrl_result.metrics

    comparison = {
        "sharpe_ratio": {"a2118_own_engine": a2118_metrics["sharpe_ratio"], "finrl_engine": finrl_metrics["sharpe"]},
        "annual_return": {"a2118_own_engine": a2118_metrics["annual_return"], "finrl_engine": finrl_metrics["annual_return"]},
        "max_drawdown": {"a2118_own_engine": a2118_metrics["max_drawdown"], "finrl_engine": finrl_metrics["max_drawdown"]},
        "total_return": {"a2118_own_engine": a2118_metrics["total_return"], "finrl_engine": finrl_metrics["total_return"]},
    }

    result = {
        "schema_version": 1,
        "report_type": "a2118_m6_dual_engine_reconciliation",
        "status": "research_only",
        "active_allocation_impact": "none",
        "note": (
            "M6 research: does FinRL's independent weight-driven backtest "
            "engine (bt library) agree with a2118's own _simulate_costed_curve "
            "for the SAME daily target weights? Does not touch any live file."
        ),
        "known_methodology_differences": [
            "FinRL engine does not model slippage (a2118 uses slippage_rate=0.0005)",
            "FinRL engine uses one tax_rate=0.001 for all tickers (a2118 distinguishes equity-ETF 0.001 vs bond-ETF 0.0)",
            "bt's WeighTarget+Rebalance execution-day semantics may differ from _simulate_costed_curve's own rebalancing logic",
            "cash modeled as a constant price=1.0 synthetic instrument",
        ],
        "window": {"start": str(frame.index[0].date()), "end": str(frame.index[-1].date())},
        "comparison": comparison,
        "a2118_own_engine_full_metrics": a2118_metrics,
        "finrl_engine_full_metrics": finrl_metrics,
    }

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print("Metric comparison (a2118's own _simulate_costed_curve vs FinRL BacktestEngine):")
    for metric, values in comparison.items():
        own = values["a2118_own_engine"]
        finrl = values["finrl_engine"]
        diff = finrl - own
        print(f"  {metric:16s} own={own:+.4f}  finrl={finrl:+.4f}  diff={diff:+.4f}")
    print(f"\nSaved: {args.output}")


if __name__ == "__main__":
    main()
