#!/usr/bin/env python3
"""Run the authors' 2608.07977 Trading_test notebooks as a reproducible script.

This uses the Zenodo/GitHub source tree and pre-trained model weights. It does
not retrain Deep-BSDE or DBDP2 models.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch


DEFAULT_SOURCE_ROOT = Path(
    "/tmp/Deep_BSDE_for_4-ETFs-v1.0.0/huangzhecheng1996-Deep_BSDE_for_4-ETFs-2d7906c"
)


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _metrics(values: np.ndarray, dates: pd.Index, ew_values: np.ndarray | None = None) -> dict[str, float]:
    nav = pd.Series(values, index=dates)
    start_val = float(nav.iloc[0])
    end_val = float(nav.iloc[-1])
    years = len(nav) / 252.0
    ann_ret = float(np.log(end_val / start_val) / years) if start_val > 0 and end_val > 0 else 0.0
    daily_log_ret = np.log(nav / nav.shift(1)).dropna()
    ann_vol = float(daily_log_ret.std() * np.sqrt(252.0)) if len(daily_log_ret) > 1 else 0.0
    downside_sq = np.minimum(0.0, daily_log_ret) ** 2
    downside_dev = float(np.sqrt(np.mean(downside_sq)) * np.sqrt(252.0)) if len(daily_log_ret) else 0.0
    running_max = nav.cummax()
    drawdown = (nav - running_max) / running_max
    max_dd = float(drawdown.min())
    current_dd_duration = 0
    max_dd_duration = 0
    for underwater in nav < running_max:
        if underwater:
            current_dd_duration += 1
        else:
            max_dd_duration = max(max_dd_duration, current_dd_duration)
            current_dd_duration = 0
    max_dd_duration = max(max_dd_duration, current_dd_duration)
    mes_val = 0.0
    if ew_values is not None:
        ew_nav = pd.Series(ew_values, index=dates)
        ew_ret = np.log(ew_nav / ew_nav.shift(1)).dropna()
        threshold = np.percentile(ew_ret, 5) if len(ew_ret) else None
        if threshold is not None and len(ew_ret) == len(daily_log_ret):
            mes_val = float(daily_log_ret[ew_ret <= threshold].mean())
    return {
        "initial_value": start_val,
        "final_value": end_val,
        "annual_return": ann_ret,
        "volatility": ann_vol,
        "sharpe_ratio": ann_ret / ann_vol if ann_vol > 1e-6 else 0.0,
        "sortino_ratio": ann_ret / downside_dev if downside_dev > 1e-6 else 0.0,
        "calmar_ratio": ann_ret / abs(max_dd) if abs(max_dd) > 1e-9 else 0.0,
        "max_drawdown": max_dd,
        "recovery_time": int(max_dd_duration),
        "mes_5pct": mes_val,
    }


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


def run_deepbsde(
    source_root: Path,
    *,
    device: str,
    model_path: Path | None,
    start_date: str,
    end_date: str,
    rf: float,
    target_return: float,
    rebalance_period: int,
    strategy_window: int,
    allow_leverage: bool,
) -> dict[str, Any]:
    trading_dir = source_root / "Trading_test"
    for path in [source_root, trading_dir]:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    from LambdaNetwork import LambdaNetwork  # type: ignore
    from DeepLnSRESolver import DeepLnSRESolver  # type: ignore
    from lnSRE_Equation import lnSRE_Equation  # type: ignore
    from DeepBSDEBacktestEngine_lnSRE import BacktestEngine  # type: ignore
    from DeepBSDE_Strategy_LogSpace import DeepBSDE_Strategy_LogSpace  # type: ignore

    dt = 1 / 252
    horizon = 1.0
    lambda_net = LambdaNetwork(num_steps=int(horizon / dt), state_dim=5, lambda_dim=14, hidden_layers=[20, 20]).to(
        torch.float64
    )
    dummy_eq = lnSRE_Equation({"r": rf}, device=device)
    solver = DeepLnSRESolver({"r": rf}, lambda_net, dummy_eq, device=device)
    checkpoint_path = model_path or trading_dir / "sre_deepbsde_model_step5.pt"
    params = solver.load_model(str(checkpoint_path))
    strategy = DeepBSDE_Strategy_LogSpace(
        initial_check_p0=solver.P0.item(),
        q0=np.exp(-rf * horizon),
        model_params=params,
        r_f=rf,
        dt=dt,
        T_horizon=horizon,
        lambda_net=solver.lambda_net,
        sre_eq=lnSRE_Equation(params, device=device),
        device=device,
    )
    engine = BacktestEngine(assets=["xa", "xb", "xc", "xd"])
    engine.load_data(str(trading_dir / "SP500_ETFs_data.csv"))
    results = engine.run_backtest(
        strategy=strategy,
        start_date=start_date,
        end_date=end_date,
        target_return=target_return,
        initial_capital=100.0,
        rebalance_period=rebalance_period,
        strategy_window=strategy_window,
        allow_leverage=allow_leverage,
    )
    return {"method": "DeepBSDE", "metrics": _strategy_metrics(results)}


def run_dbdp2(
    source_root: Path,
    *,
    device: str,
    model_path: Path | None,
    start_date: str,
    end_date: str,
    rf: float,
    target_return: float,
    rebalance_period: int,
    strategy_window: int,
    allow_leverage: bool,
) -> dict[str, Any]:
    trading_dir = source_root / "Trading_test"
    dbdp_dir = source_root / "DBDP2"
    for path in [source_root, trading_dir, dbdp_dir]:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    from lnSRE_Equation import lnSRE_Equation  # type: ignore
    from DeepBSDEBacktestEngine_lnSRE import BacktestEngine  # type: ignore
    from DBDP_Strategy_LogSpace import DBDP_Strategy_LogSpace  # type: ignore

    value_module = _load_module("paper_2608_07977_value_network", dbdp_dir / "ValueNetwork.py")
    solver_module = _load_module("paper_2608_07977_dbdp_solver", dbdp_dir / "DBDPLnSRESolver.py")
    ValueNetwork = value_module.ValueNetwork
    DBDPLnSRESolver = solver_module.DBDPLnSRESolver

    dt = 1 / 252
    horizon = 1.0
    value_net = ValueNetwork(num_steps=int(horizon / dt), state_dim=5, hidden_layers=[64, 64]).to(torch.float64)
    dummy_params = {
        "r": rf,
        "sigma_a": 0.0,
        "sigma_b": 0.0,
        "sigma_c": 0.0,
        "sigma_d": 0.0,
        "sigma_M": 0.0,
    }
    solver = DBDPLnSRESolver(dummy_params, value_net, lnSRE_Equation(dummy_params, device=device), device=device)
    checkpoint_path = model_path or trading_dir / "value_net_final_complete_set2.pt"
    params = solver.load_model(str(checkpoint_path))
    strategy = DBDP_Strategy_LogSpace(
        initial_check_p0=solver.P0.item(),
        q0=np.exp(-rf * horizon),
        model_params=params,
        r_f=rf,
        dt=dt,
        T_horizon=horizon,
        value_net=solver.value_net,
        sre_eq=lnSRE_Equation(params, device=device),
        device=device,
    )
    engine = BacktestEngine(assets=["xa", "xb", "xc", "xd"])
    engine.load_data(str(trading_dir / "SP500_ETFs_data.csv"))
    results = engine.run_backtest(
        strategy=strategy,
        start_date=start_date,
        end_date=end_date,
        target_return=target_return,
        initial_capital=100.0,
        rebalance_period=rebalance_period,
        strategy_window=strategy_window,
        include_individual=False,
        allow_leverage=allow_leverage,
    )
    return {"method": "DBDP2", "metrics": _strategy_metrics(results)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--start-date", default="2020-01-01")
    parser.add_argument("--end-date", default="2020-12-31")
    parser.add_argument("--methods", default="deepbsde,dbdp2")
    parser.add_argument("--deepbsde-model-path", type=Path)
    parser.add_argument("--dbdp2-model-path", type=Path)
    parser.add_argument("--rf", type=float, default=0.02)
    parser.add_argument("--target-return", type=float, default=0.06)
    parser.add_argument("--rebalance-period", type=int, default=5)
    parser.add_argument("--strategy-window", type=int, default=20)
    parser.add_argument("--allow-leverage", action="store_true")
    parser.add_argument("--output", default="results/2608_07977_author_trading_test_2020.json")
    parser.add_argument("--csv-output", default="results/2608_07977_author_trading_test_2020.csv")
    args = parser.parse_args()

    if not args.source_root.exists():
        raise FileNotFoundError(f"source root not found: {args.source_root}")
    methods = [item.strip().lower() for item in args.methods.split(",") if item.strip()]
    runs = []
    if "deepbsde" in methods:
        runs.append(
            run_deepbsde(
                args.source_root,
                device=args.device,
                model_path=args.deepbsde_model_path,
                start_date=args.start_date,
                end_date=args.end_date,
                rf=args.rf,
                target_return=args.target_return,
                rebalance_period=args.rebalance_period,
                strategy_window=args.strategy_window,
                allow_leverage=args.allow_leverage,
            )
        )
    if "dbdp2" in methods:
        runs.append(
            run_dbdp2(
                args.source_root,
                device=args.device,
                model_path=args.dbdp2_model_path,
                start_date=args.start_date,
                end_date=args.end_date,
                rf=args.rf,
                target_return=args.target_return,
                rebalance_period=args.rebalance_period,
                strategy_window=args.strategy_window,
                allow_leverage=args.allow_leverage,
            )
        )

    report = {
        "schema_version": 1,
        "report_type": "paper_2608_07977_author_trading_test_reproduction",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_root": str(args.source_root),
        "source_paper": "arXiv:2608.07977",
        "target_return": args.target_return,
        "initial_capital": 100.0,
        "rf": args.rf,
        "rebalance_period": args.rebalance_period,
        "strategy_window": args.strategy_window,
        "allow_leverage": args.allow_leverage,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "device": args.device,
        "deepbsde_model_path": str(args.deepbsde_model_path) if args.deepbsde_model_path else None,
        "dbdp2_model_path": str(args.dbdp2_model_path) if args.dbdp2_model_path else None,
        "runs": runs,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows = []
    for run in runs:
        for strategy, metrics in run["metrics"].items():
            rows.append({"method": run["method"], "strategy": strategy, **metrics})
    csv_output = Path(args.csv_output)
    pd.DataFrame(rows).to_csv(csv_output, index=False, encoding="utf-8-sig")

    print(f"Output: {output.resolve()}")
    print(f"CSV: {csv_output.resolve()}")
    for row in rows:
        print(
            f"{row['method']} {row['strategy']}: return={row['annual_return']:.2%} "
            f"vol={row['volatility']:.2%} sharpe={row['sharpe_ratio']:.2f} "
            f"mdd={row['max_drawdown']:.2%} mes={row['mes_5pct']:.2%}"
        )


if __name__ == "__main__":
    main()
