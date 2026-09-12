#!/usr/bin/env python3
"""Robustness sweep for the GJR-GARCH vs symmetric GARCH OOS forecast
comparison for 00631L.TW (see GROUP_A_PLUS_20260813_GJR_GARCH_OOS_FORECAST_
QUALITY_00631L_HANDOFF.md sec 8): does the "GJR-GARCH forecasts better"
finding hold across a grid of reasonable (train_window, refit_every)
specifications, or does it flip across the 5% significance threshold
depending on arbitrary methodological choices (as the single 08-01 vs
08-13 comparison suggested)?

Runs group_a_plus... no -- scripts.misc.gjr_garch_oos_forecast_quality_
00631l.run_spec() across a small grid and reports, for each spec, the
proper Diebold-Mariano p-value (overall QLIKE and tail-5pct QLIKE), then
summarizes what fraction of specs are significant at 5% in each direction.

Read-only research. Does not modify any production file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.misc.gjr_garch_oos_forecast_quality_00631l import (  # noqa: E402
    END,
    START,
    TICKER,
    _load_returns,
    run_spec,
)

TRAIN_WINDOWS = (400, 500, 600)
REFIT_EVERY = (21, 42, 63)


def main() -> None:
    returns = _load_returns(TICKER, START, END)
    resid_full = returns.to_numpy(dtype=float)
    dates = returns.index
    print(f"{TICKER}: {len(resid_full)} obs, {dates[0].date()} .. {dates[-1].date()}", flush=True)

    specs = [(tw, rf) for tw in TRAIN_WINDOWS for rf in REFIT_EVERY]
    rows = []
    for i, (tw, rf) in enumerate(specs):
        print(f"\n=== spec {i+1}/{len(specs)}: train_window={tw}, refit_every={rf} ===", flush=True)
        result = run_spec(resid_full, dates, initial_train_days=tw, refit_every_days=rf)
        overall_dm = result["overall"]["qlike_diebold_mariano"]
        tail_dm = result["tail_5pct_worst_realized_days"]["qlike_diebold_mariano"]
        row = {
            "train_window": tw,
            "refit_every": rf,
            "n_oos_days": result["oos_window"]["n"],
            "overall_qlike_dm_p": overall_dm.get("p_value"),
            "overall_qlike_dm_sig": overall_dm.get("significant_at_5pct"),
            "overall_qlike_mean_diff": overall_dm.get("mean_diff"),
            "tail_qlike_dm_p": tail_dm.get("p_value"),
            "tail_qlike_dm_sig": tail_dm.get("significant_at_5pct"),
            "tail_qlike_mean_diff": tail_dm.get("mean_diff"),
        }
        rows.append(row)
        print(f"  overall: p={row['overall_qlike_dm_p']:.4f} sig={row['overall_qlike_dm_sig']} "
              f"diff={row['overall_qlike_mean_diff']:.4f}", flush=True)
        print(f"  tail:    p={row['tail_qlike_dm_p']:.4f} sig={row['tail_qlike_dm_sig']} "
              f"diff={row['tail_qlike_mean_diff']:.4f}", flush=True)

    n_overall_sig = sum(1 for r in rows if r["overall_qlike_dm_sig"])
    n_tail_sig = sum(1 for r in rows if r["tail_qlike_dm_sig"])
    n_overall_gjr_better = sum(1 for r in rows if r["overall_qlike_mean_diff"] < 0)
    n_tail_gjr_better = sum(1 for r in rows if r["tail_qlike_mean_diff"] < 0)

    summary = {
        "ticker": TICKER,
        "n_specs": len(specs),
        "specs": rows,
        "overall_significant_at_5pct_frac": n_overall_sig / len(specs),
        "overall_gjr_point_estimate_better_frac": n_overall_gjr_better / len(specs),
        "tail_significant_at_5pct_frac": n_tail_sig / len(specs),
        "tail_gjr_point_estimate_better_frac": n_tail_gjr_better / len(specs),
    }
    out_path = PROJECT_ROOT / "results" / "gjr_garch_robustness_sweep_00631l.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nSaved: {out_path}", flush=True)
    print(f"\nOverall QLIKE: significant at 5% in {n_overall_sig}/{len(specs)} specs "
          f"({summary['overall_significant_at_5pct_frac']:.0%}); "
          f"GJR point estimate better in {n_overall_gjr_better}/{len(specs)}", flush=True)
    print(f"Tail QLIKE:    significant at 5% in {n_tail_sig}/{len(specs)} specs "
          f"({summary['tail_significant_at_5pct_frac']:.0%}); "
          f"GJR point estimate better in {n_tail_gjr_better}/{len(specs)}", flush=True)


if __name__ == "__main__":
    main()
