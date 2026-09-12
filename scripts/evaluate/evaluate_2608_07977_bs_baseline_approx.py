#!/usr/bin/env python3
"""Approximate Black-Scholes mean-variance baseline for 2608.07977 trading data.

The paper reports a Black-Scholes baseline but the released Zenodo bundle does
not include its implementation. This script uses a transparent approximation:
rolling constant drift/covariance estimates and a closed-form tangency
direction scaled to the requested annual target return.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reproduce_2608_07977_author_trading_test import DEFAULT_SOURCE_ROOT, _metrics


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class BSApproxStrategy:
    def __init__(
        self,
        assets: list[str],
        *,
        r_f: float,
        dt: float,
        T: float,
        estimation_window: int,
        ridge: float,
        mode: str,
    ):
        self.assets = assets
        self.r_f = float(r_f)
        self.dt = float(dt)
        self.T = float(T)
        self.estimation_window = int(estimation_window)
        self.ridge = float(ridge)
        self.mode = mode

    def calculate_weights(
        self,
        snapshot,
        target_return: float,
        initial_capital: float,
        allow_leverage: bool,
        time_remain: float,
    ) -> dict[str, float]:
        history = snapshot.history_window[self.assets].tail(self.estimation_window)
        mu = history.mean().values.astype(np.float64) * 252.0
        cov = history.cov().values.astype(np.float64) * 252.0
        cov = cov + np.eye(len(self.assets)) * self.ridge
        excess_mu = mu - self.r_f
        try:
            direction = np.linalg.solve(cov, excess_mu)
        except np.linalg.LinAlgError:
            direction = np.linalg.pinv(cov) @ excess_mu
        theta_sq = float(excess_mu @ direction)
        if abs(theta_sq) < 1e-12 or not np.isfinite(theta_sq):
            weights = np.repeat(1.0 / len(self.assets), len(self.assets))
        elif self.mode == "scaled_target":
            scale = (float(target_return) - self.r_f) / theta_sq
            weights = scale * direction
        elif self.mode == "feedback":
            p0 = float(np.exp(-(2.0 * self.r_f - theta_sq) * self.T))
            h0 = float(np.exp(-self.r_f * self.T))
            x0 = float(initial_capital)
            d_tgt = x0 * float(np.exp(target_return * self.T))
            denom = 1.0 - p0 * (h0**2)
            c_star = (p0 * h0 * x0 - d_tgt) / denom if abs(denom) > 1e-9 else 0.0
            q_t = float(np.exp(-self.r_f * max(time_remain, 0.0)))
            feedback = (snapshot.total_equity + c_star * q_t) / max(snapshot.total_equity, 1e-9)
            weights = -direction * feedback
        else:
            raise ValueError(f"unsupported mode: {self.mode}")
        weights = np.nan_to_num(weights, nan=0.0, posinf=0.0, neginf=0.0)
        if not allow_leverage:
            gross = float(np.sum(np.abs(weights)))
            if gross > 1.0:
                weights = weights / gross
        return dict(zip(self.assets, weights))


def _strategy_metrics(results: dict[str, Any]) -> dict[str, Any]:
    dates = pd.DatetimeIndex(results["dates"])
    ew_values = results.get("EW")
    out: dict[str, Any] = {}
    for name, values in results.items():
        if name in {"dates", "w_affine_dict"} or name.startswith("w_"):
            continue
        if not isinstance(values, np.ndarray) or values.ndim != 1:
            continue
        out[name] = _metrics(values, dates, ew_values=ew_values)
    return out


def _weight_summary(results: dict[str, Any], key: str) -> dict[str, float]:
    weights = np.asarray(results.get("w_affine_dict", {}).get(key, []), dtype=np.float64)
    if weights.size == 0:
        return {
            "weight_gross_mean": 0.0,
            "weight_gross_max": 0.0,
            "weight_net_mean": 0.0,
            "cash_weight_mean": 1.0,
            "cash_weight_min": 1.0,
        }
    gross = np.sum(np.abs(weights), axis=1)
    net = np.sum(weights, axis=1)
    cash = 1.0 - net
    return {
        "weight_gross_mean": float(np.mean(gross)),
        "weight_gross_max": float(np.max(gross)),
        "weight_net_mean": float(np.mean(net)),
        "cash_weight_mean": float(np.mean(cash)),
        "cash_weight_min": float(np.min(cash)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--windows", default="2020-01-01:2020-12-31,2025-01-01:2025-12-31")
    parser.add_argument("--rf-values", default="0.02,0.04")
    parser.add_argument("--target-return", type=float, default=0.06)
    parser.add_argument("--estimation-windows", default="20,60,252")
    parser.add_argument("--rebalance-period", type=int, default=5)
    parser.add_argument("--allow-leverage", action="store_true")
    parser.add_argument("--ridge", type=float, default=1e-8)
    parser.add_argument("--mode", choices=["scaled_target", "feedback"], default="scaled_target")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    args = parser.parse_args()

    trading_dir = args.source_root / "Trading_test"
    for path in [args.source_root, trading_dir]:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    BacktestEngine = _load_module(
        "paper_2608_07977_bs_backtest_engine", trading_dir / "DeepBSDEBacktestEngine_lnSRE.py"
    ).BacktestEngine

    windows = [tuple(item.split(":", 1)) for item in args.windows.split(",") if item.strip()]
    rf_values = [float(item) for item in args.rf_values.split(",") if item.strip()]
    estimation_windows = [int(item) for item in args.estimation_windows.split(",") if item.strip()]
    rows: list[dict[str, Any]] = []
    assets = ["xa", "xb", "xc", "xd"]
    for start_date, end_date in windows:
        for rf in rf_values:
            for estimation_window in estimation_windows:
                strategy = BSApproxStrategy(
                    assets,
                    r_f=rf,
                    dt=1 / 252,
                    T=1.0,
                    estimation_window=estimation_window,
                    ridge=args.ridge,
                    mode=args.mode,
                )
                engine = BacktestEngine(assets=assets)
                engine.load_data(str(trading_dir / "SP500_ETFs_data.csv"))
                results = engine.run_backtest(
                    strategy=strategy,
                    start_date=start_date,
                    end_date=end_date,
                    target_return=args.target_return,
                    initial_capital=100.0,
                    rebalance_period=args.rebalance_period,
                    strategy_window=estimation_window,
                    allow_leverage=args.allow_leverage,
                )
                metrics = _strategy_metrics(results)
                bs_key = f"Affine_{args.target_return:.1%}"
                weight_summary = _weight_summary(results, bs_key)
                row = {
                    "window": start_date[:4],
                    "start_date": start_date,
                    "end_date": end_date,
                    "method": "BSApprox",
                    "rf": rf,
                    "target_return": args.target_return,
                    "estimation_window": estimation_window,
                    "allow_leverage": args.allow_leverage,
                    **metrics[bs_key],
                    **weight_summary,
                }
                rows.append(row)

    definitions = {
        "scaled_target": "rolling constant drift/covariance tangency portfolio scaled to target return",
        "feedback": "rolling constant drift/covariance Black-Scholes mean-variance feedback-control approximation",
    }
    report = {
        "schema_version": 1,
        "report_type": "paper_2608_07977_black_scholes_baseline_approximation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_root": str(args.source_root),
        "definition": definitions[args.mode],
        "mode": args.mode,
        "target_return": args.target_return,
        "rebalance_period": args.rebalance_period,
        "allow_leverage": args.allow_leverage,
        "ridge": args.ridge,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.csv_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(args.csv_output, index=False, encoding="utf-8-sig")
    print(f"Output: {args.output.resolve()}")
    print(f"CSV: {args.csv_output.resolve()}")
    for row in rows:
        print(
            f"{row['window']} rf={row['rf']:.2%} est_win={row['estimation_window']} "
            f"lev={row['allow_leverage']}: ret={row['annual_return']:.2%} "
            f"vol={row['volatility']:.2%} sharpe={row['sharpe_ratio']:.2f} "
            f"mdd={row['max_drawdown']:.2%} mes={row['mes_5pct']:.2%}"
        )


if __name__ == "__main__":
    main()
