#!/usr/bin/env python3
"""Out-of-sample robustness check for the standalone-0050-momentum-filter
thread flagged (not pursued) in
docs/HANDOFF_2104_03667_REGIME_CLUSTERING_VLSTAR_GROUPA_PLUS_20260827.md.

Follow-up 2 of that review found that filtering a naive 20d-momentum(0050)
strategy with a drawdown-selected VLSTAR-lite regime detector (paper-default,
un-tuned hyperparameters, transition variable chosen by a non-performance
correlation criterion) Pareto-dominates the unfiltered strategy over the
FULL historical window (Sharpe 1.007->1.144, MDD -21.47%->-17.29%). That
number is a single pooled statistic over one continuous window -- exactly
the kind of result this project treats with suspicion until it is checked
per-year (see e.g. chasm_online_changepoint_dynamics_regime_detection's
promotion_checklist note: "single continuous window, not independent-year
split" as a flagged weakness).

This script reruns the same, already-fixed detector (no new hyperparameter
search) and breaks the comparison down by calendar year, to check whether
the aggregate improvement is broad-based or driven by one or two dominant
episodes (e.g. COVID 2020).

CAVEAT NOT RESOLVED HERE: the transition variable itself (drawdown) was
selected once using the full sample's correlation with next-day volatility.
A fully walk-forward version would re-select the variable using only each
fold's trailing data. This script does not do that -- it only checks
whether the fixed, already-selected detector's edge is broad-based across
years, which is a necessary but not sufficient robustness condition.

Research-only. Does not touch any production runner, signal, or execution
plan. Scoped entirely to the standalone-momentum-filter thread -- does not
touch, and has no bearing on, the golden1/defensive switch decision, which
is separately and independently closed (see the four prior 2104.03667
follow-ups).
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
    _load_close,
    _apply_min_hold,
    _perf_stats,
    MIN_HOLD_DAYS,
)
from scripts.evaluate.build_group_a_plus_2104_03667_transition_variable_selection import (  # noqa: E402
    CANDIDATE_VARIABLES,
    DEFAULT_GAMMA_SCALE,
    DEFAULT_THRESHOLD,
    REGIME_FEATURES_CSV,
    _causal_vlstar_lite,
    _select_transition_variable,
)

OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2104_03667_momentum_filter_year_split_validation.json"


def build_review(
    db_path: Path = DB_PATH,
    regime_features_path: Path = REGIME_FEATURES_CSV,
    core_tickers: tuple[str, ...] = CORE_TICKERS,
    min_hold_days: int = MIN_HOLD_DAYS,
) -> dict:
    if not regime_features_path.exists():
        return {"status": "blocked", "blocking_reasons": ["regime_features_csv_missing"], "target_weight_change_allowed": False}
    close = _load_close(db_path, core_tickers)
    if close.empty:
        return {"status": "blocked", "blocking_reasons": ["insufficient_price_history"], "target_weight_change_allowed": False}

    features = pd.read_csv(
        regime_features_path,
        usecols=["dt", "ma_gap", "drawdown", "realized_vol_0050_20d", "tail_risk_score", "total_risk_score"],
    )
    features["dt"] = pd.to_datetime(features["dt"])
    features = features.set_index("dt").sort_index()

    selection = _select_transition_variable(features, close["0050.TW"])
    col, sign = CANDIDATE_VARIABLES[selection["selected_variable"]]
    signal = sign * features[col]

    raw = _causal_vlstar_lite(signal, gamma_scale=DEFAULT_GAMMA_SCALE, threshold=DEFAULT_THRESHOLD)
    daily = raw.reindex(close.index).fillna(False).astype(bool)
    daily = _apply_min_hold(daily, min_hold_days)
    lagged = daily.shift(1).fillna(False).astype(bool)

    ret_0050 = np.log(close["0050.TW"] / close["0050.TW"].shift(1)).dropna()
    mom_signal = (
        (close["0050.TW"].pct_change(20) > 0).reindex(ret_0050.index).fillna(False).astype(bool)
        .shift(1).fillna(False).astype(bool)
    )
    lagged_a = lagged.reindex(ret_0050.index).fillna(False).astype(bool)

    # IMPORTANT: the regime-features CSV (drawdown, the selected transition
    # variable) only starts 2020-01-02, while 0050 price history used for
    # ret_0050/mom_signal starts 2017-01-11 (bounded by 00679B.TWO's launch
    # date via _load_close's dropna(how="any") across CORE_TICKERS). Any date
    # before the features start has lagged_a trivially False via reindex
    # fillna -- i.e. the filter is silently OFF, not "detected calm". That
    # inflates any "filtered beats unfiltered" full-window comparison with
    # ~3 years where the mechanism could not possibly have fired. Restrict
    # the comparison to the actual overlap window where the transition
    # variable exists, so "filtered" vs "unfiltered" is an honest comparison
    # over dates where the filter could actually do something.
    feature_start = features.index.min()
    overlap_mask = ret_0050.index >= feature_start
    ret_0050 = ret_0050.loc[overlap_mask]
    mom_signal = mom_signal.loc[overlap_mask]
    lagged_a = lagged_a.loc[overlap_mask]

    unfiltered_ret = pd.Series(np.where(mom_signal, ret_0050, 0.0), index=ret_0050.index)
    filtered_ret = pd.Series(np.where(mom_signal & ~lagged_a, ret_0050, 0.0), index=ret_0050.index)

    full_window = {
        "unfiltered": _perf_stats(unfiltered_ret.values),
        "filtered": _perf_stats(filtered_ret.values),
    }

    per_year = {}
    for year, idx in ret_0050.groupby(ret_0050.index.year).groups.items():
        u = unfiltered_ret.loc[idx].values
        f = filtered_ret.loc[idx].values
        if len(u) < 200:  # a full Taiwan trading year is ~240 days; flag partial first/last years
            thin = True
        else:
            thin = False
        pu = _perf_stats(u)
        pf = _perf_stats(f)
        per_year[str(year)] = {
            "n_trading_days": int(len(u)),
            "thin_sample": thin,
            "unfiltered": pu,
            "filtered": pf,
            "filtered_wins_sharpe": bool(pf["sharpe"] > pu["sharpe"]),
            "filtered_wins_mdd": bool(pf["mdd"] > pu["mdd"]),
            "filtered_wins_both": bool(pf["sharpe"] > pu["sharpe"] and pf["mdd"] > pu["mdd"]),
        }

    full_years = {y: v for y, v in per_year.items() if not v["thin_sample"]}
    n_full_years = len(full_years)
    n_wins_both = sum(1 for v in full_years.values() if v["filtered_wins_both"])
    n_wins_sharpe = sum(1 for v in full_years.values() if v["filtered_wins_sharpe"])
    n_wins_mdd = sum(1 for v in full_years.values() if v["filtered_wins_mdd"])

    return {
        "paper": "arXiv:2104.03667",
        "follow_up_of": "2104_03667_regime_detection_vlstar_hierarchical_clustering",
        "scope": "standalone_0050_momentum_filter_only -- does NOT affect the golden1/defensive switch decision",
        "status": "available_for_shadow_monitoring",
        "transition_variable_used": selection["selected_variable"],
        "gamma_scale": DEFAULT_GAMMA_SCALE,
        "threshold": DEFAULT_THRESHOLD,
        "full_window": full_window,
        "per_year": per_year,
        "n_full_years": n_full_years,
        "n_years_filtered_wins_both": n_wins_both,
        "n_years_filtered_wins_sharpe": n_wins_sharpe,
        "n_years_filtered_wins_mdd": n_wins_mdd,
        "broad_based_edge": bool(n_full_years > 0 and n_wins_both >= (n_full_years + 1) // 2),
        "caveat": "transition variable was selected once on the full sample by correlation with next-day "
                  "volatility, not re-selected per fold -- this is a necessary-but-not-sufficient robustness "
                  "check, not a full walk-forward re-selection.",
        "target_weight_change_allowed": False,
        "replace_a2118": False,
        "train_vlstar_now": False,
    }


def write_review(review: dict, output_path: Path = OUTPUT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    review = build_review()
    fw = review.get("full_window", {})
    print("=== Full window (for reference) ===")
    for name, p in fw.items():
        print(f"{name:12s} sharpe={p['sharpe']:6.3f}  mdd={p['mdd']*100:7.2f}%  ann_ret={p['ann_ret']*100:7.2f}%")

    print("\n=== Per-year breakdown: unfiltered vs drawdown-VLSTAR-lite-filtered ===")
    print(f"{'year':>6} {'n_days':>7} {'u_sharpe':>9} {'f_sharpe':>9} {'u_mdd':>9} {'f_mdd':>9} {'wins_both':>10}")
    for year, v in review.get("per_year", {}).items():
        thin = " (thin)" if v["thin_sample"] else ""
        u, f = v["unfiltered"], v["filtered"]
        print(f"{year:>6}{thin} {v['n_trading_days']:>7} {u['sharpe']:>9.3f} {f['sharpe']:>9.3f} "
              f"{u['mdd']*100:>8.2f}% {f['mdd']*100:>8.2f}% {str(v['filtered_wins_both']):>10}")

    print(f"\nFull years counted: {review.get('n_full_years')}")
    print(f"Years filtered wins BOTH sharpe and mdd: {review.get('n_years_filtered_wins_both')}")
    print(f"Years filtered wins sharpe only: {review.get('n_years_filtered_wins_sharpe')}")
    print(f"Years filtered wins mdd only: {review.get('n_years_filtered_wins_mdd')}")
    print(f"Broad-based edge (wins both in >=half of full years): {review.get('broad_based_edge')}")

    write_review(review, OUTPUT)
    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()
