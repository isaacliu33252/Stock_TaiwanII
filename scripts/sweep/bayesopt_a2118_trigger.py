#!/usr/bin/env python3
"""Bayesian Optimisation sweep for A21.18 late-bull NCF trigger parameters.

Replaces the manual 15-combo grid (h20_max × conf_min) with a Gaussian-Process
surrogate that guides the search.  Search space adds h5_reentry_min as a 3rd
dimension, which the grid never explored.

Data loading is done ONCE before the optimisation loop; each probe only runs the
lightweight overlay + simulate step (~milliseconds) rather than reloading prices
from SQLite every iteration.

Objective
---------
  score = sharpe_ratio - λ_trigger × max(0, trigger_rate - max_trigger_rate)

  λ_trigger = 1.0 by default.  Over-triggering causes excessive turnover and
  commission drag, so the penalty discourages parameters that fire on too many
  days.  Set --max-trigger-rate to adjust the cap (default 5%).

Typical usage
-------------
    PYTHONPATH=. .venv/bin/python scripts/sweep/bayesopt_a2118_trigger.py \\
        --panel results/ncf_00631l_panel_2025_v3_mdd.csv

    # More iterations, 3-D search including h5 re-entry:
    PYTHONPATH=. .venv/bin/python scripts/sweep/bayesopt_a2118_trigger.py \\
        --panel results/ncf_00631l_panel_2025_v3_mdd.csv \\
        --init-points 10 --n-iter 30 --search-h5 \\
        --output results/bayesopt_a2118_trigger.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# ── A21.18 internals ──────────────────────────────────────────────────────────
from group_a_plus.runners.a2118 import (
    NCF_LB_REGIME,
    NCF_LB_SOFT_REGIME,
    _apply_late_bull_overlay,
    _late_bull_hedge_weights,
    _load_ncf_panel,
)

# ── Backtest helpers (shared across runners) ──────────────────────────────────
from backtest_group_a_plus_defensive_basket import (
    DEFENSIVE_BASKETS,
    _load_total_return_prices,
    _recovery_ramp_regime,
    _simulate_costed_curve,
)
from backtest_group_a_plus_policy_signal import (
    DEFAULT_DECISION_POINTER,
    TICKERS,
    _load,
    _load_policy_signal,
    _normalize,
    _resolve,
    _weights_from_group_a,
    _weights_from_group_a_plus,
)
from backtest_group_a_plus_switch_policy import (
    DB_PATH,
    _load_chip_features,
    _load_prices,
    _metrics,
    _switch_returns,
)
from backtest_group_a_plus_warmup_consistency import _trim_window, _warmup_start
from group_a_plus.runners.a2111 import _build_switch_rule, _resolve_golden_signal_path

# ── Bayesian Optimisation ─────────────────────────────────────────────────────
try:
    from bayes_opt import BayesianOptimization
except ImportError:
    print("ERROR: bayesian-optimization not installed.  Run:")
    print("  .venv/bin/pip install bayesian-optimization")
    sys.exit(1)


# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_START = "2025-01-02"
DEFAULT_END = "2026-06-25"
WARMUP_DAYS = 180
COMMISSION_RATE = 0.001425
SLIPPAGE_RATE = 0.0005
EQUITY_SELL_TAX = 0.001
INITIAL_VALUE = 1_000_000.0

# Parameter bounds
PBOUNDS_2D = {
    "h20_max": (0.25, 0.48),
    "conf_min": (0.45, 0.68),
}
PBOUNDS_3D = {
    "h20_max": (0.25, 0.48),
    "conf_min": (0.45, 0.68),
    "h5_reentry_min": (0.0, 0.70),
}

# Known good seed points (from prior grid experiments / a2118 defaults)
SEED_PROBES = [
    {"h20_max": 0.45, "conf_min": 0.55, "h5_reentry_min": 0.0},   # a2118 default
    {"h20_max": 0.33, "conf_min": 0.55, "h5_reentry_min": 0.0},   # live trigger
    {"h20_max": 0.35, "conf_min": 0.50, "h5_reentry_min": 0.0},   # looser conf
    {"h20_max": 0.30, "conf_min": 0.60, "h5_reentry_min": 0.0},   # tighter both
    {"h20_max": 0.38, "conf_min": 0.55, "h5_reentry_min": 0.50},  # h5 hold-through
]


def _load_static_data(
    start: str,
    end: str,
    db: Path,
) -> dict:
    """Load all price/chip/policy data once before the optimisation loop."""
    policy_signal, _ = _load_policy_signal(_resolve(DEFAULT_DECISION_POINTER))
    golden_signal_path = _resolve_golden_signal_path()
    golden_signal = _load(golden_signal_path)
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
    basket = _normalize(DEFENSIVE_BASKETS["bond30_cash30"])
    golden_weights = _normalize(_weights_from_group_a(golden_signal))

    load_start = _warmup_start(start, WARMUP_DAYS)
    switch_rule = _build_switch_rule()
    full_prices = _load_prices(_resolve(db), list(TICKERS), load_start, end)
    full_chip = _load_chip_features(_resolve(db), full_prices.index, load_start, end)
    full_events, full_frame = _switch_returns(full_prices, full_chip, switch_rule)
    close_prices, frame, _ = _trim_window(full_prices, full_frame, full_events, start, end)
    total_return_prices, _ = _load_total_return_prices(_resolve(db), close_prices.index)

    execution_regime = _recovery_ramp_regime(frame["regime"], frame)
    ma_gap_series = frame["ma_gap"].reindex(execution_regime.index).fillna(0.0)

    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": basket,
        "group_a_plus_recovery": current_defensive,
        NCF_LB_REGIME: _late_bull_hedge_weights(golden_weights),
        NCF_LB_SOFT_REGIME: _late_bull_hedge_weights(golden_weights, intensity=0.5),
    }

    return {
        "total_return_prices": total_return_prices,
        "execution_regime": execution_regime,
        "ma_gap_series": ma_gap_series,
        "weights_by_regime": weights_by_regime,
        "n_days": len(execution_regime),
    }


def _objective_factory(
    static: dict,
    panel: pd.DataFrame,
    max_trigger_rate: float,
    trigger_penalty: float,
    search_h5: bool,
    all_results: list[dict],
) -> Any:
    """Return objective function closure for BayesianOptimization.

    The function signature must match the pbounds keys exactly.
    """
    tr_prices = static["total_return_prices"]
    base_regime = static["execution_regime"]
    ma_gap = static["ma_gap_series"]
    weights = static["weights_by_regime"]
    n_days = static["n_days"]

    def _objective(h20_max: float, conf_min: float, h5_reentry_min: float = 0.0) -> float:
        modified, info = _apply_late_bull_overlay(
            base_regime,
            panel,
            ma_gap,
            ma_gap_min=0.10,
            h20_max=h20_max,
            conf_min=conf_min,
            h5_reentry_min=h5_reentry_min if search_h5 else 0.0,
        )
        curve, _ = _simulate_costed_curve(
            tr_prices,
            modified,
            weights,
            INITIAL_VALUE,
            COMMISSION_RATE,
            SLIPPAGE_RATE,
            EQUITY_SELL_TAX,
        )
        m = _metrics(curve, INITIAL_VALUE)
        trigger_days = int(info.get("late_bull_trigger_days", 0))
        trigger_rate = trigger_days / max(n_days, 1)

        # Penalty for over-triggering (excessive turnover / commission drag)
        excess = max(0.0, trigger_rate - max_trigger_rate)
        score = m["sharpe_ratio"] - trigger_penalty * excess

        row = {
            "h20_max": round(h20_max, 4),
            "conf_min": round(conf_min, 4),
            "h5_reentry_min": round(h5_reentry_min, 4),
            "sharpe": round(m["sharpe_ratio"], 4),
            "sortino": round(m["sortino_ratio"], 4),
            "annual_return": round(m["annual_return"], 4),
            "max_drawdown": round(m["max_drawdown"], 4),
            "trigger_days": trigger_days,
            "trigger_rate": round(trigger_rate, 4),
            "score": round(score, 4),
        }
        all_results.append(row)
        return score

    if search_h5:
        return _objective

    # 2-D wrapper: BayesOpt does not allow extra unused params in the signature
    def _objective_2d(h20_max: float, conf_min: float) -> float:
        return _objective(h20_max=h20_max, conf_min=conf_min, h5_reentry_min=0.0)

    return _objective_2d


def _print_table(results: list[dict], top_n: int = 10) -> None:
    ranked = sorted(results, key=lambda r: r["score"], reverse=True)[:top_n]
    print(f"\n{'='*90}")
    print(f"  A21.18 Bayesian Optimisation — Top {top_n} parameter sets")
    print(f"{'='*90}")
    hdr = f"  {'h20_max':>8} {'conf_min':>9} {'h5_re':>6} | {'Sharpe':>7} {'Sortino':>8} {'AnnRet':>7} {'MDD':>8} | {'TrigD':>5} {'TrigR':>6} | {'Score':>7}"
    print(hdr)
    print(f"  {'-'*88}")
    for r in ranked:
        print(
            f"  {r['h20_max']:>8.3f} {r['conf_min']:>9.3f} {r['h5_reentry_min']:>6.3f} | "
            f"{r['sharpe']:>7.4f} {r['sortino']:>8.4f} {r['annual_return']:>7.2%} {r['max_drawdown']:>8.2%} | "
            f"{r['trigger_days']:>5d} {r['trigger_rate']:>6.2%} | "
            f"{r['score']:>7.4f}"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", required=True,
                        help="NCF panel CSV for 00631L (must have prob_up_h20, confidence columns)")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--init-points", type=int, default=8,
                        help="Number of random exploration probes (default: 8)")
    parser.add_argument("--n-iter", type=int, default=20,
                        help="Number of Bayesian optimisation steps (default: 20)")
    parser.add_argument("--search-h5", action="store_true",
                        help="Include h5_reentry_min as 3rd dimension (default: 2-D only)")
    parser.add_argument("--max-trigger-rate", type=float, default=0.05,
                        help="Trigger rate penalty threshold (default: 5%%)")
    parser.add_argument("--trigger-penalty", type=float, default=1.0,
                        help="Penalty weight per excess trigger-rate point (default: 1.0)")
    parser.add_argument("--top-n", type=int, default=10,
                        help="Print top-N results (default: 10)")
    parser.add_argument("--output", default=None,
                        help="Save full results to JSON (optional)")
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()

    panel_path = Path(args.panel)
    if not panel_path.is_absolute():
        panel_path = ROOT / panel_path
    if not panel_path.exists():
        print(f"ERROR: panel file not found: {panel_path}")
        sys.exit(1)

    print(f"Loading NCF panel: {panel_path.name}  ({panel_path})")
    panel = _load_ncf_panel(panel_path)
    if panel is None:
        print("ERROR: failed to load panel CSV")
        sys.exit(1)
    print(f"  Panel rows: {len(panel)}  ({panel.index[0].date()} – {panel.index[-1].date()})")

    print(f"\nLoading backtest data ({args.start} → {args.end}) …")
    static = _load_static_data(args.start, args.end, Path(args.db))
    print(f"  Execution regime days: {static['n_days']}")

    all_results: list[dict] = []
    pbounds = PBOUNDS_3D if args.search_h5 else PBOUNDS_2D
    objective = _objective_factory(
        static, panel,
        max_trigger_rate=args.max_trigger_rate,
        trigger_penalty=args.trigger_penalty,
        search_h5=args.search_h5,
        all_results=all_results,
    )

    optimizer = BayesianOptimization(
        f=objective,
        pbounds=pbounds,
        random_state=args.random_state,
        verbose=0,
    )

    # Register seed probes (known good starting points)
    seeds = [
        {k: v for k, v in p.items() if k in pbounds}
        for p in SEED_PROBES
    ]
    for probe in seeds:
        try:
            optimizer.probe(params=probe, lazy=True)
        except Exception:
            pass

    dims = "3-D (h20_max × conf_min × h5_reentry_min)" if args.search_h5 else "2-D (h20_max × conf_min)"
    print(f"\nBayesian Optimisation: {dims}")
    print(f"  Seed probes : {len(seeds)}")
    print(f"  Random init : {args.init_points}")
    print(f"  BO steps    : {args.n_iter}")
    print(f"  Total evals : {len(seeds) + args.init_points + args.n_iter}")
    print(f"  Trigger cap : {args.max_trigger_rate:.0%}  (penalty λ={args.trigger_penalty})")
    print()

    optimizer.maximize(
        init_points=args.init_points,
        n_iter=args.n_iter,
    )

    best = optimizer.max
    print(f"\nBest params found:")
    for k, v in best["params"].items():
        print(f"  {k:20s} = {v:.4f}")
    print(f"  score (objective)    = {best['target']:.4f}")

    _print_table(all_results, top_n=args.top_n)

    if args.output:
        out_path = Path(args.output)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        ranked = sorted(all_results, key=lambda r: r["score"], reverse=True)
        payload = {
            "generated_at": datetime.now().isoformat(),
            "panel": str(panel_path),
            "start": args.start,
            "end": args.end,
            "search_dimensions": "3D" if args.search_h5 else "2D",
            "init_points": args.init_points,
            "n_iter": args.n_iter,
            "max_trigger_rate": args.max_trigger_rate,
            "trigger_penalty": args.trigger_penalty,
            "best_params": best["params"],
            "best_score": best["target"],
            "all_results": ranked,
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
