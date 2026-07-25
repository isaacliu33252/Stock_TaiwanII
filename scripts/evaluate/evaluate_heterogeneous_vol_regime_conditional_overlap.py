#!/usr/bin/env python3
"""Conditional overlap review for heterogeneous vol-regime shadow signals.

Research-only. Compares 2603.16035-inspired heterogeneous volatility signals
with existing SRR-lite and QGMS-lite frames, and sweeps simple source-count
thresholds. It does not change live signals or target weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HETERO_FRAME = PROJECT_ROOT / "results" / "heterogeneous_vol_regime_shadow_20250102_20260717_frame.csv"
DEFAULT_SRR_FRAME = PROJECT_ROOT / "results" / "srr_lite_shadow_backtest_20250102_20260716_tuned_frame.csv"
DEFAULT_QGMS_FRAME = PROJECT_ROOT / "results" / "qgms_lite_structural_endpoint_shadow_20250102_20260716_frame.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "heterogeneous_vol_regime_conditional_overlap_20250102_20260717.json"


def _safe_rate(num: int, den: int) -> float | None:
    return None if den == 0 else float(num / den)


def _confusion(pred: pd.Series, label: pd.Series) -> dict[str, Any]:
    valid = pred.notna() & label.notna()
    p = pred[valid].fillna(False).astype(bool)
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


def _read_frame(path: Path, prefix: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    date_col = "date" if "date" in frame.columns else "dt" if "dt" in frame.columns else frame.columns[0]
    frame[date_col] = pd.to_datetime(frame[date_col]).dt.normalize()
    frame = frame.set_index(date_col).sort_index()
    return frame.add_prefix(prefix)


def _score_forward_summary(frame: pd.DataFrame, signal: pd.Series, horizon: int) -> dict[str, Any]:
    signal = signal.reindex(frame.index).fillna(False).astype(bool)
    return {
        "horizon_days": int(horizon),
        "confusion": _confusion(signal, frame[f"hetero_no_add_label_h{horizon}"]),
        "active_mean_forward_ret_00631l": (
            float(frame.loc[signal, f"hetero_forward_ret_00631l_h{horizon}"].mean()) if signal.any() else None
        ),
        "active_mean_relative_vs_0050": (
            float(frame.loc[signal, f"hetero_forward_rel_00631l_vs_0050_h{horizon}"].mean()) if signal.any() else None
        ),
        "active_mean_forward_mdd_00631l": (
            float(frame.loc[signal, f"hetero_forward_mdd_00631l_h{horizon}"].mean()) if signal.any() else None
        ),
    }


def _summarize_signal(frame: pd.DataFrame, signal: pd.Series) -> dict[str, Any]:
    signal = signal.reindex(frame.index).fillna(False).astype(bool)
    return {
        "active_days": int(signal.sum()),
        "active_dates": [str(pd.Timestamp(dt).date()) for dt in frame.index[signal]],
        "h5": _score_forward_summary(frame, signal, 5),
        "h10": _score_forward_summary(frame, signal, 10),
    }


def _compact(summary: dict[str, Any]) -> dict[str, Any]:
    h10 = summary["h10"]["confusion"]
    return {
        "active_days": summary["active_days"],
        "h10_precision": h10["precision"],
        "h10_recall": h10["recall"],
        "h10_fpr": h10["false_positive_rate"],
    }


def _signal_sweep(frame: pd.DataFrame) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    label = frame["hetero_no_add_label_h10"]
    for stress_min in range(1, 9):
        signal = frame["hetero_verified_stress_count"].fillna(0).astype(int) >= stress_min
        c = _confusion(signal, label)
        rows.append(
            {
                "signal": f"verified_stress_count_ge_{stress_min}",
                "threshold": stress_min,
                "active_days": c["active_days"],
                "precision": c["precision"],
                "recall": c["recall"],
                "false_positive_rate": c["false_positive_rate"],
            }
        )
    for crisis_min in range(1, 9):
        signal = frame["hetero_verified_crisis_count"].fillna(0).astype(int) >= crisis_min
        c = _confusion(signal, label)
        rows.append(
            {
                "signal": f"verified_crisis_count_ge_{crisis_min}",
                "threshold": crisis_min,
                "active_days": c["active_days"],
                "precision": c["precision"],
                "recall": c["recall"],
                "false_positive_rate": c["false_positive_rate"],
            }
        )
    eligible = [
        row
        for row in rows
        if row["active_days"] >= 5
        and row["precision"] is not None
        and row["false_positive_rate"] is not None
        and row["false_positive_rate"] <= 0.20
    ]
    eligible = sorted(eligible, key=lambda r: (r["precision"], -r["false_positive_rate"], r["recall"] or 0), reverse=True)
    return {"rows": rows, "best_low_fpr": eligible[:10]}


def build_report(
    *,
    hetero_frame_path: Path,
    srr_frame_path: Path,
    qgms_frame_path: Path,
) -> tuple[dict[str, Any], pd.DataFrame]:
    hetero = _read_frame(hetero_frame_path, "hetero_")
    srr = _read_frame(srr_frame_path, "srr_")
    qgms = _read_frame(qgms_frame_path, "qgms_")
    frame = hetero.join(srr, how="left").join(qgms, how="left")
    frame = frame.dropna(subset=["hetero_no_add_label_h10"]).copy()
    if frame.empty:
        raise RuntimeError("No usable heterogeneous volatility rows")

    signals = {
        "heterogeneous_stress_active": frame["hetero_heterogeneous_stress_active"].fillna(False).astype(bool),
        "sparse_crisis_active": frame["hetero_sparse_crisis_active"].fillna(False).astype(bool),
        "local_levered_stress_active": frame["hetero_local_levered_stress_active"].fillna(False).astype(bool),
        "srr_no_add_active": frame["srr_no_add_active"].fillna(False).astype(bool),
        "qgms_endpoint_watch_active": frame["qgms_endpoint_watch_active"].fillna(False).astype(bool),
    }
    signals.update(
        {
            "hetero_sparse_and_srr_no_add": signals["sparse_crisis_active"] & signals["srr_no_add_active"],
            "hetero_sparse_or_srr_no_add": signals["sparse_crisis_active"] | signals["srr_no_add_active"],
            "hetero_sparse_and_qgms_endpoint": signals["sparse_crisis_active"] & signals["qgms_endpoint_watch_active"],
            "hetero_sparse_or_qgms_endpoint": signals["sparse_crisis_active"] | signals["qgms_endpoint_watch_active"],
            "hetero_sparse_and_srr_or_qgms": signals["sparse_crisis_active"]
            & (signals["srr_no_add_active"] | signals["qgms_endpoint_watch_active"]),
            "srr_or_qgms_without_hetero_sparse": (signals["srr_no_add_active"] | signals["qgms_endpoint_watch_active"])
            & ~signals["sparse_crisis_active"],
        }
    )

    for name, signal in signals.items():
        frame[name] = signal.reindex(frame.index).fillna(False).astype(bool)
    summary = {name: _summarize_signal(frame, signal) for name, signal in signals.items()}
    sweep = _signal_sweep(frame)
    low_fpr_candidates = {
        name: _compact(value)
        for name, value in summary.items()
        if value["active_days"] >= 5
        and _compact(value)["h10_fpr"] is not None
        and _compact(value)["h10_fpr"] <= 0.20
    }

    report = {
        "report_type": "heterogeneous_vol_regime_conditional_overlap",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_weight_change",
        "window": {
            "start": str(frame.index.min().date()),
            "end": str(frame.index.max().date()),
            "rows": int(len(frame)),
        },
        "inputs": {
            "hetero_frame": str(hetero_frame_path),
            "srr_frame": str(srr_frame_path),
            "qgms_frame": str(qgms_frame_path),
        },
        "summary": summary,
        "threshold_sweep": sweep,
        "low_fpr_candidates": low_fpr_candidates,
        "promotion_decision": "research_only",
        "interpretation": (
            "Conditional overlap review. Low-FPR candidates are for manual review only; "
            "they do not promote heterogeneous volatility regimes to live execution."
        ),
    }
    return report, frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hetero-frame", default=str(DEFAULT_HETERO_FRAME))
    parser.add_argument("--srr-frame", default=str(DEFAULT_SRR_FRAME))
    parser.add_argument("--qgms-frame", default=str(DEFAULT_QGMS_FRAME))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report, frame = build_report(
        hetero_frame_path=Path(args.hetero_frame),
        srr_frame_path=Path(args.srr_frame),
        qgms_frame_path=Path(args.qgms_frame),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame_output = output.with_name(output.stem + "_frame.csv")
    frame.to_csv(frame_output, encoding="utf-8-sig")
    report["frame_output"] = str(frame_output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compact = {name: _compact(value) for name, value in report["summary"].items()}
    print(f"Saved: {output}")
    print(f"Frame: {frame_output}")
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    print("Low-FPR candidates:")
    print(json.dumps(report["low_fpr_candidates"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
