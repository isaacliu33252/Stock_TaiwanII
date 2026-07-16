#!/usr/bin/env python3
"""Research sweep: does enabling SwitchRule's `override_risk_score` (bypass
MA-gap entry when total_risk_score + drawdown both fire) or
`low_risk_exit_ma_gap` (faster exit back to golden1 once total_risk_score has
cooled) actually improve a2118, versus leaving them at their current
production-disabled defaults (override_risk_score=0, low_risk_exit_ma_gap=None)?

Context: these fields exist on `SwitchRule` (backtest_group_a_plus_switch_policy.py)
but the a2111/a2118 production rule (`_build_switch_rule()` in
group_a_plus/runners/a2111.py) never sets them -- a stray regenerated
`switch_backtest.json` surfaced them but on inspection was not itself an
improvement (final_value +1.3%, Sharpe -0.072, Sortino -0.091, max_drawdown
unchanged -- see chat 2026-07-05) and both fields were literally at their
disabled defaults in that file too. This sweep asks the sharper question:
is there ANY setting of these two mechanisms that improves the actual a2118
strategy (base regime + NCF late-bull overlay), not just a same-window
re-run noise artifact?

Read-only with respect to production strategy code: monkeypatches
`_build_switch_rule` inside `group_a_plus.runners.a2118`'s own namespace for
the duration of each run (restored after), never edits a2111.py/a2118.py on
disk. Writes one JSON report to results/.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import group_a_plus.runners.a2118 as a2118_module  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.runners.a2111 import _build_switch_rule as _base_build_switch_rule  # noqa: E402

START = "2025-01-02"
END = "2026-07-03"
INITIAL_VALUE = 1_000_000.0

PANEL_631L = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260630.csv"
OUT = PROJECT_ROOT / "results" / "a2118_switch_rule_override_lowrisk_exit_sweep_20260705.json"

# Production a2118 params (report/group_a_plus/latest/strategy.json runner_params).
H20_MAX = 0.33
CONF_MIN = 0.55
H5_REENTRY_MIN = 0.55

BASE_RULE = _base_build_switch_rule()

OVERRIDE_RISK_SCORES = [6, 7, 8, 9, 10]
OVERRIDE_DRAWDOWN_THRESHOLDS = [-0.03, -0.05, -0.07, -0.10]
LOW_RISK_EXIT_MA_GAPS = [0.0, 0.003, 0.005, 0.008]
LOW_RISK_EXIT_SCORE_THRESHOLDS = [0, 1, 2, 3]


def _run_with_rule(rule) -> dict:
    def patched_build_switch_rule():
        return rule

    original = a2118_module._build_switch_rule
    a2118_module._build_switch_rule = patched_build_switch_rule
    try:
        report, frame = a2118_module.run_a2118(
            START,
            END,
            INITIAL_VALUE,
            DB_PATH,
            ncf_panel_631l_path=str(PANEL_631L),
            h20_max=H20_MAX,
            conf_min=CONF_MIN,
            h5_reentry_min=H5_REENTRY_MIN,
        )
    finally:
        a2118_module._build_switch_rule = original
    defensive_days = int((frame["execution_regime"] == "group_a_plus_defensive").sum())
    return {"metrics": report["metrics"], "defensive_days": defensive_days, "switch_count": len(report.get("execution", {}).get("late_bull_trigger_events", []))}


def _delta(m: dict, baseline: dict) -> dict:
    return {
        "final_value": float(m["final_value"]) - float(baseline["final_value"]),
        "sharpe_ratio": float(m["sharpe_ratio"]) - float(baseline["sharpe_ratio"]),
        "sortino_ratio": float(m["sortino_ratio"]) - float(baseline["sortino_ratio"]),
        "max_drawdown": float(m["max_drawdown"]) - float(baseline["max_drawdown"]),
    }


def main() -> None:
    baseline = _run_with_rule(BASE_RULE)
    baseline_metrics = baseline["metrics"]

    override_variants: list[dict[str, Any]] = []
    for risk_score in OVERRIDE_RISK_SCORES:
        for dd_threshold in OVERRIDE_DRAWDOWN_THRESHOLDS:
            rule = dataclasses.replace(
                BASE_RULE,
                override_risk_score=risk_score,
                override_drawdown_threshold=dd_threshold,
            )
            result = _run_with_rule(rule)
            override_variants.append({
                "override_risk_score": risk_score,
                "override_drawdown_threshold": dd_threshold,
                "defensive_days": result["defensive_days"],
                "defensive_days_delta": result["defensive_days"] - baseline["defensive_days"],
                "metrics": result["metrics"],
                "delta_vs_baseline": _delta(result["metrics"], baseline_metrics),
            })

    low_risk_exit_variants: list[dict[str, Any]] = []
    for ma_gap in LOW_RISK_EXIT_MA_GAPS:
        for score_threshold in LOW_RISK_EXIT_SCORE_THRESHOLDS:
            rule = dataclasses.replace(
                BASE_RULE,
                low_risk_exit_ma_gap=ma_gap,
                low_risk_exit_score_threshold=score_threshold,
            )
            result = _run_with_rule(rule)
            low_risk_exit_variants.append({
                "low_risk_exit_ma_gap": ma_gap,
                "low_risk_exit_score_threshold": score_threshold,
                "defensive_days": result["defensive_days"],
                "defensive_days_delta": result["defensive_days"] - baseline["defensive_days"],
                "metrics": result["metrics"],
                "delta_vs_baseline": _delta(result["metrics"], baseline_metrics),
            })

    def _is_genuine_improvement(item: dict) -> bool:
        d = item["delta_vs_baseline"]
        return d["final_value"] > 0 and d["max_drawdown"] >= 0 and d["sharpe_ratio"] > 0

    override_wins = [v for v in override_variants if _is_genuine_improvement(v)]
    low_risk_exit_wins = [v for v in low_risk_exit_variants if _is_genuine_improvement(v)]

    override_sorted = sorted(override_variants, key=lambda v: v["delta_vs_baseline"]["final_value"], reverse=True)
    low_risk_exit_sorted = sorted(low_risk_exit_variants, key=lambda v: v["delta_vs_baseline"]["final_value"], reverse=True)

    result = {
        "experiment": "a2118_switch_rule_override_lowrisk_exit_sweep",
        "window": {"start": START, "end": END},
        "base_rule": dataclasses.asdict(BASE_RULE),
        "baseline": {
            "metrics": baseline_metrics,
            "defensive_days": baseline["defensive_days"],
        },
        "override_risk_score_variants": override_variants,
        "low_risk_exit_variants": low_risk_exit_variants,
        "summary": {
            "override_genuine_improvements_count": len(override_wins),
            "low_risk_exit_genuine_improvements_count": len(low_risk_exit_wins),
            "override_genuine_improvements": override_wins,
            "low_risk_exit_genuine_improvements": low_risk_exit_wins,
            "top5_override_by_final_value": override_sorted[:5],
            "top5_low_risk_exit_by_final_value": low_risk_exit_sorted[:5],
        },
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "saved": str(OUT),
                "baseline": {
                    "final_value": baseline_metrics["final_value"],
                    "sharpe_ratio": baseline_metrics["sharpe_ratio"],
                    "sortino_ratio": baseline_metrics["sortino_ratio"],
                    "max_drawdown": baseline_metrics["max_drawdown"],
                    "defensive_days": baseline["defensive_days"],
                },
                "override_genuine_improvements_count": len(override_wins),
                "low_risk_exit_genuine_improvements_count": len(low_risk_exit_wins),
                "top5_override_by_final_value": [
                    {
                        "override_risk_score": v["override_risk_score"],
                        "override_drawdown_threshold": v["override_drawdown_threshold"],
                        "defensive_days_delta": v["defensive_days_delta"],
                        "delta_vs_baseline": v["delta_vs_baseline"],
                    }
                    for v in override_sorted[:5]
                ],
                "top5_low_risk_exit_by_final_value": [
                    {
                        "low_risk_exit_ma_gap": v["low_risk_exit_ma_gap"],
                        "low_risk_exit_score_threshold": v["low_risk_exit_score_threshold"],
                        "defensive_days_delta": v["defensive_days_delta"],
                        "delta_vs_baseline": v["delta_vs_baseline"],
                    }
                    for v in low_risk_exit_sorted[:5]
                ],
            },
            indent=2, ensure_ascii=False, default=str,
        )
    )


if __name__ == "__main__":
    main()
