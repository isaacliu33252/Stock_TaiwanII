"""Pure-logging daily accumulator for the adaptive review interval
mechanism (user proposal, 2026-08-09).

scripts/evaluate/evaluate_adaptive_review_interval_shadow.py's 7-window
backtest was a genuine, well-sampled mixed result (not promoted) -- but 3
of those 7 windows had zero suppressed days (trivial ties), so real
regime-transition-vs-review-interval evidence is thinner than 7 windows
suggests (see docs/ADAPTIVE_REVIEW_INTERVAL_GROUPA_PLUS_20260809.md). This
logs the causal classify_review_interval() decision every day at live
speed, accumulating real interval/label frequency data instead of only
relying on backtest windows. Never changes target weights, execution
guards, or the live signal -- purely observational.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

SHADOW_LOG_SCHEMA_VERSION = 1


def build_shadow_log_row(*, frame: pd.DataFrame, review_interval_days: int, review_interval_label: str) -> dict[str, Any]:
    if frame.empty:
        return {
            "schema_version": SHADOW_LOG_SCHEMA_VERSION,
            "status": "unavailable",
            "reason": "empty_frame",
        }
    row = frame.iloc[-1]
    dt = frame.index[-1]

    def _clean_float(value: Any) -> float | None:
        try:
            fvalue = float(value)
        except (TypeError, ValueError):
            return None
        return fvalue if fvalue == fvalue else None  # noqa: PLR0124 (drop NaN)

    return {
        "schema_version": SHADOW_LOG_SCHEMA_VERSION,
        "status": "available",
        "date": str(pd.Timestamp(dt).date()),
        "execution_regime": str(row.get("execution_regime")),
        "ma_gap": _clean_float(row.get("ma_gap")),
        "drawdown": _clean_float(row.get("drawdown")),
        "tail_risk_score": _clean_float(row.get("tail_risk_score")),
        "review_interval_days": review_interval_days,
        "review_interval_label": review_interval_label,
    }


def append_shadow_log_row(row: dict[str, Any], log_path: str | Path) -> bool:
    """Append row to a JSONL log, deduped by date. Returns True if appended."""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if row.get("status") != "available":
        return False
    existing_dates: set[str] = set()
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                existing_dates.add(json.loads(line).get("date"))
    if row.get("date") in existing_dates:
        return False
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return True
