#!/usr/bin/env python3
"""Second follow-up to arXiv:2104.03667 (see
build_group_a_plus_2104_03667_regime_clustering_review.py and
docs/HANDOFF_2104_03667_REGIME_CLUSTERING_VLSTAR_GROUPA_PLUS_20260827.md).

The original review's VLSTAR-lite proxy used trailing realized volatility of
0050 as the (single) transition variable, chosen without testing
alternatives. The paper's actual VLSTAR method selects its transition
variable via a linearity test across candidates ("test linearity for each of
the potential variables and select the one exhibiting the lowest p-value") --
NOT by backtest performance. This follow-up reproduces that selection
principle: it picks among Group A+'s already-computed regime-relevant
features (ma_gap, drawdown, realized_vol_0050_20d, tail_risk_score,
total_risk_score -- all already columns in the existing switch policy's
recommended-regime feature file) using a simple, non-performance selection
statistic (correlation with next-day realized volatility, a proxy for "this
variable predicts the kind of regime shift VLSTAR is meant to detect"), then
builds ONE VLSTAR-lite detector on the selected variable using the paper's
own un-tuned default (gamma_scale=3.0, threshold=0.5 -- NOT the
sensitivity-sweep-selected values from the prior follow-up, to avoid
compounding that sweep's overfitting risk) and evaluates it exactly like the
original review's Test A / Test B.

This deliberately does NOT select the transition variable by Sharpe/MDD --
doing so would just be a second multiple-comparison search layered on top of
the first (see feedback_overfitting_fixed_window_tuning).

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
    SWITCH_CURVE,
    SWITCH_COL,
    _apply_min_hold,
    _load_close,
    _perf_stats,
)

REGIME_FEATURES_CSV = PROJECT_ROOT / "results" / "whatif_four_axis_switch_backtest_20260819_recommended_regime.csv"
OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2104_03667_transition_variable_selection.json"

DEFAULT_GAMMA_SCALE = 3.0  # paper-default, un-tuned -- deliberately NOT the sweep-selected values
DEFAULT_THRESHOLD = 0.5

# (column, sign) -- sign flips a variable so that "higher = more stress",
# matching the paper's convention that G_t > threshold means the volatile
# regime. Determined once from the existing rule's own golden1 vs
# group_a_plus_defensive feature means (golden1 has higher ma_gap and higher
# drawdown i.e. less negative; defensive has lower/more negative both).
CANDIDATE_VARIABLES = {
    "neg_ma_gap": ("ma_gap", -1.0),
    "neg_drawdown": ("drawdown", -1.0),
    "realized_vol_0050_20d": ("realized_vol_0050_20d", 1.0),
    "tail_risk_score": ("tail_risk_score", 1.0),
    "total_risk_score": ("total_risk_score", 1.0),
}


def _select_transition_variable(features: pd.DataFrame, close_0050: pd.Series) -> dict:
    """Non-performance selection: correlation of each (signed) candidate
    with next-day squared 0050 return (a realized-volatility proxy). This
    mirrors the paper's own linearity-test selection principle -- pick by a
    statistical association with volatility regime shifts, not by trading
    performance."""
    ret = np.log(close_0050 / close_0050.shift(1)).dropna()
    next_day_sq_ret = (ret.shift(-1) ** 2).reindex(features.index)

    scores = {}
    for name, (col, sign) in CANDIDATE_VARIABLES.items():
        signed = sign * features[col]
        aligned = pd.concat([signed.rename("x"), next_day_sq_ret.rename("y")], axis=1).dropna()
        if len(aligned) < 30:
            scores[name] = None
            continue
        corr = float(aligned["x"].corr(aligned["y"]))
        scores[name] = corr

    valid = {k: v for k, v in scores.items() if v is not None}
    selected = max(valid, key=valid.get) if valid else None
    return {"scores": scores, "selected_variable": selected, "selection_criterion":
            "pearson_corr(signed_candidate_t, 0050_squared_return_t+1) -- higher = more predictive of near-term volatility"}


def _causal_vlstar_lite(signal: pd.Series, gamma_scale: float, threshold: float) -> pd.Series:
    """Same causal logistic smooth-transition construction as the original
    review's _vlstar_lite_g/_vlstar_lite_regime, generalized to any single
    already-signed transition-variable series (higher = more stress)."""
    g = pd.Series(index=signal.index, dtype=float)
    min_window = 252
    for i, dt in enumerate(signal.index):
        if i < min_window:
            g.loc[dt] = 0.0
            continue
        history = signal.iloc[: i + 1]
        c_t = history.median()
        scale = history.std()
        gamma = gamma_scale / scale if scale > 1e-8 else 0.0
        s_t = signal.iloc[i]
        g.loc[dt] = 1.0 / (1.0 + np.exp(-gamma * (s_t - c_t)))
    return g > threshold


def build_review(
    db_path: Path = DB_PATH,
    regime_features_path: Path = REGIME_FEATURES_CSV,
    switch_curve_path: Path = SWITCH_CURVE,
    core_tickers: tuple[str, ...] = CORE_TICKERS,
    gamma_scale: float = DEFAULT_GAMMA_SCALE,
    threshold: float = DEFAULT_THRESHOLD,
    min_hold_days: int = MIN_HOLD_DAYS,
) -> dict:
    if not regime_features_path.exists():
        return {
            "status": "blocked",
            "blocking_reasons": ["regime_features_csv_missing"],
            "target_weight_change_allowed": False,
        }
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
    selected_name = selection["selected_variable"]
    if selected_name is None:
        return {"status": "blocked", "blocking_reasons": ["no_valid_candidate_variable"], "target_weight_change_allowed": False}
    col, sign = CANDIDATE_VARIABLES[selected_name]
    signal = sign * features[col]

    raw = _causal_vlstar_lite(signal, gamma_scale=gamma_scale, threshold=threshold)
    daily = raw.reindex(close.index).fillna(False).astype(bool)
    daily = _apply_min_hold(daily, min_hold_days)
    lagged = daily.shift(1).fillna(False).astype(bool)

    # Test A: paper's own naive momentum(0050) filter validation.
    # Restrict to dates >= the regime-features CSV's own start: before that,
    # `lagged` is trivially False via reindex/fillna (no feature data to
    # evaluate the transition variable), which would silently understate any
    # comparison by diluting it with years where the filter could not
    # possibly fire -- not a real "detected calm" period. See
    # build_group_a_plus_2104_03667_momentum_filter_year_split_validation.py
    # for the discovery and the fuller year-by-year consequence.
    ret_0050_full = np.log(close["0050.TW"] / close["0050.TW"].shift(1)).dropna()
    ret_0050 = ret_0050_full.loc[ret_0050_full.index >= features.index.min()]
    mom_signal = (
        (close["0050.TW"].pct_change(20) > 0).reindex(ret_0050.index).fillna(False).astype(bool)
        .shift(1).fillna(False).astype(bool)
    )
    unfiltered_ret = np.where(mom_signal, ret_0050, 0.0)
    lagged_a = lagged.reindex(ret_0050.index).fillna(False).astype(bool)
    filtered_ret = np.where(mom_signal & ~lagged_a, ret_0050, 0.0)
    test_a = {
        "baseline_unfiltered": _perf_stats(np.asarray(unfiltered_ret)),
        "selected_variable_filtered": _perf_stats(np.asarray(filtered_ret)),
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
            [golden_ret.rename("golden"), defensive_ret.rename("defensive"), rule_ret.rename("rule"),
             lagged.rename("defensive_flag")],
            axis=1,
        ).dropna()
        detector_ret = np.where(df["defensive_flag"], df["defensive"], df["golden"])
        test_b = {
            "golden1_alone": _perf_stats(df["golden"].values),
            "existing_switch_rule": _perf_stats(df["rule"].values),
            "selected_variable_switch": _perf_stats(np.asarray(detector_ret)),
            "volatile_share": round(float(df["defensive_flag"].mean()), 4),
        }
        test_b["dominates_existing_rule"] = bool(
            test_b["selected_variable_switch"]["sharpe"] > test_b["existing_switch_rule"]["sharpe"]
            and test_b["selected_variable_switch"]["mdd"] > test_b["existing_switch_rule"]["mdd"]
        )

    return {
        "paper": "arXiv:2104.03667",
        "follow_up_of": "2104_03667_regime_detection_vlstar_hierarchical_clustering",
        "status": "available_for_shadow_monitoring",
        "gamma_scale": gamma_scale,
        "threshold": threshold,
        "transition_variable_selection": selection,
        "test_a_paper_momentum_validation": test_a,
        "test_b_group_a_plus_switch_check": test_b,
        "any_variable_dominates_existing_rule_test_b": bool(test_b and test_b["dominates_existing_rule"]),
        "target_weight_change_allowed": False,
        "replace_a2118": False,
        "train_vlstar_now": False,
    }


def write_review(review: dict, output_path: Path = OUTPUT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    review = build_review()
    sel = review.get("transition_variable_selection", {})
    print("=== Transition variable selection (non-performance, linearity-test-style) ===")
    for name, score in sel.get("scores", {}).items():
        marker = " <== selected" if name == sel.get("selected_variable") else ""
        print(f"{name:26s} corr={score if score is not None else float('nan'):+.4f}{marker}")

    a = review.get("test_a_paper_momentum_validation", {})
    if a:
        print("\n=== Test A: naive momentum(0050) unfiltered vs selected-variable-filtered ===")
        for name, p in a.items():
            print(f"{name:28s} sharpe={p['sharpe']:6.3f}  mdd={p['mdd']*100:7.2f}%  ann_ret={p['ann_ret']*100:7.2f}%")

    b = review.get("test_b_group_a_plus_switch_check")
    if b:
        print(f"\n=== Test B: Group A+ switch-blend (selected variable's volatile share: {b['volatile_share']*100:.1f}%) ===")
        for name in ("golden1_alone", "existing_switch_rule", "selected_variable_switch"):
            p = b[name]
            print(f"{name:24s} sharpe={p['sharpe']:6.3f}  mdd={p['mdd']*100:7.2f}%")
        print(f"\ndominates existing rule (both sharpe & mdd better): {b['dominates_existing_rule']}")

    write_review(review, OUTPUT)
    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()
