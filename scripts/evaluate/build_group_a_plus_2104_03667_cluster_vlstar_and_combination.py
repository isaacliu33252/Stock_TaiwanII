#!/usr/bin/env python3
"""Third follow-up to arXiv:2104.03667 (see
build_group_a_plus_2104_03667_regime_clustering_review.py,
build_group_a_plus_2104_03667_transition_variable_selection.py, and
docs/HANDOFF_2104_03667_REGIME_CLUSTERING_VLSTAR_GROUPA_PLUS_20260827.md).

Both prior follow-ups converge on the same story: single-signal VLSTAR-lite
variants get close to but never beat Group A+'s existing switch_ma80_dd11
rule, because that rule is already a tuned multi-factor combination
(MA-gap + drawdown + a 6-part risk score), while every VLSTAR-lite tested so
far uses exactly one input at a time. This follow-up tests one more,
narrowly-scoped idea: does requiring agreement between the paper's own two
competing detectors -- AGNES/Ward hierarchical clustering (correlation-
structure based) AND VLSTAR-lite (the transition-variable-selection version
from follow-up 2, drawdown-based, un-tuned defaults) -- reduce false
positives enough to close the remaining gap.

DELIBERATE SCOPE LIMIT: this reuses the two detectors exactly as already
built and fixed (no new hyperparameter search over the AND-combination
itself), to avoid layering a third multiple-comparison search on top of the
already-flagged overfitting risk in follow-up 1.

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
    MIN_MONTHS_FOR_FIRST_FIT,
    SWITCH_CURVE,
    SWITCH_COL,
    VLSTAR_LITE_MIN_WINDOW,
    _apply_min_hold,
    _causal_cluster_regime,
    _load_close,
    _monthly_corr_features,
    _perf_stats,
)
from scripts.evaluate.build_group_a_plus_2104_03667_transition_variable_selection import (  # noqa: E402
    CANDIDATE_VARIABLES,
    DEFAULT_GAMMA_SCALE,
    DEFAULT_THRESHOLD,
    REGIME_FEATURES_CSV,
    _causal_vlstar_lite,
    _select_transition_variable,
)

OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2104_03667_cluster_vlstar_and_combination.json"


def build_review(
    db_path: Path = DB_PATH,
    regime_features_path: Path = REGIME_FEATURES_CSV,
    switch_curve_path: Path = SWITCH_CURVE,
    core_tickers: tuple[str, ...] = CORE_TICKERS,
    min_hold_days: int = MIN_HOLD_DAYS,
) -> dict:
    if not regime_features_path.exists():
        return {"status": "blocked", "blocking_reasons": ["regime_features_csv_missing"], "target_weight_change_allowed": False}
    close = _load_close(db_path, core_tickers)
    if close.empty or len(close) < VLSTAR_LITE_MIN_WINDOW + 30:
        return {"status": "blocked", "blocking_reasons": ["insufficient_price_history"], "target_weight_change_allowed": False}

    returns = np.log(close / close.shift(1)).dropna(how="any")

    # Detector 1: cluster-regime, exactly as in the original review.
    monthly = _monthly_corr_features(returns)
    cluster_monthly = _causal_cluster_regime(monthly)
    cluster_daily = cluster_monthly.reindex(returns.index, method="ffill").fillna(False).astype(bool)
    cluster_daily = _apply_min_hold(cluster_daily, min_hold_days)

    # Detector 2: VLSTAR-lite on the follow-up-2 selected variable (drawdown),
    # with un-tuned paper-default hyperparameters.
    features = pd.read_csv(
        regime_features_path,
        usecols=["dt", "ma_gap", "drawdown", "realized_vol_0050_20d", "tail_risk_score", "total_risk_score"],
    )
    features["dt"] = pd.to_datetime(features["dt"])
    features = features.set_index("dt").sort_index()
    selection = _select_transition_variable(features, close["0050.TW"])
    col, sign = CANDIDATE_VARIABLES[selection["selected_variable"]]
    signal = sign * features[col]
    vlstar_raw = _causal_vlstar_lite(signal, gamma_scale=DEFAULT_GAMMA_SCALE, threshold=DEFAULT_THRESHOLD)
    vlstar_daily = vlstar_raw.reindex(returns.index).fillna(False).astype(bool)
    vlstar_daily = _apply_min_hold(vlstar_daily, min_hold_days)

    idx = returns.index
    cluster_al = cluster_daily.reindex(idx).fillna(False).astype(bool)
    vlstar_al = vlstar_daily.reindex(idx).fillna(False).astype(bool)
    and_daily = cluster_al & vlstar_al
    and_lagged = and_daily.shift(1).fillna(False).astype(bool)
    cluster_lagged = cluster_al.shift(1).fillna(False).astype(bool)
    vlstar_lagged = vlstar_al.shift(1).fillna(False).astype(bool)

    # Test A: paper's own naive momentum(0050) filter validation.
    # Restrict to dates >= the regime-features CSV's own start (see
    # build_group_a_plus_2104_03667_momentum_filter_year_split_validation.py
    # for the discovery): before that date vlstar_lagged is trivially False
    # via reindex/fillna, which would silently dilute the comparison with
    # years the vlstar detector could not possibly fire in.
    ret_0050 = returns["0050.TW"]
    ret_0050 = ret_0050.loc[ret_0050.index >= features.index.min()]
    mom_signal = (
        (close["0050.TW"].pct_change(20) > 0).reindex(ret_0050.index).fillna(False).astype(bool)
        .shift(1).fillna(False).astype(bool)
    )
    unfiltered_ret = np.where(mom_signal, ret_0050, 0.0)
    test_a = {
        "baseline_unfiltered": _perf_stats(np.asarray(unfiltered_ret)),
        "cluster_only_filtered": _perf_stats(np.asarray(np.where(mom_signal & ~cluster_lagged.reindex(ret_0050.index).fillna(False), ret_0050, 0.0))),
        "vlstar_only_filtered": _perf_stats(np.asarray(np.where(mom_signal & ~vlstar_lagged.reindex(ret_0050.index).fillna(False), ret_0050, 0.0))),
        "cluster_and_vlstar_filtered": _perf_stats(np.asarray(np.where(mom_signal & ~and_lagged.reindex(ret_0050.index).fillna(False), ret_0050, 0.0))),
    }

    # Test B: Group A+ golden1/defensive switch-blend vs existing rule
    test_b = None
    if switch_curve_path.exists():
        curve = pd.read_csv(switch_curve_path)
        curve["dt"] = pd.to_datetime(curve["dt"])
        curve = curve.set_index("dt").sort_index()
        golden_ret = curve[GOLDEN_COL].pct_change()
        defensive_ret = curve[DEFENSIVE_COL].pct_change()
        rule_ret = curve[SWITCH_COL].pct_change()
        df = pd.concat(
            [
                golden_ret.rename("golden"), defensive_ret.rename("defensive"), rule_ret.rename("rule"),
                cluster_lagged.rename("cluster_flag"), vlstar_lagged.rename("vlstar_flag"),
                and_lagged.rename("and_flag"),
            ],
            axis=1,
        ).dropna()

        def _blend(flag_col: str) -> dict:
            r = np.where(df[flag_col], df["defensive"], df["golden"])
            return _perf_stats(np.asarray(r))

        rule_perf = _perf_stats(df["rule"].values)
        and_perf = _blend("and_flag")
        test_b = {
            "golden1_alone": _perf_stats(df["golden"].values),
            "existing_switch_rule": rule_perf,
            "cluster_only_switch": _blend("cluster_flag"),
            "vlstar_only_switch": _blend("vlstar_flag"),
            "cluster_and_vlstar_switch": and_perf,
            "and_volatile_share": round(float(df["and_flag"].mean()), 4),
            "cluster_volatile_share": round(float(df["cluster_flag"].mean()), 4),
            "vlstar_volatile_share": round(float(df["vlstar_flag"].mean()), 4),
        }
        test_b["and_dominates_existing_rule"] = bool(
            and_perf["sharpe"] > rule_perf["sharpe"] and and_perf["mdd"] > rule_perf["mdd"]
        )
        test_b["and_beats_both_single_detectors"] = bool(
            and_perf["sharpe"] > test_b["cluster_only_switch"]["sharpe"]
            and and_perf["sharpe"] > test_b["vlstar_only_switch"]["sharpe"]
            and and_perf["mdd"] > test_b["cluster_only_switch"]["mdd"]
            and and_perf["mdd"] > test_b["vlstar_only_switch"]["mdd"]
        )

    return {
        "paper": "arXiv:2104.03667",
        "follow_up_of": "2104_03667_regime_detection_vlstar_hierarchical_clustering",
        "status": "available_for_shadow_monitoring",
        "vlstar_transition_variable_used": selection["selected_variable"],
        "test_a_paper_momentum_validation": test_a,
        "test_b_group_a_plus_switch_check": test_b,
        "and_dominates_existing_rule_test_b": bool(test_b and test_b["and_dominates_existing_rule"]),
        "and_beats_both_single_detectors_test_b": bool(test_b and test_b["and_beats_both_single_detectors"]),
        "target_weight_change_allowed": False,
        "replace_a2118": False,
        "train_vlstar_now": False,
    }


def write_review(review: dict, output_path: Path = OUTPUT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    review = build_review()
    a = review.get("test_a_paper_momentum_validation", {})
    print("=== Test A: naive momentum(0050), single detectors vs AND-combination ===")
    for name, p in a.items():
        print(f"{name:30s} sharpe={p['sharpe']:6.3f}  mdd={p['mdd']*100:7.2f}%  ann_ret={p['ann_ret']*100:7.2f}%")

    b = review.get("test_b_group_a_plus_switch_check")
    if b:
        print(f"\n=== Test B: Group A+ switch-blend ===")
        print(f"volatile share -- cluster: {b['cluster_volatile_share']*100:.1f}%  "
              f"vlstar: {b['vlstar_volatile_share']*100:.1f}%  AND: {b['and_volatile_share']*100:.1f}%")
        for name in ("golden1_alone", "existing_switch_rule", "cluster_only_switch", "vlstar_only_switch", "cluster_and_vlstar_switch"):
            p = b[name]
            print(f"{name:26s} sharpe={p['sharpe']:6.3f}  mdd={p['mdd']*100:7.2f}%")
        print(f"\nAND dominates existing rule: {b['and_dominates_existing_rule']}")
        print(f"AND beats both single detectors: {b['and_beats_both_single_detectors']}")

    write_review(review, OUTPUT)
    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()
