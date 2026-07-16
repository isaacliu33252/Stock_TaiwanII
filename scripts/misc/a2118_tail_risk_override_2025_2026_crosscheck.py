#!/usr/bin/env python3
"""Cross-check for a2118_override_risk_2008_proxy_test.py: the tail_risk_score
-based override (bypass ALL entry gates, not just MA-gap, when tail_risk_score
>= threshold and drawdown <= threshold) found a genuine improvement in the
2008 TWII proxy crash (both final value and max_drawdown improved with just
3 extra earlier-entry days, at tail_risk_score>=1 & drawdown<=-0.08/-0.10).
Before treating that as informative, it must be checked against real
2025-2026 data: does the same mechanism cost anything (whipsaw, false
triggers) during the actual bull-skewed sample a2118 runs on live?

Read-only with respect to production strategy code: monkeypatches
`_switch_returns` inside `group_a_plus.runners.a2118`'s own namespace for the
duration of each run (restored after), never edits any file on disk. Writes
one JSON report to results/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import group_a_plus.runners.a2118 as a2118_module  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _regime_features, _switch_returns  # noqa: E402

START = "2025-01-02"
END = "2026-07-03"
INITIAL_VALUE = 1_000_000.0

PANEL_631L = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260630.csv"
OUT = PROJECT_ROOT / "results" / "a2118_tail_risk_override_2025_2026_crosscheck_20260705.json"

H20_MAX = 0.33
CONF_MIN = 0.55
H5_REENTRY_MIN = 0.55

# The two 2008-proxy variants that showed a genuine improvement there.
VARIANTS = [
    {"override_tail_risk_score": 1, "override_drawdown_threshold": -0.08},
    {"override_tail_risk_score": 1, "override_drawdown_threshold": -0.10},
]


def _make_patched_switch_returns(override_tail_risk_score: int | None, override_drawdown_threshold: float | None):
    def patched(prices, chip_features, rule, chip_data_fallback_max_stale_days=None):
        if override_tail_risk_score is None:
            return _switch_returns(prices, chip_features, rule, chip_data_fallback_max_stale_days)

        features = _regime_features(prices, rule, chip_features)
        in_defense = False
        hold_days = 0
        regimes = []
        events: list[dict[str, Any]] = []
        for dt, row in features.iterrows():
            price_enter = row["ma_gap"] <= rule.enter_ma_gap or row["drawdown"] <= rule.enter_drawdown
            tail_override_enter = (
                int(row["tail_risk_score"]) >= override_tail_risk_score
                and float(row["drawdown"]) <= override_drawdown_threshold
            )
            chip_ok = int(row["chip_score"]) >= int(rule.require_chip_score)
            derivative_ok = int(row["derivative_score"]) >= int(rule.require_derivative_score)
            total_risk_ok = int(row["total_risk_score"]) >= int(rule.require_total_risk_score)
            tail_risk_ok = int(row["tail_risk_score"]) >= int(rule.require_tail_risk_score)
            if chip_data_fallback_max_stale_days is not None:
                stale_days = row.get(
                    "chip_data_core_days_since_source_update",
                    row.get("chip_data_days_since_source_update", 0),
                )
                if int(stale_days) >= int(chip_data_fallback_max_stale_days):
                    chip_ok = derivative_ok = total_risk_ok = True
            # Normal path: price entry, gated by chip/derivative/total_risk (as today).
            # Tail-risk override path: bypasses ALL of those gates too (matches
            # the 2008 proxy test's construction), not just the MA-gap check.
            enter = (price_enter and chip_ok and derivative_ok and total_risk_ok and tail_risk_ok) or tail_override_enter
            exit_ = row["ma_gap"] >= rule.exit_ma_gap and row["exit_momentum"] > 0.0
            if in_defense:
                hold_days += 1
                if hold_days >= rule.min_hold_days and exit_:
                    in_defense = False
                    hold_days = 0
                    events.append({"date": str(dt.date()), "action": "switch_to_golden"})
            elif enter:
                in_defense = True
                hold_days = 1
                events.append({"date": str(dt.date()), "action": "switch_to_group_a_plus_defensive", "via_tail_override": bool(tail_override_enter and not price_enter)})
            regimes.append("group_a_plus_defensive" if in_defense else "golden1")
        features = features.copy()
        features["regime"] = regimes
        return events, features

    return patched


def _run(override_tail_risk_score=None, override_drawdown_threshold=None) -> dict:
    original = a2118_module._switch_returns
    a2118_module._switch_returns = _make_patched_switch_returns(override_tail_risk_score, override_drawdown_threshold)
    try:
        report, frame = a2118_module.run_a2118(
            START, END, INITIAL_VALUE, DB_PATH,
            ncf_panel_631l_path=str(PANEL_631L),
            h20_max=H20_MAX, conf_min=CONF_MIN, h5_reentry_min=H5_REENTRY_MIN,
        )
    finally:
        a2118_module._switch_returns = original
    defensive_days = int((frame["execution_regime"] == "group_a_plus_defensive").sum())
    return {"metrics": report["metrics"], "defensive_days": defensive_days}


def main() -> None:
    baseline = _run()
    baseline_metrics = baseline["metrics"]

    variants: list[dict[str, Any]] = []
    for v in VARIANTS:
        result = _run(**v)
        m = result["metrics"]
        variants.append({
            **v,
            "defensive_days": result["defensive_days"],
            "defensive_days_delta": result["defensive_days"] - baseline["defensive_days"],
            "metrics": m,
            "delta_vs_baseline": {
                "final_value": float(m["final_value"]) - float(baseline_metrics["final_value"]),
                "sharpe_ratio": float(m["sharpe_ratio"]) - float(baseline_metrics["sharpe_ratio"]),
                "max_drawdown": float(m["max_drawdown"]) - float(baseline_metrics["max_drawdown"]),
            },
        })

    result = {
        "experiment": "a2118_tail_risk_override_2025_2026_crosscheck",
        "window": {"start": START, "end": END},
        "baseline": {"metrics": baseline_metrics, "defensive_days": baseline["defensive_days"]},
        "variants": variants,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
