"""Daily live shadow log for the spillover-gated recovery boost combination.

Fable audit (2026-07-16, combination opportunities #3/#4): the spillover gate
in evaluate_group_a_plus_recovery_boost_spillover_gate.py has never actually
fired in any tested historical window (spillover_blocked_recovery_days == 0
everywhere) because GroupA+'s "group_a_plus_recovery" regime is rare (32 days
across 7 windows spanning 2017-2026) and none of those recovery episodes
happened to coincide with a systemic spillover spike. The 2011-style "long
weak recovery that turns out to be a false dawn" scenario this gate is meant
to catch cannot be tested historically at all: the five-crisis proxy folds
(2008/2011/2015/2018) are close-only price series for only 4 tickers, and the
spillover network needs full OHLC across all 7 DEFAULT_TICKERS (three of
which -- 00646/00713/00878 -- did not exist as instruments in 2008/2011).

Rather than keep waiting on historical data that structurally does not exist,
this module builds one shadow-log row per day going forward: research-only,
pure logging, never touches target weights or execution guards. Once enough
real recovery-regime + spillover-stress coincidences accumulate live, they can
be joined against realized forward returns the same way
scripts/evaluate/evaluate_ncf_blend_live_auc_archive.py already does for NCF.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from group_a_plus.integrations.network_volatility_spillover_shadow import (
    DEFAULT_TICKERS,
    build_log_realized_variance_panel,
    build_spillover_network_frame,
    latest_spillover_snapshot,
    spillover_recovery_boost_gate,
)

SHADOW_LOG_SCHEMA_VERSION = 1
RECOVERY_REGIME_NAME = "group_a_plus_recovery"


def _recovery_age(execution_regime: pd.Series) -> int:
    """Consecutive trailing days execution_regime has been RECOVERY_REGIME_NAME."""
    age = 0
    for state in reversed(execution_regime.astype(str).tolist()):
        if state != RECOVERY_REGIME_NAME:
            break
        age += 1
    return age


def build_shadow_log_row(
    *,
    execution_regime: pd.Series,
    ohlcv: pd.DataFrame,
    max_age_days: int = 20,
    max_systemic_percentile: float = 0.80,
    max_target_in_percentile: float = 0.80,
    target: str = "0050.TW",
) -> dict[str, Any]:
    if execution_regime.empty:
        return {
            "schema_version": SHADOW_LOG_SCHEMA_VERSION,
            "status": "unavailable",
            "reason": "empty_execution_regime",
        }
    date = str(pd.Timestamp(execution_regime.index[-1]).date())
    current_regime = str(execution_regime.iloc[-1])
    in_recovery = current_regime == RECOVERY_REGIME_NAME
    age = _recovery_age(execution_regime)
    age_allowed = in_recovery and age <= int(max_age_days)

    log_rv = build_log_realized_variance_panel(ohlcv, tickers=DEFAULT_TICKERS)
    spillover_frame = build_spillover_network_frame(log_rv)
    snapshot = latest_spillover_snapshot(spillover_frame, target=target)
    gate = spillover_recovery_boost_gate(
        snapshot,
        max_systemic_percentile=max_systemic_percentile,
        max_target_in_percentile=max_target_in_percentile,
    )

    boost_allowed = bool(age_allowed and gate.get("allow_recovery_boost"))
    if not in_recovery:
        boost_reason = "not_in_recovery_regime"
    elif not age_allowed:
        boost_reason = "recovery_age_exceeds_max"
    elif not gate.get("allow_recovery_boost"):
        boost_reason = str(gate.get("reason", "spillover_blocked"))
    else:
        boost_reason = "allowed"

    return {
        "schema_version": SHADOW_LOG_SCHEMA_VERSION,
        "status": "available",
        "research_only": True,
        "production_effect": "none",
        "date": date,
        "execution_regime": current_regime,
        "in_recovery_regime": in_recovery,
        "recovery_age_days": age,
        "max_age_days": int(max_age_days),
        "age_allowed": age_allowed,
        "spillover_snapshot": snapshot,
        "spillover_gate": gate,
        "boost_allowed": boost_allowed,
        "boost_reason": boost_reason,
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
