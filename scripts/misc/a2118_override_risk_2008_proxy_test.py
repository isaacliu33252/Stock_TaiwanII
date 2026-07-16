#!/usr/bin/env python3
"""Does `SwitchRule.override_risk_score` (bypass MA-gap entry when risk score
+ drawdown both fire) help in a genuine crash, unlike the 2025-2026 result
(0/20 combos improved, most made things worse -- see chat 2026-07-05)?

Cannot be tested directly on the 2008 TWII proxy: `override_enter` reads
`total_risk_score`, which is chip/derivative-data-derived and proven stuck at
0 for the entire 2008 proxy window (no chip/derivative tables exist that far
back -- same root cause as GROUP_A_PLUS_A2118_CHIP_FALLBACK_HANDOFF_20260704.md).
`chip_data_fallback_max_stale_days` bypasses the *gate* that reads
total_risk_score, but does not give the score itself a real value, so
`override_risk_score>0` can never fire on this data no matter what threshold
is swept -- Part 1 below demonstrates this empirically instead of asserting
it.

Part 2 substitutes `tail_risk_score` (purely price/return-derived: historical
VaR breach + realized-vol-ratio regime flag, range 0-2, proven NOT stuck at 0
in 2008 by market_state_2008_proxy_backtest.py) for `total_risk_score` in the
override condition, as the only available like-for-like way to ask the
intended question: does bypassing the MA-gap entry when a price-derived
extreme-risk signal fires, even before drawdown/MA thresholds are hit, help
in a real crash? Baseline for this comparison is `fallback_enabled` (today's
already-promoted production fix), not `real_rule` (proven to never enter at
all on this data) or `idealized` (a different, gate-free construction).

Read-only: does not modify backtest_group_a_plus_switch_policy.py, a2111.py,
a2118.py, or any report/* file. Writes one JSON report to results/.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from twii_proxy_utils import build_group_a_twii_proxy_data  # noqa: E402
from backtest_group_a_plus_switch_policy import _regime_features, _switch_returns  # noqa: E402
from group_a_plus.runners.a2111 import _build_switch_rule  # noqa: E402

START_2008, END_2008 = "2007-07-01", "2010-12-31"
MAX_STALE_DAYS = 10
OUT = PROJECT_ROOT / "results" / "a2118_override_risk_2008_proxy_test_20260705.json"

TAIL_RISK_THRESHOLDS = [1, 2]
DRAWDOWN_THRESHOLDS = [-0.05, -0.08, -0.10, -0.15, -0.20]


def _metrics_from_curve(curve: pd.Series) -> dict:
    daily_ret = curve.pct_change().dropna()
    n_years = len(curve) / 252.0
    total_return = float(curve.iloc[-1] / curve.iloc[0] - 1.0)
    annual_return = float((curve.iloc[-1] / curve.iloc[0]) ** (1.0 / max(n_years, 1e-6)) - 1.0)
    vol = float(daily_ret.std() * (252 ** 0.5)) if len(daily_ret) > 1 else 0.0
    sharpe = float(daily_ret.mean() / daily_ret.std() * (252 ** 0.5)) if daily_ret.std() > 0 else 0.0
    running_max = curve.cummax()
    mdd = float((curve / running_max - 1.0).min())
    return {
        "final_value": float(curve.iloc[-1]),
        "total_return": total_return,
        "annual_return": annual_return,
        "volatility": vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": mdd,
    }


def _simulate(regime: pd.Series, aggressive_ret: pd.Series, defensive_ret: pd.Series) -> pd.Series:
    daily_ret = aggressive_ret.where(regime.reindex(aggressive_ret.index) == "golden1", defensive_ret)
    return (1.0 + daily_ret.fillna(0.0)).cumprod()


def _tail_risk_override_regime(
    features: pd.DataFrame,
    rule,
    *,
    override_tail_risk_score: int,
    override_drawdown_threshold: float,
) -> pd.Series:
    """Same state machine as `_switch_returns`, with chip_data_fallback
    already assumed active (chip_ok/derivative_ok/total_risk_ok all bypassed,
    matching the promoted production fix), plus an ADDITIONAL override path
    using `tail_risk_score` (price-derived, not stuck at 0 here) in place of
    the chip-derived `total_risk_score`."""
    in_defense = False
    hold_days = 0
    regimes = []
    for _dt, row in features.iterrows():
        price_enter = row["ma_gap"] <= rule.enter_ma_gap or row["drawdown"] <= rule.enter_drawdown
        override_enter = (
            int(row["tail_risk_score"]) >= override_tail_risk_score
            and float(row["drawdown"]) <= override_drawdown_threshold
        )
        enter = price_enter or override_enter  # chip/derivative/total_risk gates bypassed (fallback active)
        exit_ = row["ma_gap"] >= rule.exit_ma_gap and row["exit_momentum"] > 0.0
        if in_defense:
            hold_days += 1
            if hold_days >= rule.min_hold_days and exit_:
                in_defense = False
                hold_days = 0
        elif enter:
            in_defense = True
            hold_days = 1
        regimes.append("group_a_plus_defensive" if in_defense else "golden1")
    return pd.Series(regimes, index=features.index)


def main() -> None:
    stock_data, _market = build_group_a_twii_proxy_data(START_2008, END_2008)
    prices = pd.DataFrame(
        {
            t: pd.Series(
                stock_data[t]["close"].to_numpy(),
                index=pd.to_datetime(stock_data[t]["date"]).dt.normalize(),
            )
            for t in ("0050.TW", "00631L.TW", "00632R.TW")
        }
    ).dropna().sort_index()

    rule = _build_switch_rule()
    features = _regime_features(prices[["0050.TW"]], rule, chip_features=None)
    assert (features["total_risk_score"] == 0).all(), "expected total_risk_score stuck at 0 in 2008 proxy"

    # Part 1: empirically confirm override_risk_score (total_risk_score-based)
    # cannot fire here no matter the threshold.
    part1 = []
    for risk_score in (6, 8, 10):
        rule_variant = dataclasses.replace(
            rule, override_risk_score=risk_score, override_drawdown_threshold=-0.05,
        )
        _events, frame = _switch_returns(
            prices[["0050.TW"]], None, rule_variant, chip_data_fallback_max_stale_days=MAX_STALE_DAYS,
        )
        part1.append({
            "override_risk_score": risk_score,
            "defensive_days": int((frame["regime"] == "group_a_plus_defensive").sum()),
        })
    part1_all_identical = len({p["defensive_days"] for p in part1}) == 1

    # Baseline: fallback_enabled (today's promoted fix), no tail-risk override.
    _events_fb, frame_fb = _switch_returns(
        prices[["0050.TW"]], None, rule, chip_data_fallback_max_stale_days=MAX_STALE_DAYS,
    )
    baseline_regime = frame_fb["regime"]

    aggressive_ret = prices["00631L.TW"].pct_change()
    cash_ret = pd.Series(0.0, index=prices.index)
    inverse_ret = prices["00632R.TW"].pct_change()

    baseline_result = {
        "defensive_days": int((baseline_regime == "group_a_plus_defensive").sum()),
        "vs_cash": _metrics_from_curve(_simulate(baseline_regime, aggressive_ret, cash_ret)),
        "vs_00632r_hedge": _metrics_from_curve(_simulate(baseline_regime, aggressive_ret, inverse_ret)),
    }

    # Part 2: tail_risk_score-based override on top of the fallback-fixed rule.
    part2: list[dict[str, Any]] = []
    for tail_thr in TAIL_RISK_THRESHOLDS:
        for dd_thr in DRAWDOWN_THRESHOLDS:
            regime = _tail_risk_override_regime(
                features, rule, override_tail_risk_score=tail_thr, override_drawdown_threshold=dd_thr,
            )
            defensive_days = int((regime == "group_a_plus_defensive").sum())
            entered_earlier_days = int(((regime == "group_a_plus_defensive") & (baseline_regime != "group_a_plus_defensive")).sum())
            vs_cash = _metrics_from_curve(_simulate(regime, aggressive_ret, cash_ret))
            vs_hedge = _metrics_from_curve(_simulate(regime, aggressive_ret, inverse_ret))
            part2.append({
                "override_tail_risk_score": tail_thr,
                "override_drawdown_threshold": dd_thr,
                "defensive_days": defensive_days,
                "defensive_days_delta_vs_baseline": defensive_days - baseline_result["defensive_days"],
                "extra_defensive_days_not_in_baseline": entered_earlier_days,
                "vs_cash": vs_cash,
                "vs_00632r_hedge": vs_hedge,
                "delta_vs_baseline": {
                    "vs_cash_final_value": vs_cash["final_value"] - baseline_result["vs_cash"]["final_value"],
                    "vs_cash_max_drawdown": vs_cash["max_drawdown"] - baseline_result["vs_cash"]["max_drawdown"],
                    "vs_hedge_final_value": vs_hedge["final_value"] - baseline_result["vs_00632r_hedge"]["final_value"],
                    "vs_hedge_max_drawdown": vs_hedge["max_drawdown"] - baseline_result["vs_00632r_hedge"]["max_drawdown"],
                },
            })

    result = {
        "experiment": "a2118_override_risk_2008_proxy_test",
        "window": {"start": START_2008, "end": END_2008},
        "part1_total_risk_score_override_cannot_fire": {
            "variants": part1,
            "all_identical": part1_all_identical,
            "conclusion": "override_risk_score (total_risk_score-based) is untestable on 2008 proxy: total_risk_score stuck at 0 regardless of threshold, same root cause as the chip-data-outage gap fix.",
        },
        "baseline_fallback_enabled": baseline_result,
        "part2_tail_risk_score_override": part2,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
