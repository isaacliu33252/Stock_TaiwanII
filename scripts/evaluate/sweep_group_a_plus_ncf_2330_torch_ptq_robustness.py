#!/usr/bin/env python3
"""Run robustness checks for the ncf_2330 Torch PTQ shadow.

This script extends the one-shot PTQ shadow into a multi-seed, multi-window
review. It also compares the Torch student against the original ncf_2330
pipeline and runs a Torch dynamic-quantization backend smoke test. It is
research-only and never authorizes live weights.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from torch.ao.quantization import quantize_dynamic

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.train_group_a_plus_ncf_2330_torch_ptq_shadow import (
    FEATURE_COLUMNS,
    LABEL_COLUMN,
    ActivationQuantizedWrapper,
    SplitData,
    TinyNCFStudent,
    _activation_ranges,
    _damage,
    _layerwise_w4a4_review,
    _load_panel,
    _metrics,
    _train_model,
    _weight_quantized_model,
)


DEFAULT_PANEL = PROJECT_ROOT / "results/ncf_2330_panel_latest_20260821.csv"
DEFAULT_ORIGINAL_NCF = PROJECT_ROOT / "results/ncf_2330_latest_20260821.json"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "report/group_a_plus/latest/ptq_calibration_robustness_sweep.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/ptq_calibration_robustness_sweep.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/ptq_calibration_robustness/history"

MAX_W8A8_DAMAGE = 0.03
MAX_W4_WEIGHT_ONLY_DAMAGE = 0.05
MAX_W4A4_DAMAGE = 0.05
MIN_LIVE_TEST_ROWS = 252
MIN_LIVE_WINDOWS = 3
MIN_LIVE_SEEDS = 5
MIN_STUDENT_VS_ORIGINAL_RATIO = 0.95


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _original_pipeline_metric(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    horizons = payload.get("horizons") if isinstance(payload.get("horizons"), dict) else {}
    aucs: dict[str, float] = {}
    for h, h_payload in horizons.items():
        try:
            aucs[str(h)] = float(h_payload["classification"]["val_auc"])
        except (KeyError, TypeError, ValueError):
            continue
    mean_auc = float(np.mean(list(aucs.values()))) if aucs else None
    return {
        "path": str(path),
        "exists": path.exists(),
        "metric_name": "mean_direction_val_auc_across_horizons",
        "metric": mean_auc,
        "horizon_aucs": aucs,
    }


def _make_split(frame: pd.DataFrame, start: int, train_rows: int, calib_rows: int, test_rows: int) -> SplitData:
    train = frame.iloc[start : start + train_rows]
    calib = frame.iloc[start + train_rows : start + train_rows + calib_rows]
    test = frame.iloc[start + train_rows + calib_rows : start + train_rows + calib_rows + test_rows]
    if len(train) < train_rows or len(calib) < calib_rows or len(test) < test_rows:
        raise ValueError("insufficient rows for split")

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


def _split_starts(n_rows: int, train_rows: int, calib_rows: int, test_rows: int, n_windows: int) -> list[int]:
    width = train_rows + calib_rows + test_rows
    max_start = n_rows - width
    if max_start < 0:
        raise ValueError(f"not enough rows: n={n_rows}, required={width}")
    if n_windows <= 1:
        return [0]
    return sorted({int(round(x)) for x in np.linspace(0, max_start, n_windows)})


def _dynamic_quant_backend_metrics(model: TinyNCFStudent, data: SplitData) -> dict[str, Any]:
    try:
        q_model = quantize_dynamic(copy.deepcopy(model).cpu(), {torch.nn.Linear}, dtype=torch.qint8)
        return {
            "available": True,
            "backend": "torch.ao.quantization.quantize_dynamic_qint8_cpu",
            "metrics": _metrics(q_model, data.x_test.cpu(), data.y_test.cpu()),
        }
    except Exception as exc:  # pragma: no cover - backend availability varies by build
        return {"available": False, "backend": "torch_dynamic_quantization", "error": str(exc)}


def _run_one(data: SplitData, *, seed: int, epochs: int, lr: float, hidden_dim: int) -> dict[str, Any]:
    model = _train_model(data, seed=seed, epochs=epochs, lr=lr, hidden_dim=hidden_dim)
    fp32 = _metrics(model, data.x_test, data.y_test)
    fp32_auc = float(fp32["auc"])

    w8_model = _weight_quantized_model(model, 8)
    w8_ranges = _activation_ranges(model, data.x_calib, percentile=0.99)
    w8a8 = _metrics(ActivationQuantizedWrapper(w8_model, bits=8, ranges=w8_ranges), data.x_test, data.y_test)

    w4_model = _weight_quantized_model(model, 4)
    w4_weight_only = _metrics(w4_model, data.x_test, data.y_test)

    w4_ranges = _activation_ranges(model, data.x_calib, percentile=0.99)
    w4a4 = _metrics(ActivationQuantizedWrapper(w4_model, bits=4, ranges=w4_ranges), data.x_test, data.y_test)
    layerwise = _layerwise_w4a4_review(model, data, fp32_auc, w4_ranges)
    dynamic_backend = _dynamic_quant_backend_metrics(model, data)
    if dynamic_backend.get("available"):
        dynamic_backend["damage_pct_of_fp32_signal"] = _damage(fp32_auc, dynamic_backend["metrics"]["auc"])

    return {
        "seed": seed,
        "fp32": fp32,
        "W8A8": {
            "metrics": w8a8,
            "damage_pct_of_fp32_signal": _damage(fp32_auc, w8a8["auc"]),
            "passed_research_gate": _damage(fp32_auc, w8a8["auc"]) <= MAX_W8A8_DAMAGE,
        },
        "W4_weight_only": {
            "metrics": w4_weight_only,
            "damage_pct_of_fp32_signal": _damage(fp32_auc, w4_weight_only["auc"]),
            "passed_research_gate": _damage(fp32_auc, w4_weight_only["auc"]) <= MAX_W4_WEIGHT_ONLY_DAMAGE,
        },
        "W4A4": {
            "metrics": w4a4,
            "damage_pct_of_fp32_signal": _damage(fp32_auc, w4a4["auc"]),
            "passed_research_gate": _damage(fp32_auc, w4a4["auc"]) <= MAX_W4A4_DAMAGE,
            "percentile_sweep_tested": True,
            "layerwise_exception_reviewed": True,
            "layerwise_exception_review": layerwise,
        },
        "dynamic_quant_backend": dynamic_backend,
    }


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ["fp32", "W8A8", "W4_weight_only", "W4A4"]:
        aucs = [
            float((row[key]["metrics"] if key != "fp32" else row[key])["auc"])
            for row in rows
        ]
        damages = [float(row[key]["damage_pct_of_fp32_signal"]) for row in rows if key != "fp32"]
        out[key] = {
            "mean_auc": float(np.mean(aucs)),
            "min_auc": float(np.min(aucs)),
            "max_auc": float(np.max(aucs)),
            "std_auc": float(np.std(aucs)),
        }
        if damages:
            out[key]["mean_damage_pct_of_fp32_signal"] = float(np.mean(damages))
            out[key]["max_damage_pct_of_fp32_signal"] = float(np.max(damages))
            out[key]["pass_rate"] = float(np.mean([bool(row[key]["passed_research_gate"]) for row in rows]))
    backend_rows = [row["dynamic_quant_backend"] for row in rows if row["dynamic_quant_backend"].get("available")]
    if backend_rows:
        aucs = [float(row["metrics"]["auc"]) for row in backend_rows]
        damages = [float(row["damage_pct_of_fp32_signal"]) for row in backend_rows]
        out["dynamic_quant_backend"] = {
            "available_rate": len(backend_rows) / len(rows),
            "mean_auc": float(np.mean(aucs)),
            "max_damage_pct_of_fp32_signal": float(np.max(damages)),
        }
    else:
        out["dynamic_quant_backend"] = {"available_rate": 0.0}
    return out


def build_sweep(
    *,
    as_of: str,
    panel_path: Path = DEFAULT_PANEL,
    original_ncf_path: Path = DEFAULT_ORIGINAL_NCF,
    seeds: list[int] | None = None,
    n_windows: int = 3,
    train_rows: int = 220,
    calib_rows: int = 55,
    test_rows: int = 55,
    epochs: int = 350,
    lr: float = 0.01,
    hidden_dim: int = 16,
) -> dict[str, Any]:
    seeds = seeds or [1, 2, 3, 42, 101]
    frame = _load_panel(panel_path)
    starts = _split_starts(len(frame), train_rows, calib_rows, test_rows, n_windows)
    original = _original_pipeline_metric(original_ncf_path)

    windows: list[dict[str, Any]] = []
    flat_rows: list[dict[str, Any]] = []
    for wi, start in enumerate(starts, start=1):
        data = _make_split(frame, start, train_rows, calib_rows, test_rows)
        runs = [_run_one(data, seed=seed, epochs=epochs, lr=lr, hidden_dim=hidden_dim) for seed in seeds]
        flat_rows.extend(runs)
        windows.append(
            {
                "window_id": wi,
                "start_row": start,
                "train_period": data.train_dates,
                "calibration_period": data.calib_dates,
                "test_period": data.test_dates,
                "train_rows": train_rows,
                "calibration_rows": calib_rows,
                "test_rows": test_rows,
                "test_positive_rate": float(data.y_test.mean().item()),
                "runs": runs,
                "aggregate": _aggregate(runs),
            }
        )

    aggregate = _aggregate(flat_rows)
    original_metric = original.get("metric")
    fp32_mean = aggregate["fp32"]["mean_auc"]
    fp32_vs_original_ratio = (
        float(fp32_mean / original_metric)
        if isinstance(original_metric, (float, int)) and original_metric
        else None
    )

    live_blockers: list[str] = []
    if n_windows < MIN_LIVE_WINDOWS:
        live_blockers.append("insufficient_walk_forward_windows_for_live")
    if len(seeds) < MIN_LIVE_SEEDS:
        live_blockers.append("insufficient_seed_count_for_live")
    if test_rows < MIN_LIVE_TEST_ROWS:
        live_blockers.append("test_rows_below_live_minimum")
    if fp32_vs_original_ratio is None:
        live_blockers.append("missing_original_pipeline_comparison")
    elif fp32_vs_original_ratio < MIN_STUDENT_VS_ORIGINAL_RATIO:
        live_blockers.append("torch_student_underperforms_original_pipeline")
    if aggregate["dynamic_quant_backend"].get("available_rate", 0.0) < 1.0:
        live_blockers.append("dynamic_quant_backend_not_available_for_all_runs")
    # Even if the smoke backend is available, this is not a latency/execution
    # deployment validation against the production path.
    live_blockers.append("production_quantized_inference_path_not_integrated_or_latency_validated")
    live_blockers.append("student_shadow_is_not_authorized_replacement_for_ncf_2330")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_ncf_2330_torch_ptq_robustness_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "source_panel": str(panel_path),
        "seeds": seeds,
        "n_windows": len(starts),
        "window_shape": {"train_rows": train_rows, "calibration_rows": calib_rows, "test_rows": test_rows},
        "original_pipeline_baseline": original,
        "aggregate": aggregate,
        "student_vs_original": {
            "student_fp32_mean_auc": fp32_mean,
            "original_mean_auc": original_metric,
            "ratio": fp32_vs_original_ratio,
            "minimum_live_ratio": MIN_STUDENT_VS_ORIGINAL_RATIO,
        },
        "windows": windows,
        "decision": {
            "research_robustness_complete": True,
            "fake_quant_research_passed": all(
                aggregate[name].get("pass_rate") == 1.0 for name in ["W8A8", "W4_weight_only", "W4A4"]
            ),
            "dynamic_quant_backend_smoke_available": aggregate["dynamic_quant_backend"].get("available_rate", 0.0) > 0.0,
            "promote_to_live": False,
            "quantized_inference_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "live_blocking_reasons": sorted(set(live_blockers)),
        },
    }


def _write_md(payload: dict[str, Any], path: Path) -> None:
    agg = payload["aggregate"]
    decision = payload["decision"]
    lines = [
        "# ncf_2330 Torch PTQ Robustness Sweep",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Windows: `{payload['n_windows']}`",
        f"- Seeds: `{payload['seeds']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Quantized inference allowed: `{decision['quantized_inference_allowed']}`",
        f"- Target weight change allowed: `{decision['target_weight_change_allowed']}`",
        "",
        "## Aggregate",
        "",
        f"- FP32 mean AUC: `{agg['fp32']['mean_auc']}`",
        f"- W8A8 mean AUC: `{agg['W8A8']['mean_auc']}` pass_rate=`{agg['W8A8'].get('pass_rate')}`",
        f"- W4 weight-only mean AUC: `{agg['W4_weight_only']['mean_auc']}` pass_rate=`{agg['W4_weight_only'].get('pass_rate')}`",
        f"- W4A4 mean AUC: `{agg['W4A4']['mean_auc']}` pass_rate=`{agg['W4A4'].get('pass_rate')}`",
        f"- Dynamic quant backend available rate: `{agg['dynamic_quant_backend'].get('available_rate')}`",
        "",
        "## Original Pipeline Comparison",
        "",
        f"- Original mean AUC: `{payload['student_vs_original']['original_mean_auc']}`",
        f"- Student FP32 mean AUC: `{payload['student_vs_original']['student_fp32_mean_auc']}`",
        f"- Student/original ratio: `{payload['student_vs_original']['ratio']}`",
        "",
        "## Live Blocking Reasons",
        "",
    ]
    lines.extend(f"- `{reason}`" for reason in decision["live_blocking_reasons"])
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- Research robustness can be used as PTQ governance evidence.",
            "- Do not replace the original ncf_2330 pipeline.",
            "- Do not connect the Torch student or quantized variants to latest strategy.",
            "- No live strategy, target weight, rebalance, or order file was changed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"ncf_2330_torch_ptq_robustness_sweep_{as_of.replace('-', '')}.json"


def write_sweep(payload: dict[str, Any], output_json: Path, output_md: Path, history_dir: Path | None) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_md(payload, output_md)
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
    parser.add_argument("--original-ncf", default=str(DEFAULT_ORIGINAL_NCF))
    parser.add_argument("--seeds", default="1,2,3,42,101")
    parser.add_argument("--n-windows", type=int, default=3)
    parser.add_argument("--train-rows", type=int, default=220)
    parser.add_argument("--calib-rows", type=int, default=55)
    parser.add_argument("--test-rows", type=int, default=55)
    parser.add_argument("--epochs", type=int, default=350)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--hidden-dim", type=int, default=16)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seeds = [int(part.strip()) for part in args.seeds.split(",") if part.strip()]
    payload = build_sweep(
        as_of=args.as_of,
        panel_path=_resolve(args.panel),
        original_ncf_path=_resolve(args.original_ncf),
        seeds=seeds,
        n_windows=args.n_windows,
        train_rows=args.train_rows,
        calib_rows=args.calib_rows,
        test_rows=args.test_rows,
        epochs=args.epochs,
        lr=args.lr,
        hidden_dim=args.hidden_dim,
    )
    write_sweep(
        payload,
        _resolve(args.output_json),
        _resolve(args.output_md),
        None if args.no_history else _resolve(args.history_dir),
    )
    print(f"ncf_2330 Torch PTQ robustness sweep: {_resolve(args.output_json)}")
    print(
        json.dumps(
            {
                "fp32_mean_auc": payload["aggregate"]["fp32"]["mean_auc"],
                "w8a8_pass_rate": payload["aggregate"]["W8A8"]["pass_rate"],
                "w4_weight_only_pass_rate": payload["aggregate"]["W4_weight_only"]["pass_rate"],
                "w4a4_pass_rate": payload["aggregate"]["W4A4"]["pass_rate"],
                "student_original_ratio": payload["student_vs_original"]["ratio"],
                "quantized_inference_allowed": payload["decision"]["quantized_inference_allowed"],
                "live_blocking_reasons": payload["decision"]["live_blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
