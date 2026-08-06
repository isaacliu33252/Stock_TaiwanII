#!/usr/bin/env python3
"""Evaluate diagnostic thresholds for the 0050 NCF validation panel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PANEL = PROJECT_ROOT / "results" / "ncf_0050_panel_latest_20260803.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "ncf_0050_threshold_eval_20260803.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "results" / "ncf_0050_threshold_eval_20260803.md"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _float_or_none(value: Any) -> float | None:
    if pd.isna(value):
        return None
    return float(value)


def _metric_pair(frame: pd.DataFrame, prob_col: str, actual_col: str) -> dict[str, Any]:
    resolved = frame[[prob_col, actual_col]].dropna()
    if resolved.empty:
        return {"resolved_rows": 0, "auc": None, "brier": None, "positive_rate": None}
    y = resolved[actual_col].astype(int)
    p = resolved[prob_col].astype(float).clip(0.0, 1.0)
    auc = None
    if y.nunique() == 2:
        auc = float(roc_auc_score(y, p))
    return {
        "resolved_rows": int(len(resolved)),
        "auc": auc,
        "brier": float(brier_score_loss(y, p)),
        "positive_rate": float(y.mean()),
    }


def _threshold_row(frame: pd.DataFrame, *, h20_max: float, confidence_min: float) -> dict[str, Any]:
    required = [
        "prob_up_h20",
        "confidence",
        "actual_up_h20",
        "actual_fwd_mdd_gt5_h20",
        "actual_fwd_gain_gt5_h20",
        "forward_mdd_h20",
        "forward_gain_h20",
    ]
    resolved = frame.dropna(subset=[col for col in required if col in frame.columns])
    active = (resolved["prob_up_h20"].astype(float) <= h20_max) & (
        resolved["confidence"].astype(float) >= confidence_min
    )
    active_rows = resolved.loc[active]
    inactive_rows = resolved.loc[~active]

    active_gain = active_rows["forward_gain_h20"].mean() if len(active_rows) else pd.NA
    inactive_gain = inactive_rows["forward_gain_h20"].mean() if len(inactive_rows) else pd.NA
    active_mdd = active_rows["forward_mdd_h20"].mean() if len(active_rows) else pd.NA
    inactive_mdd = inactive_rows["forward_mdd_h20"].mean() if len(inactive_rows) else pd.NA
    active_up_rate = active_rows["actual_up_h20"].mean() if len(active_rows) else pd.NA
    inactive_up_rate = inactive_rows["actual_up_h20"].mean() if len(inactive_rows) else pd.NA
    active_mdd_rate = active_rows["actual_fwd_mdd_gt5_h20"].mean() if len(active_rows) else pd.NA
    inactive_mdd_rate = inactive_rows["actual_fwd_mdd_gt5_h20"].mean() if len(inactive_rows) else pd.NA
    active_gain_rate = active_rows["actual_fwd_gain_gt5_h20"].mean() if len(active_rows) else pd.NA
    inactive_gain_rate = inactive_rows["actual_fwd_gain_gt5_h20"].mean() if len(inactive_rows) else pd.NA

    score = None
    if len(active_rows) and len(inactive_rows):
        # Positive means the active warning bucket has worse reward and more drawdown events.
        score = float(
            (float(inactive_gain) - float(active_gain))
            + 0.02 * (float(active_mdd_rate) - float(inactive_mdd_rate))
        )

    return {
        "h20_prob_up_max": h20_max,
        "confidence_min": confidence_min,
        "resolved_rows": int(len(resolved)),
        "active_rows": int(len(active_rows)),
        "active_rate": float(active.mean()) if len(resolved) else None,
        "active_mean_forward_gain_h20": _float_or_none(active_gain),
        "inactive_mean_forward_gain_h20": _float_or_none(inactive_gain),
        "active_mean_forward_mdd_h20": _float_or_none(active_mdd),
        "inactive_mean_forward_mdd_h20": _float_or_none(inactive_mdd),
        "active_actual_up_rate_h20": _float_or_none(active_up_rate),
        "inactive_actual_up_rate_h20": _float_or_none(inactive_up_rate),
        "active_mdd_gt5_rate_h20": _float_or_none(active_mdd_rate),
        "inactive_mdd_gt5_rate_h20": _float_or_none(inactive_mdd_rate),
        "active_gain_gt5_rate_h20": _float_or_none(active_gain_rate),
        "inactive_gain_gt5_rate_h20": _float_or_none(inactive_gain_rate),
        "separation_score": score,
    }


def evaluate_thresholds(
    panel_path: str | Path,
    *,
    h20_thresholds: list[float],
    confidence_thresholds: list[float],
    min_active_rows: int = 20,
) -> dict[str, Any]:
    path = _resolve(panel_path)
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "date" not in frame.columns:
        raise ValueError(f"{path} is missing required date column")
    frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")

    metrics = {
        "h1_direction": _metric_pair(frame, "prob_up_h1", "actual_up_h1"),
        "h5_direction": _metric_pair(frame, "prob_up_h5", "actual_up_h5"),
        "h20_direction": _metric_pair(frame, "prob_up_h20", "actual_up_h20"),
        "h20_mdd_gt5": _metric_pair(frame, "prob_fwd_mdd_gt5_h20", "actual_fwd_mdd_gt5_h20"),
        "h20_gain_gt5": _metric_pair(frame, "prob_fwd_gain_gt5_h20", "actual_fwd_gain_gt5_h20"),
    }

    rows = [
        _threshold_row(frame, h20_max=h20, confidence_min=conf)
        for h20 in h20_thresholds
        for conf in confidence_thresholds
    ]
    eligible = [
        row for row in rows
        if row["active_rows"] >= min_active_rows and row["separation_score"] is not None
    ]
    eligible.sort(key=lambda row: row["separation_score"], reverse=True)
    recommendation = {
        "status": "candidate_found" if eligible else "insufficient_events",
        "trade_policy": "diagnostic_only_no_weight_change",
        "recommended_use": "block_new_0050_add_shadow_only",
        "min_active_rows": min_active_rows,
        "candidate": eligible[0] if eligible else None,
        "rationale": (
            "Use as a warning gate only when the active bucket has enough samples "
            "and shows lower forward gain plus higher drawdown-event rate."
        ),
    }
    return {
        "report_type": "ncf_0050_panel_threshold_evaluation",
        "panel": str(path),
        "rows": int(len(frame)),
        "date_start": str(frame["date"].min()),
        "date_end": str(frame["date"].max()),
        "live_rows": int(frame.get("is_live", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()),
        "metrics": metrics,
        "threshold_sweep": rows,
        "recommendation": recommendation,
    }


def write_markdown(report: dict[str, Any], path: str | Path) -> None:
    out = _resolve(path)
    rec = report["recommendation"]
    lines = [
        "# NCF 0050 Threshold Evaluation",
        "",
        f"- panel: `{report['panel']}`",
        f"- rows: `{report['rows']}`",
        f"- range: `{report['date_start']}` to `{report['date_end']}`",
        f"- trade policy: `{rec['trade_policy']}`",
        f"- recommended use: `{rec['recommended_use']}`",
        "",
        "## Direction Metrics",
        "",
    ]
    for name, metrics in report["metrics"].items():
        lines.append(
            f"- `{name}`: rows={metrics['resolved_rows']} "
            f"auc={metrics['auc']} brier={metrics['brier']} positive_rate={metrics['positive_rate']}"
        )
    lines.extend(["", "## Candidate", ""])
    lines.append("```json")
    lines.append(json.dumps(rec["candidate"], ensure_ascii=False, indent=2))
    lines.append("```")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--h20-thresholds", default="0.30,0.35,0.40,0.45")
    parser.add_argument("--confidence-thresholds", default="0.00,0.10,0.12,0.20,0.30")
    parser.add_argument("--min-active-rows", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    h20_thresholds = [float(x) for x in args.h20_thresholds.split(",") if x.strip()]
    confidence_thresholds = [float(x) for x in args.confidence_thresholds.split(",") if x.strip()]
    report = evaluate_thresholds(
        args.panel,
        h20_thresholds=h20_thresholds,
        confidence_thresholds=confidence_thresholds,
        min_active_rows=args.min_active_rows,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, args.output_md)
    print(f"Saved: {output}")
    print(f"Saved: {_resolve(args.output_md)}")


if __name__ == "__main__":
    main()
