#!/usr/bin/env python3
"""Continue-training smoke runner for the 2608.07977 DeepBSDE checkpoint."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

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


def _last_history_row(csv_path: Path) -> dict[str, Any]:
    if not csv_path.exists():
        return {}
    df = pd.read_csv(csv_path)
    if df.empty:
        return {}
    return df.iloc[-1].to_dict()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_SOURCE_ROOT / "Trading_test" / "sre_deepbsde_model_step5.pt",
    )
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr-lambda", type=float, default=1e-4)
    parser.add_argument("--lr-p0", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--freeze-p0", action="store_true")
    parser.add_argument("--freeze-lambda", action="store_true")
    parser.add_argument("--reuse-optim-state", action="store_true")
    parser.add_argument("--output-model", type=Path, required=True)
    parser.add_argument("--history-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()

    if not args.source_root.exists():
        raise FileNotFoundError(f"source root not found: {args.source_root}")
    if not args.checkpoint.exists():
        raise FileNotFoundError(f"checkpoint not found: {args.checkpoint}")

    if str(args.source_root) not in sys.path:
        sys.path.insert(0, str(args.source_root))

    lambda_module = _load_module("paper_2608_07977_lambda_network", args.source_root / "LambdaNetwork.py")
    solver_module = _load_module("paper_2608_07977_deep_solver", args.source_root / "DeepLnSRESolver.py")
    equation_module = _load_module("paper_2608_07977_lnsre_equation", args.source_root / "lnSRE_Equation.py")
    simulator_module = _load_module(
        "paper_2608_07977_stochastic_vol_model", args.source_root / "StochasticVolatilityModel.py"
    )

    LambdaNetwork = lambda_module.LambdaNetwork
    DeepLnSRESolver = solver_module.DeepLnSRESolver
    lnSRE_Equation = equation_module.lnSRE_Equation
    StochasticVolatilityModel = simulator_module.StochasticVolatilityModel

    dt = 1 / 252
    horizon = 1.0
    lambda_net = LambdaNetwork(num_steps=int(horizon / dt), state_dim=5, lambda_dim=14, hidden_layers=[20, 20]).to(
        torch.float64
    )
    dummy_params = {"r": 0.02}
    solver = DeepLnSRESolver(
        dummy_params,
        lambda_net,
        lnSRE_Equation(dummy_params, device=args.device),
        dt=dt,
        T=horizon,
        device=args.device,
    )
    params = solver.load_model(str(args.checkpoint))
    if not params:
        raise ValueError(f"checkpoint did not contain env_params: {args.checkpoint}")
    solver.params = params
    solver.sre_equation = lnSRE_Equation(params, device=args.device).to(args.device)
    simulator = StochasticVolatilityModel(params)

    start_epoch = int(solver.current_epoch)
    start_p0 = float(solver.P0.item())
    started = time.perf_counter()
    solver.train_model(
        simulator=simulator,
        additional_epochs=args.epochs,
        lr_lambda=args.lr_lambda,
        lr_p0=args.lr_p0,
        batch_size=args.batch_size,
        freeze_p0=args.freeze_p0,
        freeze_lambda=args.freeze_lambda,
        reset_optim_state=not args.reuse_optim_state,
        patience=args.patience,
    )
    elapsed_seconds = time.perf_counter() - started

    args.output_model.parent.mkdir(parents=True, exist_ok=True)
    args.history_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    solver.save_model(file_path=str(args.output_model), csv_path=str(args.history_output))

    report = {
        "schema_version": 1,
        "report_type": "paper_2608_07977_deepbsde_continuation_train",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_root": str(args.source_root),
        "checkpoint": str(args.checkpoint),
        "output_model": str(args.output_model),
        "history_output": str(args.history_output),
        "device": args.device,
        "epochs_requested": args.epochs,
        "batch_size": args.batch_size,
        "lr_lambda": args.lr_lambda,
        "lr_p0": args.lr_p0,
        "patience": args.patience,
        "freeze_p0": args.freeze_p0,
        "freeze_lambda": args.freeze_lambda,
        "reuse_optim_state": args.reuse_optim_state,
        "start_epoch": start_epoch,
        "end_epoch": int(solver.current_epoch),
        "start_check_p0": start_p0,
        "end_check_p0": float(solver.P0.item()),
        "elapsed_seconds": elapsed_seconds,
        "last_history_row": _last_history_row(args.history_output),
    }
    args.report_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Output model: {args.output_model.resolve()}")
    print(f"History: {args.history_output.resolve()}")
    print(f"Report: {args.report_output.resolve()}")
    print(f"Epoch: {start_epoch} -> {solver.current_epoch}")
    print(f"Elapsed seconds: {elapsed_seconds:.2f}")


if __name__ == "__main__":
    main()
