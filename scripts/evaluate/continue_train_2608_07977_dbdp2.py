#!/usr/bin/env python3
"""Tiny continuation runner for the 2608.07977 DBDP2 checkpoint."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

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


def _jsonify(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    if hasattr(value, "item"):
        return value.item()
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_SOURCE_ROOT / "Trading_test" / "value_net_final_complete_set2.pt",
    )
    parser.add_argument("--epochs-per-step", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--target-mse", type=float, default=0.0)
    parser.add_argument("--lr-start", type=float, default=1e-5)
    parser.add_argument("--lr-patience", type=int, default=20)
    parser.add_argument("--min-lr", type=float, default=5e-7)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output-model", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()

    if not args.source_root.exists():
        raise FileNotFoundError(f"source root not found: {args.source_root}")
    if not args.checkpoint.exists():
        raise FileNotFoundError(f"checkpoint not found: {args.checkpoint}")

    dbdp_dir = args.source_root / "DBDP2"
    for path in [args.source_root, dbdp_dir]:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    value_module = _load_module("paper_2608_07977_dbdp_value_network_cont", dbdp_dir / "ValueNetwork.py")
    solver_module = _load_module("paper_2608_07977_dbdp_solver_cont", dbdp_dir / "DBDPLnSRESolver.py")
    equation_module = _load_module("paper_2608_07977_dbdp_lnsre_equation_cont", args.source_root / "lnSRE_Equation.py")
    simulator_module = _load_module(
        "paper_2608_07977_dbdp_stochastic_vol_model_cont", args.source_root / "StochasticVolatilityModel.py"
    )

    ValueNetwork = value_module.ValueNetwork
    DBDPLnSRESolver = solver_module.DBDPLnSRESolver
    lnSRE_Equation = equation_module.lnSRE_Equation
    StochasticVolatilityModel = simulator_module.StochasticVolatilityModel

    dt = 1 / 252
    horizon = 1.0
    dummy_params = {
        "r": 0.02,
        "sigma_a": 0.0,
        "sigma_b": 0.0,
        "sigma_c": 0.0,
        "sigma_d": 0.0,
        "sigma_M": 0.0,
    }
    value_net = ValueNetwork(num_steps=int(horizon / dt), state_dim=5, hidden_layers=[64, 64]).to(torch.float64)
    solver = DBDPLnSRESolver(
        dummy_params,
        value_net,
        lnSRE_Equation(dummy_params, device=args.device),
        dt=dt,
        T=horizon,
        device=args.device,
    )
    params = solver.load_model(str(args.checkpoint))
    solver.params = params
    solver.sre_equation = lnSRE_Equation(params, device=args.device).to(args.device)
    solver.sigma_V_tensor = torch.tensor(
        [
            params.get("sigma_a"),
            params.get("sigma_b"),
            params.get("sigma_c"),
            params.get("sigma_d"),
            params.get("sigma_M"),
        ],
        dtype=torch.float64,
        device=args.device,
    )
    simulator = StochasticVolatilityModel(params)

    start_p0 = float(solver.P0.item())
    max_epochs_list = [args.epochs_per_step for _ in range(solver.N_steps)]
    args.output_model.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.parent.mkdir(parents=True, exist_ok=True)

    original_cwd = Path.cwd()
    os.chdir(args.output_model.parent)
    started = time.perf_counter()
    try:
        solver.train_backward(
            simulator=simulator,
            target_mse=args.target_mse,
            max_epochs_list=max_epochs_list,
            lr_start=args.lr_start,
            lr_patience=args.lr_patience,
            min_lr=args.min_lr,
            batch_size=args.batch_size,
            save_interval=solver.N_steps + 1,
            resume_ckpt_path=None,
            global_warm_start=True,
        )
    finally:
        os.chdir(original_cwd)
    elapsed_seconds = time.perf_counter() - started
    solver.save_model(file_path=str(args.output_model))

    report = {
        "schema_version": 1,
        "report_type": "paper_2608_07977_dbdp2_tiny_continuation_train",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_root": str(args.source_root),
        "checkpoint": str(args.checkpoint),
        "output_model": str(args.output_model),
        "device": args.device,
        "epochs_per_step": args.epochs_per_step,
        "total_time_steps": int(solver.N_steps),
        "batch_size": args.batch_size,
        "target_mse": args.target_mse,
        "lr_start": args.lr_start,
        "lr_patience": args.lr_patience,
        "min_lr": args.min_lr,
        "start_check_p0": start_p0,
        "end_check_p0": float(solver.P0.item()),
        "elapsed_seconds": elapsed_seconds,
        "step_loss_history": _jsonify(solver.step_loss_history),
    }
    args.report_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Output model: {args.output_model.resolve()}")
    print(f"Report: {args.report_output.resolve()}")
    print(f"P0: {start_p0:.6f} -> {solver.P0.item():.6f}")
    print(f"Elapsed seconds: {elapsed_seconds:.2f}")


if __name__ == "__main__":
    main()
