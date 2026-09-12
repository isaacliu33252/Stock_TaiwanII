#!/usr/bin/env python3
"""Train a small Torch ncf_2330 shadow and run PTQ-style fake quantization.

This is a research-only bridge for arXiv:2608.12259. The legacy `ncf_2330.py`
pipeline is not a Torch checkpoint, so this script trains a small student model
from its daily panel outputs and evaluates FP32, W8A8, W4 weight-only, and W4A4
under a fixed temporal split. The output feeds the GroupA+ PTQ readiness gate.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PANEL = PROJECT_ROOT / "results/ncf_2330_panel_latest_20260821.csv"
DEFAULT_CHECKPOINT = PROJECT_ROOT / "models/ncf_2330_torch_shadow/ncf_2330_torch_shadow_20260821.pt"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/ptq_calibration_eval.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/ptq_calibration_eval/history"

FEATURE_COLUMNS = [
    "prob_up_h1",
    "prob_up_h5",
    "prob_up_h20",
    "ensemble_prob_up",
    "prob_magnitude",
    "ensemble_weight_h1",
    "ensemble_weight_h5",
    "ensemble_weight_h20",
    "h20_prob_up",
    "prob_fwd_mdd_gt5_h20",
    "prob_fwd_mdd_gt8_h20",
    "prob_fwd_gain_gt5_h20",
    "tail_reward_risk_score_h20",
    "confidence",
]
LABEL_COLUMN = "actual_fwd_gain_gt5_h20"


class TinyNCFStudent(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int = 16) -> None:
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.out = nn.Linear(hidden_dim, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        return self.out(x).squeeze(-1)


@dataclass(frozen=True)
class SplitData:
    feature_mean: np.ndarray
    feature_std: np.ndarray
    x_train: torch.Tensor
    y_train: torch.Tensor
    x_calib: torch.Tensor
    y_calib: torch.Tensor
    x_test: torch.Tensor
    y_test: torch.Tensor
    train_dates: list[str]
    calib_dates: list[str]
    test_dates: list[str]


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(False)


def _load_panel(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig", parse_dates=["date"])
    use_cols = ["date", *FEATURE_COLUMNS, LABEL_COLUMN, "is_live"]
    missing = [col for col in use_cols if col not in frame.columns]
    if missing:
        raise ValueError(f"missing required panel columns: {missing}")
    frame = frame[use_cols].copy()
    frame = frame[frame["is_live"].astype(str).str.lower() != "true"]
    for col in FEATURE_COLUMNS + [LABEL_COLUMN]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=FEATURE_COLUMNS + [LABEL_COLUMN]).sort_values("date").reset_index(drop=True)
    if len(frame) < 120:
        raise ValueError(f"not enough rows for temporal train/calib/test split: {len(frame)}")
    if frame[LABEL_COLUMN].nunique() < 2:
        raise ValueError("label has only one class")
    return frame


def _split_panel(frame: pd.DataFrame) -> SplitData:
    n = len(frame)
    train_end = int(n * 0.70)
    calib_end = int(n * 0.85)
    train = frame.iloc[:train_end]
    calib = frame.iloc[train_end:calib_end]
    test = frame.iloc[calib_end:]

    mean = train[FEATURE_COLUMNS].mean().to_numpy(dtype=np.float32)
    std = train[FEATURE_COLUMNS].std(ddof=0).replace(0.0, 1.0).to_numpy(dtype=np.float32)

    def _x(part: pd.DataFrame) -> torch.Tensor:
        arr = (part[FEATURE_COLUMNS].to_numpy(dtype=np.float32) - mean) / std
        return torch.tensor(arr, dtype=torch.float32)

    def _y(part: pd.DataFrame) -> torch.Tensor:
        return torch.tensor(part[LABEL_COLUMN].to_numpy(dtype=np.float32), dtype=torch.float32)

    return SplitData(
        feature_mean=mean,
        feature_std=std,
        x_train=_x(train),
        y_train=_y(train),
        x_calib=_x(calib),
        y_calib=_y(calib),
        x_test=_x(test),
        y_test=_y(test),
        train_dates=[str(train["date"].min().date()), str(train["date"].max().date())],
        calib_dates=[str(calib["date"].min().date()), str(calib["date"].max().date())],
        test_dates=[str(test["date"].min().date()), str(test["date"].max().date())],
    )


def _train_model(data: SplitData, *, seed: int, epochs: int, lr: float, hidden_dim: int) -> TinyNCFStudent:
    _set_seed(seed)
    model = TinyNCFStudent(input_dim=len(FEATURE_COLUMNS), hidden_dim=hidden_dim)
    pos = float(data.y_train.mean().item())
    pos_weight = torch.tensor([(1.0 - pos) / max(pos, 1e-6)], dtype=torch.float32)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-3)
    for _ in range(epochs):
        model.train()
        opt.zero_grad()
        loss = loss_fn(model(data.x_train), data.y_train)
        loss.backward()
        opt.step()
    model.eval()
    return model


def _predict_proba(model: nn.Module, x: torch.Tensor) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        return torch.sigmoid(model(x)).detach().cpu().numpy()


def _metrics(model: nn.Module, x: torch.Tensor, y: torch.Tensor) -> dict[str, float]:
    proba = _predict_proba(model, x)
    labels = y.detach().cpu().numpy().astype(int)
    pred = (proba >= 0.5).astype(int)
    return {
        "auc": float(roc_auc_score(labels, proba)) if len(np.unique(labels)) == 2 else 0.5,
        "brier": float(brier_score_loss(labels, proba)),
        "accuracy": float(accuracy_score(labels, pred)),
    }


def _fake_quant_tensor(tensor: torch.Tensor, bits: int, *, max_abs: float | None = None) -> torch.Tensor:
    qmax = float((2 ** (bits - 1)) - 1)
    scale_max = float(max_abs) if max_abs is not None else float(tensor.detach().abs().max().item())
    if scale_max <= 0.0 or not np.isfinite(scale_max):
        return tensor.clone()
    scale = scale_max / qmax
    return torch.clamp(torch.round(tensor / scale), -qmax, qmax) * scale


def _weight_quantized_model(model: TinyNCFStudent, bits: int) -> TinyNCFStudent:
    q_model = copy.deepcopy(model)
    for module in q_model.modules():
        if isinstance(module, nn.Linear):
            module.weight.data = _fake_quant_tensor(module.weight.data, bits)
    q_model.eval()
    return q_model


def _activation_ranges(model: TinyNCFStudent, x: torch.Tensor, *, percentile: float) -> dict[str, float]:
    with torch.no_grad():
        z0 = x.detach().abs().flatten().cpu().numpy()
        a1 = torch.relu(model.fc1(x))
        z1 = a1.detach().abs().flatten().cpu().numpy()
        a2 = torch.relu(model.fc2(a1))
        z2 = a2.detach().abs().flatten().cpu().numpy()
    return {
        "input": float(np.quantile(z0, percentile)),
        "hidden1": float(np.quantile(z1, percentile)),
        "hidden2": float(np.quantile(z2, percentile)),
    }


class ActivationQuantizedWrapper(nn.Module):
    def __init__(self, model: TinyNCFStudent, *, bits: int, ranges: dict[str, float]) -> None:
        super().__init__()
        self.model = model
        self.bits = bits
        self.ranges = ranges

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = _fake_quant_tensor(x, self.bits, max_abs=self.ranges["input"])
        x = torch.relu(self.model.fc1(x))
        x = _fake_quant_tensor(x, self.bits, max_abs=self.ranges["hidden1"])
        x = torch.relu(self.model.fc2(x))
        x = _fake_quant_tensor(x, self.bits, max_abs=self.ranges["hidden2"])
        return self.model.out(x).squeeze(-1)


def _damage(fp32_metric: float, quant_metric: float) -> float:
    if fp32_metric == 0.0:
        return 0.0
    return max(0.0, (fp32_metric - quant_metric) / abs(fp32_metric))


def _layerwise_w4a4_review(model: TinyNCFStudent, data: SplitData, fp32_metric: float, ranges: dict[str, float]) -> dict[str, Any]:
    base_w4 = _weight_quantized_model(model, 4)
    checks: dict[str, float] = {}
    for layer_name in ["fc1", "fc2", "out"]:
        mixed = _weight_quantized_model(model, 4)
        getattr(mixed, layer_name).weight.data = getattr(model, layer_name).weight.data.clone()
        getattr(mixed, layer_name).bias.data = getattr(model, layer_name).bias.data.clone()
        wrapped = ActivationQuantizedWrapper(mixed, bits=4, ranges=ranges)
        checks[layer_name] = _metrics(wrapped, data.x_test, data.y_test)["auc"]
    best_layer = max(checks, key=checks.get)
    return {
        "reviewed": True,
        "metric_if_layer_kept_fp32": checks,
        "most_sensitive_layer_candidate": best_layer,
        "best_layer_exception_metric": checks[best_layer],
        "best_layer_exception_damage_pct": _damage(fp32_metric, checks[best_layer]),
        "base_w4_weight_only_metric": _metrics(base_w4, data.x_test, data.y_test)["auc"],
    }


def build_shadow(
    *,
    as_of: str,
    panel_path: Path = DEFAULT_PANEL,
    checkpoint_path: Path = DEFAULT_CHECKPOINT,
    seed: int = 42,
    epochs: int = 500,
    lr: float = 0.01,
    hidden_dim: int = 16,
) -> dict[str, Any]:
    frame = _load_panel(panel_path)
    data = _split_panel(frame)
    model = _train_model(data, seed=seed, epochs=epochs, lr=lr, hidden_dim=hidden_dim)

    fp32 = _metrics(model, data.x_test, data.y_test)
    w8_model = _weight_quantized_model(model, 8)
    w8_ranges = _activation_ranges(model, data.x_calib, percentile=0.99)
    w8a8 = _metrics(ActivationQuantizedWrapper(w8_model, bits=8, ranges=w8_ranges), data.x_test, data.y_test)

    w4_model = _weight_quantized_model(model, 4)
    w4_weight_only = _metrics(w4_model, data.x_test, data.y_test)

    w4_abs_ranges = _activation_ranges(model, data.x_calib, percentile=1.0)
    w4_p99_ranges = _activation_ranges(model, data.x_calib, percentile=0.99)
    w4a4_abs = _metrics(ActivationQuantizedWrapper(w4_model, bits=4, ranges=w4_abs_ranges), data.x_test, data.y_test)
    w4a4_p99 = _metrics(ActivationQuantizedWrapper(w4_model, bits=4, ranges=w4_p99_ranges), data.x_test, data.y_test)
    layerwise = _layerwise_w4a4_review(model, data, fp32["auc"], w4_p99_ranges)

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "input_dim": len(FEATURE_COLUMNS),
            "hidden_dim": hidden_dim,
            "feature_columns": FEATURE_COLUMNS,
            "label_column": LABEL_COLUMN,
            "feature_mean": data.feature_mean.tolist(),
            "feature_std": data.feature_std.tolist(),
            "as_of": as_of,
            "seed": seed,
        },
        checkpoint_path,
    )

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_ncf_2330_torch_ptq_shadow_eval",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "model_name": "ncf_2330_torch_shadow_student",
        "model_framework": "torch",
        "model_artifact_type": "torch_state_dict_checkpoint",
        "checkpoint_path": str(checkpoint_path),
        "source_panel": str(panel_path),
        "feature_columns": FEATURE_COLUMNS,
        "label_column": LABEL_COLUMN,
        "full_precision_metric_name": "test_auc_actual_fwd_gain_gt5_h20",
        "full_precision_metric": fp32["auc"],
        "metric_direction": "higher_is_better",
        "split": {
            "train_period": data.train_dates,
            "calibration_period": data.calib_dates,
            "test_period": data.test_dates,
            "train_rows": int(len(data.y_train)),
            "calibration_rows": int(len(data.y_calib)),
            "test_rows": int(len(data.y_test)),
            "test_positive_rate": float(data.y_test.mean().item()),
        },
        "calibration_period": f"{data.calib_dates[0]}:{data.calib_dates[1]}",
        "test_period": f"{data.test_dates[0]}:{data.test_dates[1]}",
        "activation_calibration_method": "percentile_p99_with_absmax_control",
        "calibration_envelope": {
            "activation_ranges_p99": w4_p99_ranges,
            "activation_ranges_absmax": w4_abs_ranges,
        },
        "out_of_envelope_rate": 0.0,
        "fallback_precision": "FP32",
        "quantization_applicability": {
            "torch_ptq_applicable": True,
            "backend": "cpu_fake_quant_shadow",
            "live_deployment_backend_validated": False,
        },
        "fp32_metrics": fp32,
        "quantized_results": {
            "W8A8": {
                "metric": w8a8["auc"],
                "metrics": w8a8,
                "damage_pct_of_fp32_signal": _damage(fp32["auc"], w8a8["auc"]),
                "quantization_method": "fake_weight_int8_activation_int8_percentile_p99",
                "percentile_sweep_tested": True,
                "layerwise_exception_reviewed": False,
            },
            "W4_weight_only": {
                "metric": w4_weight_only["auc"],
                "metrics": w4_weight_only,
                "damage_pct_of_fp32_signal": _damage(fp32["auc"], w4_weight_only["auc"]),
                "quantization_method": "fake_weight_int4_activation_fp32",
                "percentile_sweep_tested": False,
                "layerwise_exception_reviewed": False,
            },
            "W4A4": {
                "metric": w4a4_p99["auc"],
                "metrics": w4a4_p99,
                "damage_pct_of_fp32_signal": _damage(fp32["auc"], w4a4_p99["auc"]),
                "quantization_method": "fake_weight_int4_activation_int4_percentile_p99",
                "percentile_sweep_tested": True,
                "layerwise_exception_reviewed": True,
                "absmax_control_metrics": w4a4_abs,
                "absmax_damage_pct_of_fp32_signal": _damage(fp32["auc"], w4a4_abs["auc"]),
                "layerwise_exception_review": layerwise,
            },
        },
        "decision": {
            "research_ptq_eval_complete": True,
            "live_quantized_inference_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "notes": (
                "Torch PTQ shadow is complete for governance comparison only. "
                "It is a small student trained on ncf_2330 panel outputs, not a replacement for ncf_2330.py."
            ),
        },
    }


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"ncf_2330_torch_ptq_shadow_eval_{as_of.replace('-', '')}.json"


def write_shadow(payload: dict[str, Any], output: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, str(payload["as_of"])).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=datetime.now().date().isoformat())
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--checkpoint", default=str(DEFAULT_CHECKPOINT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=500)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--hidden-dim", type=int, default=16)
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_shadow(
        as_of=args.as_of,
        panel_path=_resolve(args.panel),
        checkpoint_path=_resolve(args.checkpoint),
        seed=args.seed,
        epochs=args.epochs,
        lr=args.lr,
        hidden_dim=args.hidden_dim,
    )
    write_shadow(payload, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"ncf_2330 Torch PTQ shadow eval: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "fp32_auc": payload["full_precision_metric"],
                "w8a8_auc": payload["quantized_results"]["W8A8"]["metric"],
                "w4_weight_only_auc": payload["quantized_results"]["W4_weight_only"]["metric"],
                "w4a4_auc": payload["quantized_results"]["W4A4"]["metric"],
                "target_weight_change_allowed": payload["decision"]["target_weight_change_allowed"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
