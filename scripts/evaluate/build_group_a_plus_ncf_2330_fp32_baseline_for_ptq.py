#!/usr/bin/env python3
"""Build an original-pipeline baseline for ncf_2330 PTQ readiness.

`ncf_2330.py` is a sklearn/LightGBM/XGBoost/CatBoost ensemble, not a Torch
checkpoint. This builder therefore records the unquantized baseline metrics
needed by the PTQ readiness gate, while explicitly marking low-precision neural
PTQ as not applicable to the current model artifact.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_NCF_JSON = PROJECT_ROOT / "results/ncf_2330_latest_20260821.json"
DEFAULT_NCF_PANEL = PROJECT_ROOT / "results/ncf_2330_panel_latest_20260821.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/ptq_calibration_eval.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/ptq_calibration_eval/history"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    cur: Any = payload
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _mean_float(values: list[Any]) -> float | None:
    clean: list[float] = []
    for value in values:
        try:
            clean.append(float(value))
        except (TypeError, ValueError):
            pass
    return sum(clean) / len(clean) if clean else None


def build_baseline(
    *,
    as_of: str,
    ncf_json_path: Path = DEFAULT_NCF_JSON,
    ncf_panel_path: Path = DEFAULT_NCF_PANEL,
) -> dict[str, Any]:
    ncf = _load_json(ncf_json_path)
    horizon_keys = sorted((ncf.get("horizons") or {}).keys(), key=lambda item: int(item))
    horizon_aucs = {
        h: _nested(ncf, "horizons", h, "classification", "val_auc")
        for h in horizon_keys
    }
    horizon_briers = {
        h: _nested(ncf, "horizons", h, "classification", "ensemble_val_brier")
        for h in horizon_keys
    }
    full_precision_metric = _mean_float(list(horizon_aucs.values()))

    data_freshness = ncf.get("data_freshness") or {}
    lag_days = data_freshness.get("lag_days_vs_reference") or {}
    external_lag = lag_days.get("external_market_ohlcv")
    out_of_envelope_rate = 0.0 if external_lag in (0, 1, 2, None) else 1.0

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_ncf_2330_original_pipeline_baseline_for_ptq",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "model_name": "ncf_2330",
        "model_framework": "sklearn_lightgbm_xgboost_catboost_ensemble",
        "model_artifact_type": "scripted_original_pipeline_no_torch_checkpoint",
        "quantization_applicability": {
            "torch_ptq_applicable": False,
            "reason": "ncf_2330.py does not expose a Torch FP32 checkpoint/state_dict for INT8/INT4 PTQ.",
            "action_required_for_real_ptq": "select_or_train_a_torch_neural_checkpoint_first",
        },
        "source_outputs": {
            "ncf_json": {"path": str(ncf_json_path), "exists": ncf_json_path.exists()},
            "ncf_panel": {"path": str(ncf_panel_path), "exists": ncf_panel_path.exists()},
        },
        "full_precision_metric_name": "mean_direction_val_auc_across_horizons",
        "full_precision_metric": full_precision_metric,
        "metric_direction": "higher_is_better",
        "horizon_metrics": {
            h: {
                "val_auc": horizon_aucs.get(h),
                "ensemble_val_brier": horizon_briers.get(h),
                "probability_up": _nested(ncf, "horizons", h, "classification", "probability_up"),
                "direction": _nested(ncf, "horizons", h, "classification", "direction"),
            }
            for h in horizon_keys
        },
        "calibration_period": "train_start_to_validation_start_from_ncf_2330_runtime",
        "test_period": f"{ncf.get('last_close_date')}_latest_output_snapshot",
        "activation_calibration_method": "not_applicable_non_torch_original_pipeline",
        "calibration_envelope": {
            "data_freshness_status": data_freshness.get("status"),
            "external_market_ohlcv_lag_days_vs_reference": external_lag,
            "missing_sources": data_freshness.get("missing_sources", []),
        },
        "out_of_envelope_rate": out_of_envelope_rate,
        "fallback_precision": "original_pipeline",
        "quantized_results": {},
        "decision": {
            "fp32_or_original_baseline_available": full_precision_metric is not None,
            "quantized_results_available": False,
            "torch_ptq_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
        },
    }


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"ncf_2330_fp32_baseline_for_ptq_{as_of.replace('-', '')}.json"


def write_baseline(payload: dict[str, Any], output: Path, history_dir: Path | None) -> None:
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
    parser.add_argument("--ncf-json", default=str(DEFAULT_NCF_JSON))
    parser.add_argument("--ncf-panel", default=str(DEFAULT_NCF_PANEL))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_baseline(
        as_of=args.as_of,
        ncf_json_path=_resolve(args.ncf_json),
        ncf_panel_path=_resolve(args.ncf_panel),
    )
    write_baseline(payload, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"ncf_2330 original-pipeline baseline for PTQ: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "full_precision_metric": payload["full_precision_metric"],
                "torch_ptq_applicable": payload["quantization_applicability"]["torch_ptq_applicable"],
                "target_weight_change_allowed": payload["decision"]["target_weight_change_allowed"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
