#!/usr/bin/env python3
"""Scorecard for cross-market graph daily NO_ADD predictions.

Research-only. Consumes the daily prediction frame exported from
export_cross_market_graph_prediction_frame.py and evaluates whether
cross-market NO_ADD deserves to remain an independent advisory.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_INPUT = Path("results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.csv")
DEFAULT_OUTPUT = Path("results/cross_market_graph_daily_scorecard_20260716.json")

WINDOWS = {
    "2020_covid": ("2020-01-02", "2020-06-30"),
    "2022_rate_hike": ("2022-01-03", "2022-10-31"),
    "2025_2026_full": ("2025-01-02", "2026-07-16"),
    "2026_q1q2": ("2026-02-01", "2026-04-30"),
    "2026_recent": ("2026-05-15", "2026-07-16"),
}


def _safe_rate(num: int, den: int) -> float | None:
    return None if den == 0 else float(num / den)


def _summary(frame: pd.DataFrame, *, label_col: str = "label_NO_ADD") -> dict[str, Any]:
    if frame.empty:
        return {
            "rows": 0,
            "active_days": 0,
            "event_days": 0,
            "precision": None,
            "recall": None,
            "false_positive_rate": None,
        }
    pred = frame["no_add_active"].astype(bool)
    label = frame[label_col].astype(bool)
    tp = int((pred & label).sum())
    fp = int((pred & ~label).sum())
    tn = int((~pred & ~label).sum())
    fn = int((~pred & label).sum())
    return {
        "rows": int(len(frame)),
        "start": str(frame.index.min().date()),
        "end": str(frame.index.max().date()),
        "active_days": int(pred.sum()),
        "event_days": int(label.sum()),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": _safe_rate(tp, tp + fp),
        "recall": _safe_rate(tp, tp + fn),
        "false_positive_rate": _safe_rate(fp, fp + tn),
        "mean_prob_NO_ADD": float(frame["prob_NO_ADD"].mean()) if "prob_NO_ADD" in frame else None,
        "mean_prob_REENTER": float(frame["prob_REENTER"].mean()) if "prob_REENTER" in frame else None,
        "active_dates": [str(pd.Timestamp(dt).date()) for dt in frame.index[pred]],
    }


def build_scorecard(input_path: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    frame = pd.read_csv(input_path, parse_dates=["date"]).set_index("date").sort_index()
    if "no_add_active" not in frame or "label_NO_ADD" not in frame:
        raise RuntimeError("Input frame must include no_add_active and label_NO_ADD")
    frame["no_add_active"] = frame["no_add_active"].astype(bool)
    frame["year"] = frame.index.year.astype(int)

    yearly = {
        str(year): _summary(part.drop(columns=["year"], errors="ignore"))
        for year, part in frame.groupby("year", sort=True)
    }
    windows: dict[str, Any] = {}
    for name, (start, end) in WINDOWS.items():
        part = frame.loc[pd.Timestamp(start) : pd.Timestamp(end)]
        windows[name] = _summary(part.drop(columns=["year"], errors="ignore"))

    report = {
        "report_type": "cross_market_graph_daily_scorecard",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_frame": str(input_path),
        "policy": "advisory_only_no_weight_change",
        "overall": _summary(frame.drop(columns=["year"], errors="ignore")),
        "by_year": yearly,
        "by_window": windows,
        "interpretation": (
            "Cross-market graph daily NO_ADD should be treated as an independent advisory only "
            "if precision is stable across multiple windows. It should not suppress SRR-lite "
            "crash_watch_active unless overlap is validated separately."
        ),
    }
    return report, frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report, _frame = build_scorecard(Path(args.input))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    compact = {
        "overall": {
            key: report["overall"].get(key)
            for key in ("rows", "active_days", "precision", "recall", "false_positive_rate")
        },
        "by_window": {
            name: {
                key: summary.get(key)
                for key in ("rows", "active_days", "precision", "recall", "false_positive_rate")
            }
            for name, summary in report["by_window"].items()
        },
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
