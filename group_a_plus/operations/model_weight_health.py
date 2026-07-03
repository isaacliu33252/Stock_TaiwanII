"""Read-only model weight health diagnostics for GroupA+.

Inspired by WeightWatcher, but intentionally implemented as a lightweight
optional shadow report. It does not mutate models and does not influence active
allocation.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from group_a_plus.paths import PROJECT_ROOT
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_MODEL_PATH = PROJECT_ROOT / "models/portfolio/group_a_plus_4tickers_2020_2025.zip"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "results/model_weight_health_shadow_latest_20260701.json"
OVER_TRAINED_ALPHA = 2.0
UNDER_TRAINED_ALPHA = 6.0


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_numpy(value: Any) -> np.ndarray:
    try:
        import torch

        if isinstance(value, torch.Tensor):
            return value.detach().cpu().numpy()
    except Exception:
        pass
    return np.asarray(value)


def _matrix_from_weight(weight: Any) -> np.ndarray | None:
    arr = _to_numpy(weight).astype(float, copy=False)
    if arr.ndim < 2:
        return None
    if arr.ndim > 2:
        arr = arr.reshape(arr.shape[0], -1)
    if arr.shape[0] < 2 or arr.shape[1] < 2:
        return None
    if not np.isfinite(arr).all():
        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    if np.allclose(arr, 0.0):
        return None
    return arr


def _tail_alpha(eigenvalues: np.ndarray, *, tail_fraction: float = 0.5) -> float | None:
    vals = np.sort(np.asarray(eigenvalues, dtype=float))
    vals = vals[np.isfinite(vals) & (vals > 1e-12)]
    if len(vals) < 8:
        return None
    tail_start = max(0, int(len(vals) * (1.0 - tail_fraction)))
    tail = vals[tail_start:]
    if len(tail) < 4:
        return None
    ranks = np.arange(len(tail), 0, -1, dtype=float) / float(len(tail))
    x = np.log(tail)
    y = np.log(ranks)
    if np.std(x) <= 1e-12:
        return None
    slope, _ = np.polyfit(x, y, 1)
    alpha = -float(slope)
    if not np.isfinite(alpha) or alpha <= 0.0:
        return None
    return alpha


def analyze_weight_matrix(name: str, weight: Any) -> dict[str, Any] | None:
    matrix = _matrix_from_weight(weight)
    if matrix is None:
        return None
    singular_values = np.linalg.svd(matrix, compute_uv=False)
    singular_values = singular_values[np.isfinite(singular_values) & (singular_values > 1e-12)]
    if len(singular_values) < 2:
        return None
    eigenvalues = singular_values ** 2
    fro_norm_sq = float(np.sum(eigenvalues))
    spectral_norm_sq = float(np.max(eigenvalues))
    stable_rank = fro_norm_sq / spectral_norm_sq if spectral_norm_sq > 0.0 else None
    alpha = _tail_alpha(eigenvalues)
    log_norm = math.log10(fro_norm_sq) if fro_norm_sq > 0.0 else None
    log_spectral_norm = math.log10(spectral_norm_sq) if spectral_norm_sq > 0.0 else None
    alpha_weighted = (
        float(alpha * log_spectral_norm)
        if alpha is not None and log_spectral_norm is not None
        else None
    )
    warning = ""
    if alpha is not None and alpha < OVER_TRAINED_ALPHA:
        warning = "over-trained"
    elif alpha is not None and alpha > UNDER_TRAINED_ALPHA:
        warning = "under-trained"
    return {
        "name": name,
        "shape": list(matrix.shape),
        "rank": int(np.linalg.matrix_rank(matrix)),
        "log_norm": round(float(log_norm), 6) if log_norm is not None else None,
        "log_spectral_norm": round(float(log_spectral_norm), 6) if log_spectral_norm is not None else None,
        "stable_rank": round(float(stable_rank), 6) if stable_rank is not None else None,
        "alpha": round(float(alpha), 6) if alpha is not None else None,
        "alpha_weighted": round(float(alpha_weighted), 6) if alpha_weighted is not None else None,
        "warning": warning,
    }


def _summary(details: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = ("log_norm", "log_spectral_norm", "stable_rank", "alpha", "alpha_weighted")
    summary: dict[str, Any] = {}
    for metric in metrics:
        values = [float(row[metric]) for row in details if row.get(metric) is not None]
        summary[metric] = round(float(np.mean(values)), 6) if values else None
    warnings: dict[str, int] = {}
    for row in details:
        warning = str(row.get("warning") or "")
        if warning:
            warnings[warning] = warnings.get(warning, 0) + 1
    summary["warning_counts"] = warnings
    return summary


def analyze_state_dict(state_dict: dict[str, Any]) -> dict[str, Any]:
    details = []
    skipped = []
    for name, weight in state_dict.items():
        if not str(name).endswith("weight"):
            continue
        row = analyze_weight_matrix(str(name), weight)
        if row is None:
            skipped.append(str(name))
        else:
            details.append(row)
    if not details:
        return {
            "status": "unavailable",
            "reason": "no_supported_weight_matrices",
            "layer_count": 0,
            "skipped_count": len(skipped),
            "details": [],
            "summary": {},
        }
    warning_count = sum(1 for row in details if row.get("warning"))
    return {
        "status": "warning" if warning_count else "ok",
        "layer_count": len(details),
        "skipped_count": len(skipped),
        "warning_count": warning_count,
        "details": details,
        "summary": _summary(details),
    }


def _load_torch_state_dict(path: Path) -> tuple[str, dict[str, Any]]:
    import torch

    payload = torch.load(str(path), map_location="cpu")
    if isinstance(payload, dict) and "state_dict" in payload and isinstance(payload["state_dict"], dict):
        return "torch_state_dict", payload["state_dict"]
    if isinstance(payload, dict):
        return "torch_state_dict", payload
    if hasattr(payload, "state_dict"):
        return "torch_module", payload.state_dict()
    raise ValueError("unsupported torch payload")


def _load_sb3_policy_state_dict(path: Path) -> tuple[str, dict[str, Any]]:
    loaders: list[tuple[str, Any]] = []
    from stable_baselines3 import A2C, PPO, SAC

    loaders.extend([("sb3_ppo_policy", PPO), ("sb3_a2c_policy", A2C), ("sb3_sac_policy", SAC)])
    errors: list[str] = []
    for label, cls in loaders:
        try:
            model = cls.load(str(path), device="cpu")
            return label, model.policy.state_dict()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}:{type(exc).__name__}")
    raise RuntimeError("unable_to_load_sb3_model:" + ",".join(errors))


def load_model_state_dict(path: Path, *, model_type: str = "auto") -> tuple[str, dict[str, Any]]:
    if model_type not in {"auto", "torch", "sb3"}:
        raise ValueError("model_type must be one of: auto, torch, sb3")
    suffix = path.suffix.lower()
    if model_type == "sb3" or (model_type == "auto" and suffix == ".zip"):
        return _load_sb3_policy_state_dict(path)
    if model_type == "torch" or suffix in {".pt", ".pth"}:
        return _load_torch_state_dict(path)
    if model_type == "auto":
        try:
            return _load_torch_state_dict(path)
        except Exception:
            return _load_sb3_policy_state_dict(path)
    raise ValueError(f"unsupported model path: {path}")


def build_model_weight_health(
    model_path: str | Path = DEFAULT_MODEL_PATH,
    *,
    model_type: str = "auto",
) -> dict[str, Any]:
    path = Path(model_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    base: dict[str, Any] = {
        "schema_version": 1,
        "report_type": "group_a_plus_model_weight_health_shadow",
        "generated_at": _utc_now(),
        "model_path": str(path),
        "model_type": model_type,
        "active_allocation_impact": "none",
        "source_inspiration": "WeightWatcher read-only DNN weight spectrum diagnostics",
    }
    if not path.exists():
        return {
            **base,
            "status": "unavailable",
            "reason": "model_path_not_found",
        }
    try:
        framework, state_dict = load_model_state_dict(path, model_type=model_type)
        analysis = analyze_state_dict(state_dict)
    except Exception as exc:  # noqa: BLE001
        return {
            **base,
            "status": "unavailable",
            "reason": type(exc).__name__,
            "error": str(exc),
        }
    return {
        **base,
        "status": analysis.get("status", "unknown"),
        "framework": framework,
        **analysis,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=str(DEFAULT_MODEL_PATH))
    parser.add_argument("--model-type", choices=["auto", "torch", "sb3"], default="auto")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    args = parser.parse_args()

    std = OutputStandardizer("group_a_plus.operations.model_weight_health")
    try:
        report = build_model_weight_health(args.model, model_type=args.model_type)
        payload = std.success(report)
    except Exception as exc:  # noqa: BLE001
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Model weight health: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
