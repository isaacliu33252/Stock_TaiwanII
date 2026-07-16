"""Daily live shadow log for the trough+compounding override eligibility union.

Fable audit (2026-07-16, combination opportunities #1) found that unioning
a2120's TREND_PERSISTENT compounding-regime signal into the trough-nowcast
vol-gate override's eligibility grew historical eligible events from 2 to
20-27 and, critically, grew the true out-of-sample window (2018_correction)
from 0 to 3 events -- all three individually positive. A follow-up sweep
(2026-07-16) found `override_fraction=0.50, confirmation_mode="none"` is the
best-supported combination: it keeps all 3 OOS events (the confirmation
filters cut that to 1), while the un-filtered 100% fraction has never seen a
negative event and so is not yet trustworthy at full size.

3 events is still too few to promote. This module logs one row per day going
forward -- research-only, pure logging -- so the out-of-sample sample grows
at live speed instead of waiting on more historical proxy data (which does
not exist for most crisis windows; see the spillover-gate shadow log's
docstring for the same constraint on a different signal).

It reuses simulate_override_policy exactly (same tested logic as
scripts/evaluate/evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py)
over a short recent window, so "today eligible" always means the same thing
the historical backtest measured -- not a re-derived, potentially-drifting
copy of the eligibility rule. Never changes target weights or execution
guards.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow import simulate_override_policy

SHADOW_LOG_SCHEMA_VERSION = 1
# Best-supported combination from the 2026-07-16 fraction/confirmation sweep
# (results/group_a_plus_trough_nowcast_vol_gate_override_shadow_fraction_confirmation_sweep_20260716.json):
# keeps all 3 OOS events; "none" confirmation is used because no_lower_low_3d
# cuts the OOS sample to 1 with no evidence yet that the extra filter helps.
DEFAULT_OVERRIDE_FRACTION = 0.50
DEFAULT_CONFIRMATION_MODE = "none"
DEFAULT_ELIGIBILITY_MODE = "trough_or_compounding_trend_persistent"


def build_shadow_log_row(
    *,
    prices: pd.DataFrame,
    frame: pd.DataFrame,
    trough_state: pd.DataFrame,
    gate_frame: pd.DataFrame,
    compounding_regime: pd.Series,
    report: dict[str, Any],
    initial_value: float = 1_000_000.0,
    override_fraction: float = DEFAULT_OVERRIDE_FRACTION,
    confirmation_mode: str = DEFAULT_CONFIRMATION_MODE,
    eligibility_mode: str = DEFAULT_ELIGIBILITY_MODE,
) -> dict[str, Any]:
    if prices.empty:
        return {
            "schema_version": SHADOW_LOG_SCHEMA_VERSION,
            "status": "unavailable",
            "reason": "empty_prices",
        }
    result = simulate_override_policy(
        prices=prices,
        frame=frame,
        trough_state=trough_state,
        gate_frame=gate_frame,
        report=report,
        initial_value=initial_value,
        override_fraction=override_fraction,
        confirmation_mode=confirmation_mode,
        eligibility_mode=eligibility_mode,
        compounding_regime=compounding_regime,
    )
    latest_dt = pd.Timestamp(prices.index[-1])
    today = str(latest_dt.date())
    todays_event = next((e for e in result["override_events"] if e["date"] == today), None)
    trough_today = str(trough_state["state"].reindex([latest_dt]).fillna("NO_TROUGH").iloc[0])
    compounding_today = str(compounding_regime.reindex([latest_dt]).fillna("UNAVAILABLE").iloc[0])

    return {
        "schema_version": SHADOW_LOG_SCHEMA_VERSION,
        "status": "available",
        "research_only": True,
        "production_effect": "none",
        "date": today,
        "eligible": todays_event is not None,
        "trigger_source": (todays_event or {}).get("trigger_source"),
        "trough_state": trough_today,
        "compounding_regime": compounding_today,
        "override_fraction": override_fraction,
        "confirmation_mode": confirmation_mode,
        "eligibility_mode": eligibility_mode,
        "attempted_00631l_buy_weight": (todays_event or {}).get("attempted_00631l_buy_weight"),
        "override_00631l_buy_weight": (todays_event or {}).get("override_00631l_buy_weight"),
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
