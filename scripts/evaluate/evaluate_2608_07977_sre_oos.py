#!/usr/bin/env python3
"""Out-of-sample SRE verification for the 2608.07977 released checkpoints."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
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


def _terminal_stats(values: np.ndarray, target: float) -> dict[str, float]:
    return {
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "mse": float(np.mean((values - target) ** 2)),
        "max_abs_deviation": float(np.max(np.abs(values - target))),
        "pct_99": float(np.percentile(values, 99)),
        "pct_01": float(np.percentile(values, 1)),
    }


def _init_deepbsde(source_root: Path, checkpoint: Path, device: str):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    LambdaNetwork = _load_module("paper_2608_07977_oos_lambda", source_root / "LambdaNetwork.py").LambdaNetwork
    DeepLnSRESolver = _load_module("paper_2608_07977_oos_deep_solver", source_root / "DeepLnSRESolver.py").DeepLnSRESolver
    lnSRE_Equation = _load_module("paper_2608_07977_oos_lnsre", source_root / "lnSRE_Equation.py").lnSRE_Equation

    dt = 1 / 252
    horizon = 1.0
    lambda_net = LambdaNetwork(num_steps=int(horizon / dt), state_dim=5, lambda_dim=14, hidden_layers=[20, 20]).to(
        torch.float64
    )
    dummy_params = {"r": 0.02}
    solver = DeepLnSRESolver(dummy_params, lambda_net, lnSRE_Equation(dummy_params, device=device), device=device)
    params = solver.load_model(str(checkpoint))
    solver.params = params
    solver.sre_equation = lnSRE_Equation(params, device=device).to(device)
    solver.lambda_net.eval()
    return solver, params


def _init_dbdp2(source_root: Path, checkpoint: Path, device: str):
    dbdp_dir = source_root / "DBDP2"
    for path in [source_root, dbdp_dir]:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    ValueNetwork = _load_module("paper_2608_07977_oos_value", dbdp_dir / "ValueNetwork.py").ValueNetwork
    DBDPLnSRESolver = _load_module("paper_2608_07977_oos_dbdp_solver", dbdp_dir / "DBDPLnSRESolver.py").DBDPLnSRESolver
    lnSRE_Equation = _load_module("paper_2608_07977_oos_dbdp_lnsre", source_root / "lnSRE_Equation.py").lnSRE_Equation

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
    solver = DBDPLnSRESolver(dummy_params, value_net, lnSRE_Equation(dummy_params, device=device), device=device)
    params = solver.load_model(str(checkpoint))
    solver.params = params
    solver.sre_equation = lnSRE_Equation(params, device=device).to(device)
    solver.sigma_V_tensor = torch.tensor(
        [params.get("sigma_a"), params.get("sigma_b"), params.get("sigma_c"), params.get("sigma_d"), params.get("sigma_M")],
        dtype=torch.float64,
        device=device,
    )
    solver.value_net.eval()
    return solver, params


def _simulate(source_root: Path, params: dict[str, Any], solver, scenarios: int, seed: int):
    StochasticVolatilityModel = _load_module(
        "paper_2608_07977_oos_simulator", source_root / "StochasticVolatilityModel.py"
    ).StochasticVolatilityModel
    simulator = StochasticVolatilityModel(params)
    return simulator.simulate_tensors(
        num_days=solver.N_steps,
        dt=solver.dt,
        num_scenarios=scenarios,
        seed=seed,
    )


def _deepbsde_log_terminal(solver, V_test: torch.Tensor, dW_test: torch.Tensor) -> np.ndarray:
    batch_size = V_test.shape[0]
    check_p_t = torch.full((batch_size, 1), solver.P0.item(), dtype=torch.float64, device=solver.device)
    with torch.no_grad():
        check_lambda_t = solver.lambda_net(0, V_test[:, 0, :])
        for i in range(solver.N_steps):
            t_curr = (i * solver.dt) / solver.T
            drift = solver.sre_equation(t_curr, check_p_t, check_lambda_t, V_test[:, i, :])
            diffusion = torch.sum(check_lambda_t * dW_test[:, i, :], dim=1, keepdim=True)
            check_p_t = check_p_t + drift * solver.dt + diffusion
            if i + 1 < solver.N_steps:
                check_lambda_t = solver.lambda_net(i + 1, V_test[:, i + 1, :])
    return check_p_t.cpu().numpy().flatten()


def _dbdp2_log_terminal(solver, V_test: torch.Tensor, dW_test: torch.Tensor) -> np.ndarray:
    batch_size = V_test.shape[0]
    check_p_t = torch.full((batch_size, 1), solver.P0.item(), dtype=torch.float64, device=solver.device)
    check_lambda_t = solver.Lambda0.expand(batch_size, -1)
    for i in range(solver.N_steps):
        with torch.no_grad():
            t_curr = (i * solver.dt) / solver.T
            drift = solver.sre_equation(t_curr, check_p_t, check_lambda_t, V_test[:, i, :])
            diffusion = torch.sum(check_lambda_t * dW_test[:, i, :], dim=1, keepdim=True)
            check_p_t = check_p_t + drift * solver.dt + diffusion
        if i + 1 < solver.N_steps:
            V_next = V_test[:, i + 1, :].clone().detach().requires_grad_(True)
            check_p_next = solver.value_net(i + 1, V_next)
            grad_check_p = torch.autograd.grad(
                outputs=check_p_next,
                inputs=V_next,
                grad_outputs=torch.ones_like(check_p_next),
                create_graph=False,
                retain_graph=False,
                only_inputs=True,
            )[0]
            lambda_active = (grad_check_p * solver.sigma_V_tensor * torch.sqrt(torch.clamp(V_next, min=1e-8))).detach()
            pad_zeros = torch.zeros(batch_size, 9, dtype=torch.float64, device=solver.device)
            check_lambda_t = torch.cat([lambda_active, pad_zeros], dim=1)
    return check_p_t.detach().cpu().numpy().flatten()


def _deepbsde_physical_terminal(solver, V_test: torch.Tensor, dW_test: torch.Tensor) -> np.ndarray:
    batch_size = V_test.shape[0]
    p_t = torch.full((batch_size, 1), math.exp(solver.P0.item()), dtype=torch.float64, device=solver.device)
    V_tm = V_test.transpose(0, 1).contiguous()
    dW_tm = dW_test.transpose(0, 1).contiguous()
    with torch.no_grad():
        check_lambda_t = solver.lambda_net(0, V_tm[0])
        for i in range(solver.N_steps):
            lambda_t = p_t * check_lambda_t
            B_t, Sigma_t, sigma_t = solver.sre_equation._build_tensors(V_tm[i])
            inv_sigma_b = torch.linalg.solve(Sigma_t, B_t.unsqueeze(-1))
            rho_sq = torch.bmm(B_t.unsqueeze(-1).transpose(1, 2), inv_sigma_b).squeeze(-1).squeeze(-1)
            lambda_unsqueeze = lambda_t.unsqueeze(-1)
            proj_lambda = torch.bmm(sigma_t, lambda_unsqueeze)
            inv_sigma_proj = torch.linalg.solve(Sigma_t, proj_lambda)
            cross = 2.0 * torch.bmm(B_t.unsqueeze(-1).transpose(1, 2), inv_sigma_proj).squeeze(-1).squeeze(-1)
            pi_lambda = torch.bmm(sigma_t.transpose(1, 2), inv_sigma_proj)
            quad = torch.bmm(lambda_unsqueeze.transpose(1, 2), pi_lambda).squeeze(-1).squeeze(-1)
            inv_p_t = 1.0 / torch.clamp(p_t.squeeze(-1), min=1e-12)
            f_p_true = ((2.0 * solver.sre_equation.r - rho_sq) * p_t.squeeze(-1) - cross - inv_p_t * quad).unsqueeze(-1)
            diffusion = torch.sum(lambda_t * dW_tm[i], dim=1, keepdim=True)
            p_t = torch.clamp(p_t - f_p_true * solver.dt + diffusion, min=1e-8)
            if i + 1 < solver.N_steps:
                check_lambda_t = solver.lambda_net(i + 1, V_tm[i + 1])
    return p_t.cpu().numpy().flatten()


def _dbdp2_physical_terminal(solver, V_test: torch.Tensor, dW_test: torch.Tensor) -> np.ndarray:
    batch_size = V_test.shape[0]
    p_t = torch.full((batch_size, 1), math.exp(solver.P0.item()), dtype=torch.float64, device=solver.device)
    V_tm = V_test.transpose(0, 1).contiguous()
    dW_tm = dW_test.transpose(0, 1).contiguous()
    check_lambda_t = solver.Lambda0.expand(batch_size, 14)
    for i in range(solver.N_steps):
        with torch.no_grad():
            lambda_t = p_t * check_lambda_t
            B_t, Sigma_t, sigma_t = solver.sre_equation._build_tensors(V_tm[i])
            inv_sigma_b = torch.linalg.solve(Sigma_t, B_t.unsqueeze(-1))
            rho_sq = torch.bmm(B_t.unsqueeze(-1).transpose(1, 2), inv_sigma_b).squeeze(-1).squeeze(-1)
            lambda_unsqueeze = lambda_t.unsqueeze(-1)
            proj_lambda = torch.bmm(sigma_t, lambda_unsqueeze)
            inv_sigma_proj = torch.linalg.solve(Sigma_t, proj_lambda)
            cross = 2.0 * torch.bmm(B_t.unsqueeze(-1).transpose(1, 2), inv_sigma_proj).squeeze(-1).squeeze(-1)
            pi_lambda = torch.bmm(sigma_t.transpose(1, 2), inv_sigma_proj)
            quad = torch.bmm(lambda_unsqueeze.transpose(1, 2), pi_lambda).squeeze(-1).squeeze(-1)
            inv_p_t = 1.0 / torch.clamp(p_t.squeeze(-1), min=1e-12)
            f_p_true = ((2.0 * solver.sre_equation.r - rho_sq) * p_t.squeeze(-1) - cross - inv_p_t * quad).unsqueeze(-1)
            diffusion = torch.sum(lambda_t * dW_tm[i], dim=1, keepdim=True)
            p_t = torch.clamp(p_t - f_p_true * solver.dt + diffusion, min=1e-8)
        if i + 1 < solver.N_steps:
            V_next = V_tm[i + 1].clone().detach().requires_grad_(True)
            check_p_next = solver.value_net(i + 1, V_next)
            grad_check_p = torch.autograd.grad(
                outputs=check_p_next,
                inputs=V_next,
                grad_outputs=torch.ones_like(check_p_next),
                create_graph=False,
                retain_graph=False,
                only_inputs=True,
            )[0]
            lambda_active = grad_check_p * solver.sigma_V_tensor * torch.sqrt(torch.clamp(V_next, min=1e-8))
            pad_zeros = torch.zeros(batch_size, 9, dtype=torch.float64, device=solver.device)
            check_lambda_t = torch.cat([lambda_active, pad_zeros], dim=1).detach()
    return p_t.detach().cpu().numpy().flatten()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--deepbsde-checkpoint", type=Path, default=DEFAULT_SOURCE_ROOT / "Trading_test" / "sre_deepbsde_model_step5.pt")
    parser.add_argument("--dbdp2-checkpoint", type=Path, default=DEFAULT_SOURCE_ROOT / "Trading_test" / "value_net_final_complete_set2.pt")
    parser.add_argument("--methods", default="deepbsde,dbdp2")
    parser.add_argument("--scenarios", type=int, default=10000)
    parser.add_argument("--log-seed", type=int, default=9999)
    parser.add_argument("--physical-seed", type=int, default=7777)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    methods = [item.strip().lower() for item in args.methods.split(",") if item.strip()]
    runs = []
    for method in methods:
        started = time.perf_counter()
        if method == "deepbsde":
            solver, params = _init_deepbsde(args.source_root, args.deepbsde_checkpoint, args.device)
            checkpoint = args.deepbsde_checkpoint
            log_terminal_fn = _deepbsde_log_terminal
            physical_terminal_fn = _deepbsde_physical_terminal
        elif method == "dbdp2":
            solver, params = _init_dbdp2(args.source_root, args.dbdp2_checkpoint, args.device)
            checkpoint = args.dbdp2_checkpoint
            log_terminal_fn = _dbdp2_log_terminal
            physical_terminal_fn = _dbdp2_physical_terminal
        else:
            raise ValueError(f"unsupported method: {method}")

        V_log, dW_log = _simulate(args.source_root, params, solver, args.scenarios, args.log_seed)
        log_terminal = log_terminal_fn(solver, V_log, dW_log)
        del V_log, dW_log
        V_physical, dW_physical = _simulate(args.source_root, params, solver, args.scenarios, args.physical_seed)
        physical_terminal = physical_terminal_fn(solver, V_physical, dW_physical)
        del V_physical, dW_physical
        runs.append(
            {
                "method": method,
                "checkpoint": str(checkpoint),
                "check_p0": float(solver.P0.item()),
                "p0": float(math.exp(solver.P0.item())),
                "log_space": _terminal_stats(log_terminal, target=0.0),
                "physical_space": _terminal_stats(physical_terminal, target=1.0),
                "elapsed_seconds": time.perf_counter() - started,
            }
        )

    report = {
        "schema_version": 1,
        "report_type": "paper_2608_07977_sre_out_of_sample_verification",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_root": str(args.source_root),
        "scenarios": args.scenarios,
        "log_seed": args.log_seed,
        "physical_seed": args.physical_seed,
        "device": args.device,
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Output: {args.output.resolve()}")
    for run in runs:
        log_stats = run["log_space"]
        physical_stats = run["physical_space"]
        print(
            f"{run['method']}: log mean={log_stats['mean']:+.6f} std={log_stats['std']:.6f} "
            f"mse={log_stats['mse']:.2e}; physical mean={physical_stats['mean']:.6f} "
            f"std={physical_stats['std']:.6f} mse={physical_stats['mse']:.2e}; "
            f"elapsed={run['elapsed_seconds']:.2f}s"
        )


if __name__ == "__main__":
    main()
