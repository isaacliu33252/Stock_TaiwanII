#!/usr/bin/env python3
"""Evaluate A21.24 (follow-through trim + rebound recapture) vs A21.18 baseline (2026-07-10).

User question: after a de-risk/trim event, should there be a "re-entry
accelerator" -- a brief exposure boost once a rebound confirms stabilization?
`group_a_plus/runners/a2124.py` already implements exactly this (built in an
earlier session as an uncommitted shadow candidate) but was never backtested.

Learned lesson from the same day's A22_bad_vol_overlay work (see
GROUP_A_PLUS_00631L_DOWNSIDE_RISK_RACE_CLASSIFIER_HANDOFF_20260710.md): a
config that looks good after repeated tuning on one fixed set of windows can
fail completely out-of-sample. So this script evaluates A21.24 with its
built-in (untuned, as-shipped) parameters on BOTH the original 4 standard
windows (2025-2026 NCF panel) AND the 2017/2018/2019 out-of-sample years
(backfilled NCF panel) in the same run, from the start -- not as an
afterthought.

Research-only. Does not touch any live signal or target weight.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.runners.a2118 import CHIP_DATA_FALLBACK_MAX_STALE_DAYS, run_a2118
from group_a_plus.runners.a2124 import run_a2124

PANEL_2025_2026 = "results/ncf_00631l_panel_latest_20260707.csv"
PANEL_2017_2019 = "results/ncf_00631l_panel_backfill_2017_2019_20260710.csv"

WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31", PANEL_2025_2026, "tuning_window"),
    ("inflation_2022", "2022-01-03", "2022-12-30", PANEL_2025_2026, "tuning_window"),
    ("live_2024_2026", "2024-01-02", "2026-07-09", PANEL_2025_2026, "tuning_window"),
    ("active_2025_2026", "2025-01-02", "2026-07-09", PANEL_2025_2026, "tuning_window"),
    ("2017_bull", "2017-01-03", "2017-12-29", PANEL_2017_2019, "out_of_sample"),
    ("2018_correction", "2018-01-02", "2018-12-31", PANEL_2017_2019, "out_of_sample"),
    ("2019_recovery", "2019-01-02", "2019-12-31", PANEL_2017_2019, "out_of_sample"),
]

# a2124.py predates run_a2118's risk_score_lookback_days/momentum_fast_exit_*
# kwargs and does not forward them. To isolate only the trim+recapture overlay
# effect, the baseline is run through the exact same subset of kwargs (i.e.
# both sides fall back to run_a2118's own defaults for the params a2124 can't
# pass), not the fuller kwarg set used elsewhere in this project's evaluate
# scripts.
COMMON_KW = dict(
    h20_max=0.33,
    conf_min=0.55,
    h5_reentry_min=0.55,
    chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
)


# Loosened trigger config (2026-07-10, chosen a priori -- NOT tuned by peeking
# at results -- to address the "only 3 recapture events across 7 windows"
# sample-size problem found with a2124's as-shipped defaults). Roughly halves
# the extremity of every threshold; sizing (trim_fraction/boost_fraction)
# left unchanged so this isolates the effect of triggering more often, not of
# trimming/boosting harder.
LOOSENED_OVERLAY_KW = dict(
    golden_follow_through_trim_enabled=True,
    golden_follow_through_trim_fraction=0.05,
    golden_follow_through_previous_return_max=-0.02,
    golden_follow_through_previous_tail_risk_score_min=1,
    golden_follow_through_previous_drawdown_max=-0.05,
    golden_follow_through_hold_days=1,
    golden_rebound_recapture_enabled=True,
    golden_rebound_recapture_boost_fraction=0.10,
    golden_rebound_recapture_previous_return_min=0.02,
    golden_rebound_recapture_previous_drawdown_max=-0.05,
    golden_rebound_recapture_lookback_days=5,
    golden_rebound_recapture_hold_days=1,
    golden_rebound_recapture_shock_tail_risk_score_min=1,
    golden_rebound_recapture_shock_return_max=-0.02,
)


def _run_variant(name, start, end, panel, db_path):
    if name == "a2124_default":
        return run_a2124(
            start=start, end=end, initial_value=1_000_000.0, db=db_path,
            ncf_panel_631l_path=panel, **COMMON_KW,
        )
    if name == "loosened_trigger":
        report, frame = run_a2118(
            start=start, end=end, initial_value=1_000_000.0, db=db_path,
            ncf_panel_631l_path=panel, **COMMON_KW, **LOOSENED_OVERLAY_KW,
        )
        report["experiment"] = "group_a_plus_a2124_loosened_trigger_shadow"
        return report, frame
    raise ValueError(name)


def main() -> None:
    db_path = Path(DB_PATH)
    all_results: dict[str, list[dict]] = {}
    for variant_name in ["a2124_default", "loosened_trigger"]:
        print(f"\n=== variant: {variant_name} ===")
        results = []
        for label, start, end, panel, kind in WINDOWS:
            baseline, _ = run_a2118(
                start=start, end=end, initial_value=1_000_000.0, db=db_path,
                ncf_panel_631l_path=panel, **COMMON_KW,
            )
            variant, frame = _run_variant(variant_name, start, end, panel, db_path)
            bm = baseline["metrics"]
            vm = variant["metrics"]
            recapture_days = int((frame["execution_regime"] == "golden1_rebound_recapture").sum())
            trim_days = int((frame["execution_regime"] == "golden1_follow_through_trim").sum())
            result = {
                "label": label,
                "kind": kind,
                "window": {"start": start, "end": end},
                "follow_through_trim_days": trim_days,
                "rebound_recapture_days": recapture_days,
                "baseline": {"final_value": bm["final_value"], "sharpe_ratio": bm["sharpe_ratio"]},
                "variant": {"final_value": vm["final_value"], "sharpe_ratio": vm["sharpe_ratio"]},
                "delta_final_value": vm["final_value"] - bm["final_value"],
                "delta_sharpe_ratio": vm["sharpe_ratio"] - bm["sharpe_ratio"],
            }
            results.append(result)
            print(
                f"[{kind:14s}] {label:18s} trim_days={trim_days:3d} recapture_days={recapture_days:3d} "
                f"delta_final={result['delta_final_value']:>10.1f} delta_sharpe={result['delta_sharpe_ratio']:>8.4f}"
            )

        tuning_sum_sharpe = sum(r["delta_sharpe_ratio"] for r in results if r["kind"] == "tuning_window")
        oos_sum_sharpe = sum(r["delta_sharpe_ratio"] for r in results if r["kind"] == "out_of_sample")
        tuning_sum_fv = sum(r["delta_final_value"] for r in results if r["kind"] == "tuning_window")
        oos_sum_fv = sum(r["delta_final_value"] for r in results if r["kind"] == "out_of_sample")
        total_trim = sum(r["follow_through_trim_days"] for r in results)
        total_recapture = sum(r["rebound_recapture_days"] for r in results)
        print(f"total trim_days={total_trim} total recapture_days={total_recapture}")
        print(f"tuning windows sum: delta_sharpe={tuning_sum_sharpe:.4f} delta_final={tuning_sum_fv:.1f}")
        print(f"out-of-sample sum:  delta_sharpe={oos_sum_sharpe:.4f} delta_final={oos_sum_fv:.1f}")
        all_results[variant_name] = results

    output_path = PROJECT_ROOT / "results" / "group_a_plus_a2124_rebound_recapture_20260710.json"
    output_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
