"""Pure-logging daily accumulator for the ADD_0050_INSTEAD TSMC
concentration-divergence guard (user proposal, 2026-08-09).

scripts/evaluate/evaluate_add_0050_instead_of_00631l_shadow.py's 7/7-window
backtest passed but only found 3 trigger events across 6+ years of history
-- too sparse to validate the guard either way
(see docs/TSMC_CONCENTRATION_DIVERGENCE_GROUPA_PLUS_20260809.md). This
accumulates real daily observations at live speed instead of waiting on
more backfill data that does not exist. Never changes target weights,
execution guards, or the live signal -- purely observational.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

SHADOW_LOG_SCHEMA_VERSION = 1


def build_shadow_log_row(*, target_weights: pd.DataFrame, narrow_lead: pd.Series) -> dict[str, Any]:
    if target_weights.empty or "00631L.TW" not in target_weights.columns or len(target_weights) < 2:
        return {
            "schema_version": SHADOW_LOG_SCHEMA_VERSION,
            "status": "unavailable",
            "reason": "insufficient_target_weight_history",
        }
    dt = target_weights.index[-1]
    date = str(pd.Timestamp(dt).date())
    current_631l = float(target_weights["00631L.TW"].iloc[-1])
    prev_631l = float(target_weights["00631L.TW"].iloc[-2])
    is_narrow = bool(narrow_lead.get(dt, False))
    increasing = current_631l > prev_631l
    would_trigger = bool(is_narrow and increasing)
    return {
        "schema_version": SHADOW_LOG_SCHEMA_VERSION,
        "status": "available",
        "date": date,
        "narrow_lead": is_narrow,
        "00631l_target_weight": round(current_631l, 6),
        "00631l_target_weight_prev": round(prev_631l, 6),
        "00631l_target_weight_increasing": increasing,
        "would_trigger_add_0050_instead": would_trigger,
        "would_be_redirect_amount": round(current_631l - prev_631l, 6) if would_trigger else 0.0,
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
