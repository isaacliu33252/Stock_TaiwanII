#!/usr/bin/env python3
"""Sweep cross-market graph daily NO_ADD thresholds and probability margins.

Research-only. This consumes the exported daily prediction frame and searches
for low-frequency advisory thresholds. It does not change live signals,
strategy manifests, or target weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_INPUT = Path("results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.csv")
DEFAULT_OUTPUT = Path("results/cross_market_graph_threshold_sweep_20260716.json")


def _safe_rate(num: int, den: int) -> float | None:
    return None if den == 0 else float(num / den)


def _metrics(frame: pd.DataFrame, signal: pd.Series) -> dict[str, Any]:
    pred = signal.reindex(frame.index).fillna(False).astype(bool)
    label = frame["label_NO_ADD"].astype(bool)
    tp = int((pred & label).sum())
    fp = int((pred & ~label).sum())
    tn = int((~pred & ~label).sum())
    fn = int((~pred & label).sum())
    return {
        "rows": int(len(frame)),
        "active_days": int(pred.sum()),
        "event_days": int(label.sum()),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": _safe_rate(tp, tp + fp),
        "recall": _safe_rate(tp, tp + fn),
        "false_positive_rate": _safe_rate(fp, fp + tn),
        "active_dates": [str(pd.Timestamp(dt).date()) for dt in frame.index[pred]],
    }


def _window_metrics(frame: pd.DataFrame, signal: pd.Series) -> dict[str, Any]:
    windows = {
        "2022_rate_hike": ("2022-01-03", "2022-10-31"),
        "2025_2026_full": ("2025-01-02", "2026-07-16"),
        "2026_q1q2": ("2026-02-01", "2026-04-30"),
        "2026_recent": ("2026-05-15", "2026-07-16"),
    }
    out: dict[str, Any] = {}
    for name, (start, end) in windows.items():
        part = frame.loc[pd.Timestamp(start) : pd.Timestamp(end)]
        out[name] = _metrics(part, signal.reindex(part.index)) if len(part) else {"rows": 0}
    return out


def build_sweep(input_path: Path) -> dict[str, Any]:
    frame = pd.read_csv(input_path, parse_dates=["date"]).set_index("date").sort_index()
    required = {"prob_NO_ADD", "prob_REENTER", "label_NO_ADD"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise RuntimeError(f"Input frame missing columns: {missing}")
    no_add = pd.to_numeric(frame["prob_NO_ADD"], errors="coerce")
    reenter = pd.to_numeric(frame["prob_REENTER"], errors="coerce")
    margin = no_add - reenter

    rows: list[dict[str, Any]] = []
    probability_thresholds = [0.55, 0.60, 0.65, 0.70, 0.75]
    margin_thresholds = [None, 0.00, 0.03, 0.05, 0.08, 0.10]
    max_active_days = [None, 5, 10, 20]
    for prob_threshold in probability_thresholds:
        for margin_threshold in margin_thresholds:
            base = no_add >= prob_threshold
            rule = f"prob_NO_ADD>={prob_threshold:.2f}"
            if margin_threshold is not None:
                base &= margin >= margin_threshold
                rule += f" and margin>={margin_threshold:.2f}"
            for max_days in max_active_days:
                signal = base.copy()
                final_rule = rule
                if max_days is not None and int(signal.sum()) <= max_days:
                    continue
                if max_days is not None and int(signal.sum()) > max_days:
                    top_idx = no_add[signal].sort_values(ascending=False).head(max_days).index
                    signal = signal & signal.index.isin(top_idx)
                    final_rule += f" top{max_days}_by_prob"
                summary = _metrics(frame, signal)
                if summary["active_days"] == 0:
                    continue
                row = {
                    "rule": final_rule,
                    "prob_threshold": prob_threshold,
                    "margin_threshold": margin_threshold,
                    "max_active_days": max_days,
                    **{k: v for k, v in summary.items() if k != "active_dates"},
                    "active_dates": summary["active_dates"],
                    "by_window": _window_metrics(frame, signal),
                }
                rows.append(row)

    ranked = sorted(
        rows,
        key=lambda row: (
            row["precision"] if row["precision"] is not None else -1.0,
            -(row["false_positive_rate"] if row["false_positive_rate"] is not None else 1.0),
            row["active_days"],
        ),
        reverse=True,
    )
    practical = [
        row
        for row in ranked
        if row["active_days"] >= 3
        and (row["precision"] or 0.0) >= 0.50
        and (row["false_positive_rate"] or 1.0) <= 0.02
    ]
    return {
        "report_type": "cross_market_graph_threshold_sweep",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_frame": str(input_path),
        "policy": "no_live_change",
        "rows": int(len(frame)),
        "window": {
            "start": str(frame.index.min().date()),
            "end": str(frame.index.max().date()),
        },
        "top10_by_precision": ranked[:10],
        "practical_candidates": practical[:10],
        "interpretation": (
            "A practical cross-market advisory threshold should be sparse, keep false positives low, "
            "and not rely only on 2022. Passing this sweep is necessary but not sufficient for live use."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report = build_sweep(Path(args.input))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    compact = {
        "top10": [
            {
                "rule": row["rule"],
                "active_days": row["active_days"],
                "precision": row["precision"],
                "recall": row["recall"],
                "fpr": row["false_positive_rate"],
            }
            for row in report["top10_by_precision"]
        ],
        "practical_candidates": [
            {
                "rule": row["rule"],
                "active_days": row["active_days"],
                "precision": row["precision"],
                "recall": row["recall"],
                "fpr": row["false_positive_rate"],
            }
            for row in report["practical_candidates"]
        ],
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
