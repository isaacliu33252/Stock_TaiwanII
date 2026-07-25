#!/usr/bin/env python3
"""Sweep strict systemic bubble confirmation variants against SRR labels.

Research-only. The sweep uses the already-built systemic bubble/SRR overlap
frame and searches for stricter combinations that reduce false positives. It
does not change live signals, target weights, or strategy manifests.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FRAME = PROJECT_ROOT / "report/group_a_plus/latest/systemic_bubble_srr_overlap_frame.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/systemic_bubble_param_sweep.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/systemic_bubble_param_sweep/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _safe_rate(num: int, den: int) -> float | None:
    return None if den == 0 else float(num / den)


def _safe_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _confusion(pred: pd.Series, label: pd.Series) -> dict[str, Any]:
    valid = pred.notna() & label.notna()
    p = pred[valid].astype(bool)
    y = label[valid].astype(bool)
    tp = int((p & y).sum())
    fp = int((p & ~y).sum())
    tn = int((~p & ~y).sum())
    fn = int((~p & y).sum())
    return {
        "rows": int(valid.sum()),
        "active_days": int(p.sum()),
        "event_days": int(y.sum()),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": _safe_rate(tp, tp + fp),
        "recall": _safe_rate(tp, tp + fn),
        "false_positive_rate": _safe_rate(fp, fp + tn),
    }


def _score_candidate(confusion: dict[str, Any], *, min_active_for_promotion: int) -> float:
    precision = confusion.get("precision") or 0.0
    recall = confusion.get("recall") or 0.0
    fpr = confusion.get("false_positive_rate") or 0.0
    active = int(confusion.get("active_days") or 0)
    sample_penalty = 0.25 if active < min_active_for_promotion else 0.0
    return float((2.0 * precision) + (0.25 * recall) - fpr - sample_penalty)


def _series_ge(frame: pd.DataFrame, column: str, threshold: float) -> pd.Series:
    return pd.to_numeric(frame[column], errors="coerce").ge(float(threshold)).fillna(False)


def _build_signal(frame: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
    time = (
        _series_ge(frame, "systemic_time_at_risk_days_60", params["time_days_min"])
        | _series_ge(frame, "systemic_00631l_vol20_percentile_252d", params["vol_pct_min"])
        | _series_ge(frame, "systemic_0050_ma120_gap", params["ma_gap_min"])
    )
    coupling = (
        _series_ge(frame, "systemic_etf_coupling_score", params["coupling_score_min"])
        | _series_ge(frame, "systemic_etf_coupling_percentile_252d", params["coupling_pct_min"])
    )
    reflexivity = (
        _series_ge(frame, "systemic_reflexivity_proxy_percentile_252d", params["reflexivity_pct_min"])
        | _series_ge(frame, "systemic_00631l_volume_z_60d", params["volume_z_min"])
        | _series_ge(frame, "systemic_00631l_abs_return_z_60d", params["absret_z_min"])
    )
    family = str(params["family"])
    if family == "time_and_coupling":
        return time & coupling
    if family == "time_and_reflexivity":
        return time & reflexivity
    if family == "coupling_and_reflexivity":
        return coupling & reflexivity
    if family == "two_of_three":
        return ((time.astype(int) + coupling.astype(int) + reflexivity.astype(int)) >= 2).fillna(False)
    if family == "three_of_three":
        return time & coupling & reflexivity
    raise ValueError(f"Unknown family: {family}")


def _read_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    frame.index = pd.to_datetime(frame.index).normalize()
    return frame


def run_sweep(
    frame_path: Path = DEFAULT_FRAME,
    *,
    as_of: str | None = "2026-07-20",
    min_active_for_promotion: int = 20,
) -> dict[str, Any]:
    frame = _read_frame(frame_path)
    label = frame["no_add_label_h10"].astype(bool)
    srr_confusion = _confusion(frame["srr_no_add_active"].astype(bool), label)
    candidates: list[dict[str, Any]] = []

    def add_candidate(params: dict[str, Any], signal: pd.Series) -> None:
        confusion = _confusion(signal.fillna(False).astype(bool), label)
        if int(confusion["active_days"]) == 0:
            return
        candidates.append(
            {
                "params": params,
                "h10_confusion": confusion,
                "objective": _score_candidate(
                    confusion,
                    min_active_for_promotion=min_active_for_promotion,
                ),
                "sample_ready": int(confusion["active_days"]) >= min_active_for_promotion,
            }
        )

    families = ["time_and_coupling", "time_and_reflexivity", "coupling_and_reflexivity", "two_of_three", "three_of_three"]
    time_days_grid = [10, 20, 30]
    vol_pct_grid = [0.80, 0.90]
    ma_gap_grid = [0.08, 0.10]
    coupling_score_grid = [0.70, 0.75]
    coupling_pct_grid = [0.80, 0.90]
    reflexivity_pct_grid = [0.80, 0.90]
    z_grid = [2.0, 2.5]

    for family in families:
        for time_days_min in time_days_grid:
            for vol_pct_min in vol_pct_grid:
                for ma_gap_min in ma_gap_grid:
                    for coupling_score_min in coupling_score_grid:
                        for coupling_pct_min in coupling_pct_grid:
                            for reflexivity_pct_min in reflexivity_pct_grid:
                                for volume_z_min in z_grid:
                                    for absret_z_min in z_grid:
                                        params = {
                                            "family": family,
                                            "time_days_min": time_days_min,
                                            "vol_pct_min": vol_pct_min,
                                            "ma_gap_min": ma_gap_min,
                                            "coupling_score_min": coupling_score_min,
                                            "coupling_pct_min": coupling_pct_min,
                                            "reflexivity_pct_min": reflexivity_pct_min,
                                            "volume_z_min": volume_z_min,
                                            "absret_z_min": absret_z_min,
                                        }
                                        add_candidate(params, _build_signal(frame, params))

    fixed_columns = [
        "systemic_time_watch_and_coupling_elevated",
        "systemic_time_watch_and_reflexivity_elevated",
        "srr_confirmed_by_systemic_blocked",
        "intersection_srr_and_systemic_watch",
    ]
    for column in fixed_columns:
        if column in frame:
            add_candidate(
                {
                    "family": f"fixed:{column}",
                    "source_column": column,
                },
                frame[column],
            )

    candidates = sorted(
        candidates,
        key=lambda item: (
            item["objective"],
            item["h10_confusion"].get("precision") or 0.0,
            -(item["h10_confusion"].get("false_positive_rate") or 0.0),
            item["h10_confusion"].get("active_days") or 0,
        ),
        reverse=True,
    )
    best = candidates[0] if candidates else None
    best_precision = (
        sorted(
            candidates,
            key=lambda item: (
                item["h10_confusion"].get("precision") or 0.0,
                -(item["h10_confusion"].get("false_positive_rate") or 1.0),
                item["h10_confusion"].get("active_days") or 0,
            ),
            reverse=True,
        )[0]
        if candidates
        else None
    )
    best_sample_ready = next((item for item in candidates if item["sample_ready"]), None)
    blockers = [
        "systemic_bubble_param_sweep_research_only",
        "no_live_weight_change_allowed",
    ]
    if best is None:
        blockers.append("no_valid_candidate")
    elif not best["sample_ready"]:
        blockers.append("best_candidate_sample_too_small")
    if best_sample_ready is None:
        blockers.append("no_sample_ready_candidate")
    elif (best_sample_ready["h10_confusion"].get("precision") or 0.0) <= (srr_confusion.get("precision") or 0.0):
        blockers.append("sample_ready_candidate_precision_not_above_srr")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_systemic_bubble_param_sweep",
        "status": "blocked",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "input_frame": str(frame_path),
        "window": {
            "start": str(frame.index.min().date()),
            "end": str(frame.index.max().date()),
            "rows": int(len(frame)),
        },
        "policy": "research_only_systemic_bubble_param_sweep_no_weight_change",
        "srr_h10_confusion": srr_confusion,
        "min_active_for_promotion": int(min_active_for_promotion),
        "candidate_count": int(len(candidates)),
        "best_candidate": best,
        "best_precision_candidate": best_precision,
        "best_sample_ready_candidate": best_sample_ready,
        "top_candidates": candidates[:20],
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "incremental_signal_promotable": False,
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"systemic_bubble_param_sweep_{stamp}.json"


def write_sweep(payload: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, payload.get("as_of")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", default=str(DEFAULT_FRAME))
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--min-active-for-promotion", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = run_sweep(
        _resolve(args.frame),
        as_of=args.as_of,
        min_active_for_promotion=args.min_active_for_promotion,
    )
    write_sweep(payload, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    best = payload.get("best_candidate") or {}
    best_precision = payload.get("best_precision_candidate") or {}
    best_ready = payload.get("best_sample_ready_candidate") or {}
    compact = {
        "status": payload["status"],
        "candidate_count": payload["candidate_count"],
        "best_active_days": (best.get("h10_confusion") or {}).get("active_days"),
        "best_precision": (best.get("h10_confusion") or {}).get("precision"),
        "best_fpr": (best.get("h10_confusion") or {}).get("false_positive_rate"),
        "best_precision_active_days": (best_precision.get("h10_confusion") or {}).get("active_days"),
        "best_precision_precision": (best_precision.get("h10_confusion") or {}).get("precision"),
        "best_precision_fpr": (best_precision.get("h10_confusion") or {}).get("false_positive_rate"),
        "best_sample_ready_active_days": (best_ready.get("h10_confusion") or {}).get("active_days"),
        "best_sample_ready_precision": (best_ready.get("h10_confusion") or {}).get("precision"),
        "promotion_allowed": payload["decision"]["promotion_allowed"],
    }
    print(f"Systemic bubble parameter sweep: {_resolve(args.output)}")
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
