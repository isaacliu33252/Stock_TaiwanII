#!/usr/bin/env python3
"""Build a focused diagnosis report for an NCF panel drift audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRIGGER_CRITICAL_COLUMNS = {"h20_prob_up", "confidence"}
DEFAULT_LIMITS = {
    "ensemble_prob_up": 0.15,
    "h20_prob_up": 0.15,
    "confidence": 0.28,
}
HORIZON_KEYS = ("1", "5", "20")


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _load_panel(path: str | Path) -> pd.DataFrame:
    panel = pd.read_csv(_resolve(path), encoding="utf-8-sig")
    panel["date"] = pd.to_datetime(panel["date"]).dt.strftime("%Y-%m-%d")
    return panel.set_index("date").sort_index()


def _optional_json(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    resolved = _resolve(path)
    if not resolved.exists():
        return None
    return json.loads(resolved.read_text(encoding="utf-8"))


def _number(value: Any) -> float | None:
    converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(converted) if pd.notna(converted) else None


def _value_at(panel: pd.DataFrame, date: str, column: str) -> float | None:
    if date not in panel.index or column not in panel.columns:
        return None
    return _number(panel.at[date, column])


def _month_distribution(
    baseline: pd.DataFrame,
    candidate: pd.DataFrame,
    *,
    column: str,
    threshold: float,
) -> list[dict[str, Any]]:
    common = baseline.index.intersection(candidate.index).sort_values()
    rows = []
    for date in common:
        before = _value_at(baseline, date, column)
        after = _value_at(candidate, date, column)
        if before is None or after is None:
            continue
        rows.append({"date": date, "month": date[:7], "abs_delta": abs(after - before)})
    if not rows:
        return []
    frame = pd.DataFrame(rows)
    grouped = (
        frame.assign(exceeds=frame["abs_delta"] > float(threshold))
        .groupby("month", as_index=False)
        .agg(
            row_count=("date", "count"),
            exceed_count=("exceeds", "sum"),
            mean_abs_delta=("abs_delta", "mean"),
            max_abs_delta=("abs_delta", "max"),
        )
        .sort_values(["exceed_count", "max_abs_delta"], ascending=False)
    )
    return grouped.head(8).to_dict(orient="records")


def _horizon_classification(payload: dict[str, Any], horizon: str) -> dict[str, Any]:
    horizons = payload.get("horizons") if isinstance(payload.get("horizons"), dict) else {}
    info = horizons.get(horizon) or horizons.get(int(horizon)) or {}
    classification = info.get("classification") if isinstance(info.get("classification"), dict) else {}
    return classification


def _model_set_differences(baseline_payload: dict[str, Any] | None, candidate_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not baseline_payload or not candidate_payload:
        return {"status": "not_available"}
    by_horizon = {}
    for horizon in HORIZON_KEYS:
        left = _horizon_classification(baseline_payload, horizon)
        right = _horizon_classification(candidate_payload, horizon)
        left_models = set((left.get("model_probabilities") or {}).keys())
        right_models = set((right.get("model_probabilities") or {}).keys())
        by_horizon[horizon] = {
            "baseline_models": sorted(left_models),
            "candidate_models": sorted(right_models),
            "removed_models": sorted(left_models - right_models),
            "added_models": sorted(right_models - left_models),
            "baseline_best_model": left.get("best_model"),
            "candidate_best_model": right.get("best_model"),
            "baseline_val_auc": left.get("val_auc"),
            "candidate_val_auc": right.get("val_auc"),
        }
    changed = any(item["removed_models"] or item["added_models"] for item in by_horizon.values())
    return {"status": "changed" if changed else "same", "by_horizon": by_horizon}


def _run_context_differences(baseline_payload: dict[str, Any] | None, candidate_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not baseline_payload or not candidate_payload:
        return {"status": "not_available"}
    keys = [
        "feature_selection",
        "external_features",
        "tbrain_features",
        "fourier_features",
        "global_features",
        "labeling_mode",
        "labeling_per_horizon",
        "tbl_mult",
        "direction_threshold",
    ]
    return {
        "status": "available",
        "baseline_last_close_date": baseline_payload.get("last_close_date"),
        "candidate_last_close_date": candidate_payload.get("last_close_date"),
        "baseline_data_freshness_status": (baseline_payload.get("data_freshness") or {}).get("status"),
        "candidate_data_freshness_status": (candidate_payload.get("data_freshness") or {}).get("status"),
        "candidate_stale_sources": (candidate_payload.get("data_freshness") or {}).get("stale_sources", []),
        "settings": {
            key: {
                "baseline": baseline_payload.get(key),
                "candidate": candidate_payload.get(key),
                "changed": baseline_payload.get(key) != candidate_payload.get(key),
            }
            for key in keys
        },
    }


def _panel_method_differences(baseline: pd.DataFrame, candidate: pd.DataFrame) -> dict[str, Any]:
    candidate_methods = (
        candidate["horizon_ensemble_method"].value_counts(dropna=False).to_dict()
        if "horizon_ensemble_method" in candidate.columns
        else {}
    )
    return {
        "baseline_has_horizon_ensemble_method": "horizon_ensemble_method" in baseline.columns,
        "candidate_has_horizon_ensemble_method": "horizon_ensemble_method" in candidate.columns,
        "candidate_horizon_ensemble_methods": candidate_methods,
        "baseline_has_ensemble_weights": all(f"ensemble_weight_h{h}" in baseline.columns for h in HORIZON_KEYS),
        "candidate_has_ensemble_weights": all(f"ensemble_weight_h{h}" in candidate.columns for h in HORIZON_KEYS),
    }


def build_diagnosis(
    drift_audit: str | Path,
    *,
    baseline_panel: str | Path | None = None,
    candidate_panel: str | Path | None = None,
    baseline_signal: str | Path | None = None,
    candidate_signal: str | Path | None = None,
    sensitivity_audit: str | Path | None = None,
    limits: dict[str, float] | None = None,
) -> dict[str, Any]:
    audit = _load_json(drift_audit)
    baseline_path = baseline_panel or audit["baseline_panel"]
    candidate_path = candidate_panel or audit["candidate_panel"]
    baseline = _load_panel(baseline_path)
    candidate = _load_panel(candidate_path)
    baseline_payload = _optional_json(baseline_signal)
    candidate_payload = _optional_json(candidate_signal)
    sensitivity_payload = _optional_json(sensitivity_audit)
    active_limits = {**DEFAULT_LIMITS, **(limits or {})}

    columns: dict[str, Any] = {}
    exceeded_columns = []
    trigger_critical_exceeded = []
    for column, summary in (audit.get("column_summary") or {}).items():
        max_abs = float(summary.get("max_abs_delta") or 0.0)
        limit = active_limits.get(column)
        exceeded = bool(limit is not None and max_abs > float(limit))
        if exceeded:
            exceeded_columns.append(column)
        if exceeded and column in TRIGGER_CRITICAL_COLUMNS:
            trigger_critical_exceeded.append(column)

        date = str(summary.get("max_abs_delta_date"))
        before = _value_at(baseline, date, column)
        after = _value_at(candidate, date, column)
        columns[column] = {
            "tier": "trigger_critical" if column in TRIGGER_CRITICAL_COLUMNS else "diagnostic",
            "limit": limit,
            "exceeds_limit": exceeded,
            "mean_abs_delta": summary.get("mean_abs_delta"),
            "median_abs_delta": summary.get("median_abs_delta"),
            "max_abs_delta": max_abs,
            "max_abs_delta_date": date,
            "baseline_value_at_max": before,
            "candidate_value_at_max": after,
            "signed_delta_at_max": after - before if before is not None and after is not None else None,
            "top_months_by_exceed_count": _month_distribution(
                baseline,
                candidate,
                column=column,
                threshold=float(limit if limit is not None else max_abs),
            ),
        }

    return {
        "report_type": "ncf_panel_drift_diagnosis",
        "source_drift_audit": str(_resolve(drift_audit)),
        "baseline_panel": str(_resolve(baseline_path)),
        "candidate_panel": str(_resolve(candidate_path)),
        "overlap_start": audit.get("overlap_start"),
        "overlap_end": audit.get("overlap_end"),
        "overlap_rows": audit.get("overlap_rows"),
        "status": "blocked" if exceeded_columns else "pass",
        "exceeded_columns": exceeded_columns,
        "trigger_critical_exceeded": trigger_critical_exceeded,
        "columns": columns,
        "source_diagnosis": {
            "panel_methods": _panel_method_differences(baseline, candidate),
            "model_sets": _model_set_differences(baseline_payload, candidate_payload),
            "run_context": _run_context_differences(baseline_payload, candidate_payload),
            "sensitivity_audit": {
                "status": "available" if sensitivity_payload else "not_provided",
                "path": str(_resolve(sensitivity_audit)) if sensitivity_audit else None,
                "column_summary": (sensitivity_payload or {}).get("column_summary", {}),
            },
        },
        "interpretation": {
            "promotion_allowed": False,
            "training_allowed": False,
            "target_weight_change_allowed": False,
            "reason": "trigger-critical drift exceeded"
            if trigger_critical_exceeded
            else "diagnostic drift exceeded"
            if exceeded_columns
            else "no configured drift limits exceeded",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drift-audit", required=True)
    parser.add_argument("--baseline-panel", default=None)
    parser.add_argument("--candidate-panel", default=None)
    parser.add_argument("--baseline-signal", default=None)
    parser.add_argument("--candidate-signal", default=None)
    parser.add_argument("--sensitivity-audit", default=None)
    parser.add_argument("--output", default="results/ncf_panel_drift_diagnosis_latest.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_diagnosis(
        args.drift_audit,
        baseline_panel=args.baseline_panel,
        candidate_panel=args.candidate_panel,
        baseline_signal=args.baseline_signal,
        candidate_signal=args.candidate_signal,
        sensitivity_audit=args.sensitivity_audit,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"NCF panel drift diagnosis: {output}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "exceeded_columns": report["exceeded_columns"],
                "trigger_critical_exceeded": report["trigger_critical_exceeded"],
                "promotion_allowed": report["interpretation"]["promotion_allowed"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
