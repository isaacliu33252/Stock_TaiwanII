#!/usr/bin/env python3
"""Evaluate QGMS-lite overlap with SRR-lite shadow no-add signals.

Research-only. This script reads already generated daily frames and compares
same-day unions/intersections. It does not retrain thresholds and does not
change live signals, target weights, or strategy manifests.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRR_FRAME = PROJECT_ROOT / "results" / "srr_lite_shadow_backtest_20250102_20260716_tuned_frame.csv"
DEFAULT_QGMS_FRAME = PROJECT_ROOT / "results" / "qgms_lite_structural_endpoint_shadow_20250102_20260716_frame.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "qgms_srr_overlap_shadow_20250102_20260716.json"
SRR_CRASH_WATCH_SCORE_THRESHOLD = 0.75
SRR_CRASH_WATCH_DENSITY_THRESHOLD = 0.65


def _safe_rate(num: int, den: int) -> float | None:
    return None if den == 0 else float(num / den)


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


def _read_frame(path: Path, prefix: str) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    frame.index = pd.to_datetime(frame.index).normalize()
    return frame.add_prefix(prefix)


def _score_forward_summary(frame: pd.DataFrame, active: pd.Series, horizon: int) -> dict[str, Any]:
    active = active.reindex(frame.index).fillna(False).astype(bool)
    ret_col = f"srr_forward_ret_00631l_h{horizon}"
    rel_col = f"srr_forward_rel_00631l_vs_0050_h{horizon}"
    mdd_col = f"srr_forward_mdd_00631l_h{horizon}"
    label_col = f"srr_no_add_label_h{horizon}"
    return {
        "horizon_days": horizon,
        "confusion": _confusion(active, frame[label_col]),
        "active_mean_forward_ret_00631l": float(frame.loc[active, ret_col].mean()) if active.any() else None,
        "inactive_mean_forward_ret_00631l": float(frame.loc[~active, ret_col].mean()) if (~active).any() else None,
        "active_mean_relative_vs_0050": float(frame.loc[active, rel_col].mean()) if active.any() else None,
        "inactive_mean_relative_vs_0050": float(frame.loc[~active, rel_col].mean()) if (~active).any() else None,
        "active_mean_forward_mdd_00631l": float(frame.loc[active, mdd_col].mean()) if active.any() else None,
        "inactive_mean_forward_mdd_00631l": float(frame.loc[~active, mdd_col].mean()) if (~active).any() else None,
    }


def _summarize_signal(frame: pd.DataFrame, signal: pd.Series) -> dict[str, Any]:
    signal = signal.reindex(frame.index).fillna(False).astype(bool)
    return {
        "active_days": int(signal.sum()),
        "active_dates": [str(pd.Timestamp(dt).date()) for dt in frame.index[signal]],
        "h5": _score_forward_summary(frame, signal, 5),
        "h10": _score_forward_summary(frame, signal, 10),
    }


def build_overlap_report(
    *,
    srr_frame_path: Path,
    qgms_frame_path: Path,
) -> tuple[dict[str, Any], pd.DataFrame]:
    srr = _read_frame(srr_frame_path, "srr_")
    qgms = _read_frame(qgms_frame_path, "qgms_")
    frame = srr.join(qgms, how="inner")
    if frame.empty:
        raise RuntimeError("SRR and QGMS frames have no overlapping dates")

    srr_no_add = frame["srr_no_add_active"].fillna(False).astype(bool)
    if "srr_crash_watch_active" in frame:
        srr_crash_watch = frame["srr_crash_watch_active"].fillna(False).astype(bool)
        crash_watch_source = "input_column"
    else:
        srr_crash_watch = (
            (pd.to_numeric(frame["srr_systemic_fragility_score"], errors="coerce") >= SRR_CRASH_WATCH_SCORE_THRESHOLD)
            & (pd.to_numeric(frame["srr_graph_density"], errors="coerce") >= SRR_CRASH_WATCH_DENSITY_THRESHOLD)
        ).fillna(False)
        crash_watch_source = "reconstructed_from_score_and_density"
    qgms_endpoint = frame["qgms_endpoint_watch_active"].fillna(False).astype(bool)
    qgms_strong = frame["qgms_strong_endpoint_active"].fillna(False).astype(bool)

    signals = {
        "srr_no_add_active": srr_no_add,
        "srr_crash_watch_active": srr_crash_watch,
        "qgms_endpoint_watch_active": qgms_endpoint,
        "qgms_strong_endpoint_active": qgms_strong,
        "union_srr_no_add_or_qgms_endpoint": srr_no_add | qgms_endpoint,
        "union_srr_crash_or_qgms_endpoint": srr_crash_watch | qgms_endpoint,
        "intersection_srr_no_add_and_qgms_endpoint": srr_no_add & qgms_endpoint,
        "intersection_srr_crash_and_qgms_endpoint": srr_crash_watch & qgms_endpoint,
        "qgms_endpoint_without_srr_no_add": qgms_endpoint & ~srr_no_add,
        "qgms_endpoint_without_srr_crash": qgms_endpoint & ~srr_crash_watch,
        "srr_no_add_without_qgms_endpoint": srr_no_add & ~qgms_endpoint,
        "srr_crash_without_qgms_endpoint": srr_crash_watch & ~qgms_endpoint,
    }

    for name, signal in signals.items():
        frame[name] = signal.reindex(frame.index).fillna(False).astype(bool)

    summary = {name: _summarize_signal(frame, signal) for name, signal in signals.items()}
    report = {
        "report_type": "qgms_srr_overlap_shadow",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "window": {
            "start": str(frame.index.min().date()),
            "end": str(frame.index.max().date()),
            "rows": int(len(frame)),
        },
        "inputs": {
            "srr_frame": str(srr_frame_path),
            "qgms_frame": str(qgms_frame_path),
            "srr_crash_watch_source": crash_watch_source,
        },
        "policy": "shadow_only_no_weight_change",
        "summary": summary,
        "interpretation": (
            "Use this only to assess incremental information. A useful QGMS add-on should improve "
            "precision or add high-quality dates that SRR-lite missed without materially increasing "
            "false positives. This report does not promote QGMS-lite to live execution."
        ),
    }
    return report, frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--srr-frame", default=str(DEFAULT_SRR_FRAME))
    parser.add_argument("--qgms-frame", default=str(DEFAULT_QGMS_FRAME))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report, frame = build_overlap_report(
        srr_frame_path=Path(args.srr_frame),
        qgms_frame_path=Path(args.qgms_frame),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame_output = output.with_name(output.stem + "_frame.csv")
    frame.to_csv(frame_output, encoding="utf-8-sig")
    report["frame_output"] = str(frame_output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compact = {
        key: {
            "active_days": value["active_days"],
            "h10_precision": value["h10"]["confusion"]["precision"],
            "h10_recall": value["h10"]["confusion"]["recall"],
            "h10_fpr": value["h10"]["confusion"]["false_positive_rate"],
        }
        for key, value in report["summary"].items()
    }
    print(f"Saved: {output}")
    print(f"Frame: {frame_output}")
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
