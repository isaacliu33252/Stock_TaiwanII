#!/usr/bin/env python3
"""Monte Carlo / bootstrap stress comparison for GroupA+ strategies."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backtest_group_a_plus_copula_tail import A207_RULE, MA20_RULE, _copula_selector_regime
from backtest_group_a_plus_policy_signal import (
    DEFAULT_DECISION_POINTER,
    DEFAULT_GOLDEN_SIGNAL,
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
    _simulate_regime_curve,
    _switch_returns,
)


PROJECT_ROOT = Path(__file__).resolve().parent


def _block_bootstrap_returns(
    returns: pd.DataFrame,
    simulations: int,
    horizon: int,
    block_size: int,
    seed: int,
) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    data = returns.to_numpy(dtype=float)
    n_rows, n_cols = data.shape
    max_start = max(n_rows - block_size, 0)
    out = {name: np.empty(simulations, dtype=float) for name in returns.columns}
    out_mdd = {f"{name}__mdd": np.empty(simulations, dtype=float) for name in returns.columns}
    for sim in range(simulations):
        chunks = []
        while sum(len(chunk) for chunk in chunks) < horizon:
            start = int(rng.integers(0, max_start + 1)) if max_start > 0 else 0
            chunks.append(data[start : start + block_size])
        path = np.vstack(chunks)[:horizon]
        wealth = np.cumprod(1.0 + path, axis=0)
        peaks = np.maximum.accumulate(wealth, axis=0)
        drawdowns = wealth / np.maximum(peaks, 1e-12) - 1.0
        final_returns = wealth[-1, :] - 1.0
        max_drawdowns = drawdowns.min(axis=0)
        for col_idx, name in enumerate(returns.columns):
            out[name][sim] = float(final_returns[col_idx])
            out_mdd[f"{name}__mdd"][sim] = float(max_drawdowns[col_idx])
    out.update(out_mdd)
    return out


def _summarize_sim(values: np.ndarray) -> dict[str, float]:
    return {
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "p05": float(np.quantile(values, 0.05)),
        "p10": float(np.quantile(values, 0.10)),
        "p25": float(np.quantile(values, 0.25)),
        "p75": float(np.quantile(values, 0.75)),
        "p90": float(np.quantile(values, 0.90)),
        "p95": float(np.quantile(values, 0.95)),
        "prob_negative": float(np.mean(values < 0.0)),
    }


def _pairwise_win_rates(final_returns: dict[str, np.ndarray], names: list[str]) -> dict[str, float]:
    rates: dict[str, float] = {}
    for left in names:
        for right in names:
            if left == right:
                continue
            rates[f"{left}_gt_{right}"] = float(np.mean(final_returns[left] > final_returns[right]))
    return rates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--simulations", type=int, default=5000)
    parser.add_argument("--horizon", type=int, default=252)
    parser.add_argument("--block-size", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260619)
    parser.add_argument("--output-prefix", default="results/group_a_plus_monte_carlo_stress_20260619")
    args = parser.parse_args()

    policy_signal, policy_signal_path = _load_policy_signal(_resolve(args.decision_pointer))
    golden_signal_path = _resolve(args.golden_signal)
    golden_signal = _load(golden_signal_path)
    defensive_weights = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)
    prices = _load_prices(_resolve(args.db), list(TICKERS), args.start, args.end)
    chip_features = _load_chip_features(_resolve(args.db), prices.index, args.start, args.end)
    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": defensive_weights,
    }

    a207_events, a207_frame = _switch_returns(prices, chip_features, A207_RULE)
    ma20_events, ma20_frame = _switch_returns(prices, chip_features, MA20_RULE)
    copula_frame = _copula_selector_regime(
        prices,
        a207_frame["regime"],
        ma20_frame["regime"],
        window=60,
        tail_q=0.05,
        min_score=3,
        require_negative_5d=True,
    )
    regimes = {
        "golden1": pd.Series("golden1", index=prices.index),
        "group_a_plus_defensive": pd.Series("group_a_plus_defensive", index=prices.index),
        "a207": a207_frame["regime"],
        "ma20": ma20_frame["regime"],
        "copula_w60_q05_s3_neg5d": copula_frame["regime"],
    }
    curves = pd.DataFrame(index=prices.index)
    for name, regime in regimes.items():
        curves[name] = _simulate_regime_curve(prices, regime, weights_by_regime, args.initial_value)
    returns = curves.pct_change().dropna()

    simulated = _block_bootstrap_returns(
        returns,
        simulations=args.simulations,
        horizon=args.horizon,
        block_size=args.block_size,
        seed=args.seed,
    )
    strategy_names = list(returns.columns)
    final_returns = {name: simulated[name] for name in strategy_names}
    mdds = {name: simulated[f"{name}__mdd"] for name in strategy_names}
    mc_summary = {
        name: {
            "final_return": _summarize_sim(final_returns[name]),
            "max_drawdown": _summarize_sim(mdds[name]),
        }
        for name in strategy_names
    }
    report = {
        "experiment": "group_a_plus_monte_carlo_block_bootstrap",
        "method_note": (
            "Block bootstrap samples synchronized daily strategy returns to preserve cross-strategy comparison "
            "and some short-horizon volatility clustering. This does not forecast returns; it stress-tests path sensitivity."
        ),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requested_window": {"start": args.start, "end": args.end},
        "actual_window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": int(len(prices))},
        "parameters": {
            "simulations": int(args.simulations),
            "horizon": int(args.horizon),
            "block_size": int(args.block_size),
            "seed": int(args.seed),
        },
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
        },
        "weights": {
            "golden1_0531_1m": _normalize(golden_weights),
            "group_a_plus_defensive_1m": _normalize(defensive_weights),
        },
        "historical_metrics": {name: _metrics(curves[name], args.initial_value) for name in curves.columns},
        "events": {"a207": a207_events, "ma20": ma20_events},
        "monte_carlo_summary": mc_summary,
        "win_rates": _pairwise_win_rates(final_returns, strategy_names),
    }

    prefix = Path(args.output_prefix)
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    curve_path = prefix.with_name(prefix.name + "_historical_curve.csv")
    sim_path = prefix.with_name(prefix.name + "_simulated_final_returns.csv")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = []
    for name in strategy_names:
        rows.append(
            {
                "strategy": name,
                **{f"final_return_{k}": v for k, v in mc_summary[name]["final_return"].items()},
                **{f"mdd_{k}": v for k, v in mc_summary[name]["max_drawdown"].items()},
                **{f"hist_{k}": v for k, v in report["historical_metrics"][name].items() if isinstance(v, (int, float))},
            }
        )
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    curves.to_csv(curve_path, encoding="utf-8-sig")
    pd.DataFrame(final_returns).to_csv(sim_path, index=False, encoding="utf-8-sig")

    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print(f"Curve CSV: {curve_path}")
    print(f"Sim returns CSV: {sim_path}")
    print(f"Window: {report['actual_window']['start']} ~ {report['actual_window']['end']} ({report['actual_window']['rows']} rows)")
    for name in strategy_names:
        fs = mc_summary[name]["final_return"]
        ds = mc_summary[name]["max_drawdown"]
        print(
            f"{name}: hist_final={report['historical_metrics'][name]['final_value']:,.0f}, "
            f"mc_median={fs['median']:.2%}, mc_p05={fs['p05']:.2%}, "
            f"mc_mdd_p05={ds['p05']:.2%}, prob_negative={fs['prob_negative']:.2%}"
        )
    print(f"A20.7 win vs golden1: {report['win_rates']['a207_gt_golden1']:.2%}")
    print(f"A20.7 win vs copula:  {report['win_rates']['a207_gt_copula_w60_q05_s3_neg5d']:.2%}")


if __name__ == "__main__":
    main()
