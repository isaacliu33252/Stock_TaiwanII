#!/usr/bin/env python3
"""Worst-case-perturbation robustness check for `total_risk_score` gate thresholds.

Research-only. Does not update the latest strategy, live signal, or any
allocation file.

Motivated by arXiv:2601.04062v3 ("Smart Predict-then-Optimize Paradigm for
Portfolio Optimization in Real Markets"), whose RobustSPO variant trains
decisions to survive worst-case perturbations of the underlying predicted
signal (rather than trusting a point estimate), and shows this materially
improves crisis-period decision quality. This project's threshold gates on
`total_risk_score` (>=9 in `daily_signal.py::_apply_bearish_high_risk_trim`,
>=9 in `specialist_router.py`, >=8 in `trough_nowcast.py`, >=6/>=7 in
`market_state.py`, >=6 in a2110/a218/a219) are the closest analogue to the
paper's decision layer, but they are hard integer thresholds on a composite
score, not a differentiable optimization solve -- so the paper's literal
SPO+/PyEPO gradient method does not transfer. This script instead adapts the
*diagnostic* idea: `total_risk_score` is itself a sum of 14 independent
binary sub-indicators (12 chip + 2 derivative, see
`backtest_group_a_plus_switch_policy.py::_regime_features`), so its natural
"prediction noise" is discrete -- any single sub-indicator flipping (due to
data lag, a borderline rolling-quantile crossing, revision, etc.) moves the
score by exactly 1. We treat that as the perturbation set (a direct discrete
analogue of the paper's `zeta` uncertainty set) and ask two questions a
point-estimate backtest cannot answer on its own:

  1. Margin-to-boundary: when a gate historically fired, how often did it do
     so by the minimum possible margin (score == threshold, one flip away
     from not firing) vs. comfortably (score >= threshold + 2)?
  2. Regret proxy: do "marginal" (score == threshold) trigger days still
     carry a meaningfully worse forward 0050 return than non-trigger days,
     or is their forward-return signal statistically indistinguishable from
     noise -- i.e. is the gate's edge concentrated in its comfortable
     triggers, with the marginal ones adding false-positive cost rather than
     protection?

This does not change any threshold, does not retrain anything, and does not
touch `_apply_bearish_high_risk_trim` or any other production gate. It is a
read-only diagnostic over historical data already used by
`backtest_group_a_plus_switch_policy.py`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import (  # noqa: E402
    DB_PATH,
    RULES,
    _load_chip_features,
    _load_prices,
    _regime_features,
)

SUB_INDICATOR_COLUMNS = [
    "chip_inst_risk",
    "chip_foreign_risk",
    "chip_margin_risk",
    "chip_market_margin_risk",
    "chip_tdcc_risk",
    "chip_foreign_shareholding_risk",
    "chip_short_balance_risk",
    "chip_securities_lending_risk",
    "chip_day_trading_risk",
    "chip_dealer_tx_risk",
    "chip_dealer_txo_risk",
    "smart_money_cost_risk",
    "derivative_futures_foreign_risk",
    "derivative_options_foreign_risk",
]

# (threshold, production callsite) -- for reference in the report only.
PRODUCTION_THRESHOLDS = [
    (9, "daily_signal.py::_apply_bearish_high_risk_trim, specialist_router.py"),
    (8, "trough_nowcast.py"),
    (7, "market_state.py::bear_breakdown"),
    (6, "market_state.py, a2110/a218/a219 entry gates"),
]


def _load_history(start: str, end: str) -> tuple[pd.DataFrame, pd.Series]:
    # _regime_features only reads the "0050.TW" column, so load 0050.TW alone
    # rather than reusing the production backtest's full TICKERS join (which
    # requires 00631L.TW/00632R.TW/00679B.TWO to all have data too --
    # 00679B.TWO didn't IPO until 2017-01-11, which would otherwise floor
    # this diagnostic's usable history at 2017 even though 0050.TW itself
    # trades back to 2009-01-02).
    prices = _load_prices(DB_PATH, ["0050.TW"], start, end)
    chip_features = _load_chip_features(DB_PATH, prices.index, start, end)
    # total_risk_score's components don't depend on the SwitchRule's MA/
    # drawdown params, so any rule works here; pick one that already uses
    # total_risk_score in production for a realistic reference point.
    rule = next(r for r in RULES if r.name == "risk_ma90_dd12_total6_hold5")
    features = _regime_features(prices, rule, chip_features)
    return features, prices["0050.TW"].astype(float)


def _yearly_score_ceiling_report(features: pd.DataFrame) -> pd.DataFrame:
    """`total_risk_score`'s 14 sub-indicators were onboarded in phases as
    their underlying source tables came online (market_margin_data from
    2007, tdcc/shareholding_distribution from 2015, derivative_institutional_
    data from 2018-06, institutional_data/margin_data from 2020-01,
    dealer_futures_data/dealer_options_data/day_trading_data/securities_
    lending_data/foreign_shareholding_data only from 2025-01). Before all
    sources are live, `_load_chip_features` silently fills missing columns
    with 0.0, so the score's *practical ceiling* -- not just its observed
    value -- rises over time. A low/zero score in an early year can mean
    "calm market" or "most sub-indicators didn't exist yet"; this yearly
    max/mean table makes that visible instead of silently biasing any
    cross-year threshold comparison.
    """
    yearly = features.assign(year=features.index.year).groupby("year")["total_risk_score"]
    return yearly.agg(["max", "mean", "count"]).round(2)


def _fired_mask(score: pd.Series, threshold: int, persistence_days: int) -> pd.Series:
    """True on day t if score has been >= threshold for `persistence_days`
    consecutive days ending at t (persistence_days=1 reproduces the current
    same-day production gate behavior).
    """
    meets = score >= threshold
    if persistence_days <= 1:
        return meets
    return meets.rolling(persistence_days, min_periods=persistence_days).sum() == persistence_days


def _episode_count(fired: pd.Series) -> int:
    """Number of contiguous fired-day runs (rising edges), not raw day count."""
    fired_int = fired.astype(int)
    return int(((fired_int == 1) & (fired_int.shift(1, fill_value=0) == 0)).sum())


def _margin_to_boundary_report(features: pd.DataFrame, threshold: int, persistence_days: int = 1) -> dict:
    score = features["total_risk_score"]
    fired = _fired_mask(score, threshold, persistence_days)
    n_fired = int(fired.sum())
    margin = (score - threshold)[fired]
    return {
        "threshold": threshold,
        "persistence_days": persistence_days,
        "total_days": int(len(score)),
        "days_fired": n_fired,
        "episodes_fired": _episode_count(fired),
        "fired_pct_of_history": round(100.0 * n_fired / len(score), 2) if len(score) else 0.0,
        "fired_at_exact_threshold_pct": round(100.0 * (margin == 0).mean(), 1) if n_fired else None,
        "fired_with_margin_ge2_pct": round(100.0 * (margin >= 2).mean(), 1) if n_fired else None,
        "score_histogram": {int(k): int(v) for k, v in score.value_counts().sort_index().items()},
    }


def _perturbation_flip_probability(
    features: pd.DataFrame, threshold: int, flip_prob: float, n_trials: int, seed: int, persistence_days: int = 1
) -> pd.DataFrame:
    """For each historical day, Monte-Carlo flip each of the 14 binary
    sub-indicators independently with probability `flip_prob` (drawn fresh
    per day, since each day's chip/derivative source noise is independent),
    recompute the perturbed total_risk_score and the resulting persistence-
    aware fire decision, and report P(gate decision flips) grouped by the
    day's original same-day margin-to-threshold (score - threshold).
    """
    rng = np.random.default_rng(seed)
    sub = features[SUB_INDICATOR_COLUMNS].to_numpy(dtype=int)  # (n_days, 14)
    score = pd.Series(sub.sum(axis=1), index=features.index)
    original_fired = _fired_mask(score, threshold, persistence_days).to_numpy()

    n_days, n_ind = sub.shape
    flip_count = np.zeros(n_days, dtype=np.int64)
    for _ in range(n_trials):
        flips = rng.random((n_days, n_ind)) < flip_prob
        perturbed_score = pd.Series(np.logical_xor(sub.astype(bool), flips).sum(axis=1), index=features.index)
        perturbed_fired = _fired_mask(perturbed_score, threshold, persistence_days).to_numpy()
        flip_count += (perturbed_fired != original_fired).astype(np.int64)

    flip_rate = flip_count / n_trials
    margin = score.to_numpy() - threshold
    out = pd.DataFrame(
        {"margin": margin, "original_fired": original_fired, "decision_flip_rate": flip_rate},
        index=features.index,
    )
    return out


def _regret_proxy_report(features: pd.DataFrame, prices_0050: pd.Series, threshold: int, persistence_days: int = 1) -> dict:
    fwd_5d = prices_0050.pct_change(5).shift(-5).reindex(features.index)
    fwd_20d = prices_0050.pct_change(20).shift(-20).reindex(features.index)
    score = features["total_risk_score"]
    fired = _fired_mask(score, threshold, persistence_days)

    marginal = fired & (score == threshold)
    clear = fired & (score >= threshold + 2)
    never_fired = ~fired

    def _stats(mask: pd.Series) -> dict:
        f5 = fwd_5d[mask].dropna()
        f20 = fwd_20d[mask].dropna()
        return {
            "n_days": int(mask.sum()),
            "mean_fwd_5d_return_pct": round(100.0 * f5.mean(), 3) if len(f5) else None,
            "mean_fwd_20d_return_pct": round(100.0 * f20.mean(), 3) if len(f20) else None,
        }

    return {
        "threshold": threshold,
        "marginal_trigger_days (score == threshold)": _stats(marginal),
        "clear_trigger_days (score >= threshold + 2)": _stats(clear),
        "never_fired_days (score < threshold)": _stats(never_fired),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", default="2009-01-01", help="Full available 0050.TW price history starts 2009-01-02.")
    parser.add_argument("--end", default="2026-07-01")
    parser.add_argument("--thresholds", type=int, nargs="+", default=[9, 8, 7, 6])
    parser.add_argument("--flip-prob", type=float, default=0.15, help="Per-sub-indicator flip probability for the Monte Carlo perturbation.")
    parser.add_argument("--n-trials", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--persistence-days",
        type=int,
        default=1,
        help="Require score >= threshold for N consecutive days before firing (1 = current production same-day behavior).",
    )
    parser.add_argument("--output", default=None, help="Optional path to write the full JSON report.")
    args = parser.parse_args()

    print(f"Loading history {args.start} -> {args.end} ...", file=sys.stderr)
    features, prices_0050 = _load_history(args.start, args.end)

    report: dict = {
        "config": {
            "start": args.start,
            "end": args.end,
            "flip_prob": args.flip_prob,
            "n_trials": args.n_trials,
            "seed": args.seed,
            "persistence_days": args.persistence_days,
            "note": "total_risk_score = chip_score (12 binary sub-indicators) + derivative_score (2 binary sub-indicators)",
        },
        "production_thresholds_reference": PRODUCTION_THRESHOLDS,
        "per_threshold": {},
    }

    yearly_ceiling = _yearly_score_ceiling_report(features)
    print("\n=== total_risk_score ceiling by year (data-coverage context) ===")
    print(yearly_ceiling.to_string())
    print(
        "NOTE: sub-indicator source tables were onboarded in phases (see script\n"
        "docstring / _yearly_score_ceiling_report). Years before full 14-indicator\n"
        "coverage (2025-01 onward) have a structurally lower score ceiling -- low\n"
        "scores there are not necessarily 'calm market'."
    )
    report["yearly_score_ceiling"] = {
        str(k): {kk: (None if pd.isna(vv) else vv) for kk, vv in v.items()} for k, v in yearly_ceiling.to_dict(orient="index").items()
    }

    for threshold in args.thresholds:
        print(f"\n=== threshold = {threshold}, persistence_days = {args.persistence_days} ===")
        margin_report = _margin_to_boundary_report(features, threshold, args.persistence_days)
        print(
            f"  fired {margin_report['days_fired']}/{margin_report['total_days']} days "
            f"({margin_report['fired_pct_of_history']}%) across {margin_report['episodes_fired']} episodes; "
            f"of fired days, {margin_report['fired_at_exact_threshold_pct']}% were at the exact "
            f"threshold (one sub-indicator flip from not firing), "
            f"{margin_report['fired_with_margin_ge2_pct']}% had margin >= 2."
        )

        flip_df = _perturbation_flip_probability(
            features, threshold, args.flip_prob, args.n_trials, args.seed, args.persistence_days
        )
        by_margin = (
            flip_df[flip_df["margin"].between(-3, 3)]
            .groupby("margin")["decision_flip_rate"]
            .mean()
            .round(3)
        )
        print("  P(decision flips under perturbation) by same-day margin-to-threshold:")
        for m, p in by_margin.items():
            print(f"    margin={int(m):+d}: flip_rate={p}")

        regret = _regret_proxy_report(features, prices_0050, threshold, args.persistence_days)
        print("  Forward-return regret proxy:")
        for key in (
            "marginal_trigger_days (score == threshold)",
            "clear_trigger_days (score >= threshold + 2)",
            "never_fired_days (score < threshold)",
        ):
            s = regret[key]
            print(f"    {key}: n={s['n_days']}, fwd_5d={s['mean_fwd_5d_return_pct']}%, fwd_20d={s['mean_fwd_20d_return_pct']}%")

        report["per_threshold"][threshold] = {
            "margin_to_boundary": margin_report,
            "decision_flip_rate_by_margin": {int(k): float(v) for k, v in by_margin.items()},
            "regret_proxy": regret,
        }

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nWrote full report to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
