#!/usr/bin/env python3
"""Follow-up to arXiv:2104.03667 (see
build_group_a_plus_2104_03667_regime_clustering_review.py and
docs/HANDOFF_2104_03667_REGIME_CLUSTERING_VLSTAR_GROUPA_PLUS_20260827.md).

The original review found VLSTAR-lite (a fixed gamma_scale=3.0, threshold=0.5
logistic smooth-transition proxy) genuinely cuts MDD on the paper's own
naive-momentum(0050) validation (-21.47% -> -13.42%) but at a steep Sharpe/
return cost, because it is over-triggered (69% of days flagged "volatile").
That review explicitly left open whether a different (gamma_scale, threshold)
choice -- never swept -- could keep most of the MDD benefit while giving back
less return, i.e. whether the closed_negative verdict reflects the method or
just one untested hyperparameter choice.

This script sweeps gamma_scale x threshold and re-evaluates both of the
original review's tests (A: naive momentum(0050) filter, B: Group A+
golden1/defensive switch-blend) for every combination, to answer that
question directly rather than leaving it as a caveat.

Research-only. Does not touch any production runner, signal, or execution
plan.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_2104_03667_regime_clustering_review import (  # noqa: E402
    CORE_TICKERS,
    DB_PATH,
    DEFENSIVE_COL,
    GOLDEN_COL,
    MIN_HOLD_DAYS,
    REGIME_CSV,
    SWITCH_CURVE,
    SWITCH_COL,
    _apply_min_hold,
    _load_close,
    _perf_stats,
    _vlstar_lite_g,
)

OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2104_03667_vlstar_lite_sensitivity_sweep.json"

GAMMA_SCALE_GRID = (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0)
THRESHOLD_GRID = (0.5, 0.6, 0.7, 0.8, 0.9)


def run_sweep(
    db_path: Path = DB_PATH,
    switch_curve_path: Path = SWITCH_CURVE,
    core_tickers: tuple[str, ...] = CORE_TICKERS,
    gamma_scale_grid: tuple[float, ...] = GAMMA_SCALE_GRID,
    threshold_grid: tuple[float, ...] = THRESHOLD_GRID,
    min_hold_days: int = MIN_HOLD_DAYS,
) -> dict:
    close = _load_close(db_path, core_tickers)
    if close.empty:
        return {
            "status": "blocked",
            "blocking_reasons": ["insufficient_price_history"],
            "target_weight_change_allowed": False,
        }
    ret_0050 = np.log(close["0050.TW"] / close["0050.TW"].shift(1)).dropna()
    mom_signal = (
        (close["0050.TW"].pct_change(20) > 0)
        .reindex(ret_0050.index)
        .fillna(False)
        .astype(bool)
        .shift(1)
        .fillna(False)
        .astype(bool)
    )
    unfiltered_ret = np.where(mom_signal, ret_0050, 0.0)
    baseline_a = _perf_stats(np.asarray(unfiltered_ret))

    switch_check_available = switch_curve_path.exists()
    df_switch = None
    if switch_check_available:
        curve = pd.read_csv(switch_curve_path)
        curve["dt"] = pd.to_datetime(curve["dt"])
        curve = curve.set_index("dt").sort_index()
        df_switch = pd.concat(
            [curve[GOLDEN_COL].pct_change().rename("golden"), curve[DEFENSIVE_COL].pct_change().rename("defensive")],
            axis=1,
        ).dropna()
        golden_alone_b = _perf_stats(df_switch["golden"].values)
        rule_switch = curve[SWITCH_COL].pct_change().reindex(df_switch.index)
        rule_switch_b = _perf_stats(rule_switch.dropna().values)

    results = []
    for gamma_scale in gamma_scale_grid:
        g = _vlstar_lite_g(close["0050.TW"], gamma_scale=gamma_scale)
        for threshold in threshold_grid:
            raw = (g > threshold).reindex(ret_0050.index).fillna(False).astype(bool)
            daily = _apply_min_hold(raw, min_hold_days)
            lagged = daily.shift(1).fillna(False).astype(bool)

            volatile_share = float(lagged.mean())
            filtered_ret = np.where(mom_signal & ~lagged.reindex(mom_signal.index).fillna(False).astype(bool), ret_0050, 0.0)
            perf_a = _perf_stats(np.asarray(filtered_ret))

            row = {
                "gamma_scale": gamma_scale,
                "threshold": threshold,
                "volatile_share": round(volatile_share, 4),
                "test_a_momentum_filter": perf_a,
                "test_a_sharpe_vs_baseline": round(perf_a["sharpe"] - baseline_a["sharpe"], 4),
                "test_a_mdd_improvement": round(perf_a["mdd"] - baseline_a["mdd"], 4),
            }

            if switch_check_available:
                lagged_switch = lagged.reindex(df_switch.index).fillna(False).astype(bool)
                switch_ret = np.where(lagged_switch, df_switch["defensive"], df_switch["golden"])
                perf_b = _perf_stats(np.asarray(switch_ret))
                row["test_b_switch_blend"] = perf_b
                row["test_b_sharpe_vs_rule"] = round(perf_b["sharpe"] - rule_switch_b["sharpe"], 4)
                row["test_b_mdd_vs_rule"] = round(perf_b["mdd"] - rule_switch_b["mdd"], 4)

            results.append(row)

    # A combo is a genuine improvement only if it beats the baseline on BOTH
    # Sharpe and MDD in test A (a pure win, not a trade), or if it dominates
    # the existing switch rule on both axes in test B.
    pareto_wins_a = [
        r for r in results
        if r["test_a_sharpe_vs_baseline"] > 0 and r["test_a_mdd_improvement"] > 0
    ]
    pareto_wins_b = [
        r for r in results
        if switch_check_available and r["test_b_sharpe_vs_rule"] > 0 and r["test_b_mdd_vs_rule"] > 0
    ]

    result = {
        "paper": "arXiv:2104.03667",
        "follow_up_of": "2104_03667_regime_detection_vlstar_hierarchical_clustering",
        "status": "available_for_shadow_monitoring",
        "grid": {"gamma_scale": list(gamma_scale_grid), "threshold": list(threshold_grid)},
        "n_combinations": len(results),
        "test_a_baseline_unfiltered_momentum": baseline_a,
        "test_b_baseline_golden1_alone": golden_alone_b if switch_check_available else None,
        "test_b_baseline_existing_rule": rule_switch_b if switch_check_available else None,
        "sweep_results": results,
        "pareto_dominant_combinations_test_a": pareto_wins_a,
        "pareto_dominant_combinations_test_b": pareto_wins_b,
        "any_combination_dominates_baseline_test_a": len(pareto_wins_a) > 0,
        "any_combination_dominates_existing_rule_test_b": len(pareto_wins_b) > 0,
        "target_weight_change_allowed": False,
        "replace_a2118": False,
        "train_vlstar_now": False,
    }
    return result


def write_sweep(result: dict, output_path: Path = OUTPUT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    result = run_sweep()
    print(f"Swept {result.get('n_combinations')} (gamma_scale x threshold) combinations")
    baseline_a = result.get("test_a_baseline_unfiltered_momentum", {})
    print(f"\nTest A baseline (unfiltered momentum): sharpe={baseline_a.get('sharpe', 0):.3f}  "
          f"mdd={baseline_a.get('mdd', 0)*100:.2f}%")
    print("\n=== Test A: gamma_scale x threshold grid ===")
    print(f"{'gamma':>6} {'thresh':>7} {'vol_share':>10} {'sharpe':>8} {'mdd':>9} {'dSharpe':>9} {'dMDD':>9}")
    for r in result.get("sweep_results", []):
        p = r["test_a_momentum_filter"]
        print(f"{r['gamma_scale']:>6.1f} {r['threshold']:>7.2f} {r['volatile_share']*100:>9.1f}% "
              f"{p['sharpe']:>8.3f} {p['mdd']*100:>8.2f}% {r['test_a_sharpe_vs_baseline']:>+9.3f} "
              f"{r['test_a_mdd_improvement']*100:>+8.2f}%")

    rule_b = result.get("test_b_baseline_existing_rule")
    if rule_b:
        print(f"\nTest B baseline (existing switch rule): sharpe={rule_b.get('sharpe', 0):.3f}  "
              f"mdd={rule_b.get('mdd', 0)*100:.2f}%")
        print("\n=== Test B: gamma_scale x threshold grid ===")
        print(f"{'gamma':>6} {'thresh':>7} {'sharpe':>8} {'mdd':>9} {'dSharpe':>9} {'dMDD':>9}")
        for r in result.get("sweep_results", []):
            p = r.get("test_b_switch_blend")
            if not p:
                continue
            print(f"{r['gamma_scale']:>6.1f} {r['threshold']:>7.2f} {p['sharpe']:>8.3f} {p['mdd']*100:>8.2f}% "
                  f"{r['test_b_sharpe_vs_rule']:>+9.3f} {r['test_b_mdd_vs_rule']*100:>+8.2f}%")

    print(f"\nany combination dominates test A baseline (both sharpe & mdd better): "
          f"{result.get('any_combination_dominates_baseline_test_a')}")
    print(f"any combination dominates test B existing rule (both sharpe & mdd better): "
          f"{result.get('any_combination_dominates_existing_rule_test_b')}")

    write_sweep(result, OUTPUT)
    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()
