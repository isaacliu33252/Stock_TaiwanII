#!/usr/bin/env python3
"""Direction #8 faithful re-test (2026-09-08 audit follow-up).

The original direction-8 script (test_a207_2020fix_stability_20260908.py)
imported group_a_plus.runners.a207.A207_RULE -- an unrelated research
baseline -- instead of a2111's actual production switch rule, and used a
simplified defensive basket instead of production's real basket. A
"corrected" re-run was described in
project_fable_direction8_a207_2020fix_not_robust_20260908.md as having been
done, but the memory file itself says that corrected version was only run
in a scratchpad and never committed -- so as of the 2026-09-08 audit, there
is NO committed, independently-checkable evidence for direction 8's
corrected conclusion at all.

This closes that gap the way both the handoff and the memory file say is
required: call group_a_plus.runners.a2118.run_a2118() directly (the actual
production runner, not a hand-rolled proxy), toggling ONLY the three
2020-fix parameters (risk_score_lookback_days, momentum_fast_exit_min,
momentum_fast_exit_ma_gap_min) between None (PRE-fix, a2118's defaults
before the 2026-07-06 fix) and their current production values (POST-fix,
run_a2118's own defaults). Everything else -- switch rule base params,
defensive basket (bond0_cash60, hardcoded inside run_a2118 itself as of the
2026-08-18 promotion), NCF overlays, golden1 weights -- comes from
report/group_a_plus/latest/strategy.json's actual active runner_params, so
this is apples-to-apples with what production actually runs today (though
still using whatever golden1 snapshot resolution run_a2118's own backtest
replay uses -- see the H3 caveat already documented for direction 6; this
script does not attempt to fix that separate limitation).

Windows match the original direction-8 analysis: full calendar year 2020,
2022, and 2025 (partial, through today).

Read-only research. Does not touch any production/live file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.runners.a2118 import run_a2118
from backtest_group_a_plus_switch_policy import DB_PATH

STRATEGY_JSON = PROJECT_ROOT / "report/group_a_plus/latest/strategy.json"
RUNNER_PARAMS = json.loads(STRATEGY_JSON.read_text(encoding="utf-8"))["active_strategy"]["runner_params"]

INITIAL_VALUE = 1_000_000.0

WINDOWS = [
    ("2020_full_year", "2020-01-01", "2020-12-31"),
    ("2022_full_year", "2022-01-01", "2022-12-31"),
    ("2025_full_year", "2025-01-01", "2026-09-04"),
]

PRE_FIX_OVERRIDE = dict(
    risk_score_lookback_days=None,
    momentum_fast_exit_min=None,
    momentum_fast_exit_ma_gap_min=None,
)
POST_FIX_OVERRIDE = dict(
    risk_score_lookback_days=5,
    momentum_fast_exit_min=0.10,
    momentum_fast_exit_ma_gap_min=-0.08,
)


def main() -> None:
    results = {}
    for label, start, end in WINDOWS:
        window_result = {}
        for variant_name, override in (("pre_fix", PRE_FIX_OVERRIDE), ("post_fix", POST_FIX_OVERRIDE)):
            params = {**RUNNER_PARAMS, **override}
            report, frame = run_a2118(start, end, INITIAL_VALUE, DB_PATH, **params)
            metrics = report["metrics"]
            defensive_days = int((frame["execution_regime"].astype(str) == "group_a_plus_defensive").sum())
            window_result[variant_name] = {
                "final_value": metrics["final_value"],
                "sharpe_ratio": metrics["sharpe_ratio"],
                "max_drawdown": metrics["max_drawdown"],
                "defensive_days": defensive_days,
                "total_days": int(len(frame)),
            }
        pre = window_result["pre_fix"]
        post = window_result["post_fix"]
        window_result["delta_post_minus_pre"] = {
            "final_value": post["final_value"] - pre["final_value"],
            "sharpe_ratio": post["sharpe_ratio"] - pre["sharpe_ratio"],
            "max_drawdown_pp": (post["max_drawdown"] - pre["max_drawdown"]) * 100,
            "defensive_days": post["defensive_days"] - pre["defensive_days"],
        }
        results[label] = window_result

        print(f"=== {label} ({start}..{end}) ===")
        print(
            f"  pre_fix : final={pre['final_value']:,.0f} sharpe={pre['sharpe_ratio']:.4f} "
            f"mdd={pre['max_drawdown']*100:.2f}% defensive_days={pre['defensive_days']}/{pre['total_days']}"
        )
        print(
            f"  post_fix: final={post['final_value']:,.0f} sharpe={post['sharpe_ratio']:.4f} "
            f"mdd={post['max_drawdown']*100:.2f}% defensive_days={post['defensive_days']}/{post['total_days']}"
        )
        d = window_result["delta_post_minus_pre"]
        print(
            f"  delta   : final={d['final_value']:+,.0f} sharpe={d['sharpe_ratio']:+.4f} "
            f"mdd={d['max_drawdown_pp']:+.2f}pp defensive_days={d['defensive_days']:+d}"
        )
        print()

    out_path = PROJECT_ROOT / "results" / "a207_2020fix_stability_a2118_faithful_20260908.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
