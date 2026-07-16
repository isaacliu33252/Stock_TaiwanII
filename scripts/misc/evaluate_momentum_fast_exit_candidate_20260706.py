#!/usr/bin/env python3
"""Candidate fast-exit fix for the 2020 V-shaped-rebound final-value drag (2026-07-06).

Direct feature inspection of the 2020-03-09..2020-04-17 defensive window
(risk-score-lookback(5) candidate) found: `exit_momentum` (5-day 0050
return) turned positive on 2020-03-25 (+5.6%) and spiked to +12.6% on
2020-03-26 -- three full weeks before `ma_gap` (100-day MA gap) finally
cleared the existing `exit_ma_gap=0.01` exit threshold on 2020-04-17. The
existing exit condition requires `ma_gap >= exit_ma_gap AND exit_momentum >
0` (both same-day) -- during a fast V-shaped rebound, momentum recovers far
faster than a 100-day moving-average gap ever can, so the rule is
structurally slow to release defensive exposure exactly when it costs the
most (missing early rebound days). This mirrors the entry-side timing
defect the risk-score-lookback fix (2026-07-06) already addressed, but on
the exit side.

Candidate: add an independent fast-exit path -- exit immediately (once
`min_hold_days` is satisfied) if `exit_momentum >= momentum_fast_exit_min`,
regardless of `ma_gap`. This is an OR alongside the existing exit condition,
not a replacement.

Risk this is designed to catch: 2008 and 2011 were prolonged, multi-legged
declines with real bear-market relief rallies (dead-cat bounces). A
momentum-only fast exit could fire mid-decline on one of those rallies and
re-enter golden1 right before the next leg down, which would hurt the
2008/2011 folds' currently-clean results. Every threshold below is tested
across all six windows (five crisis folds + current live 2025-2026) for
exactly this reason -- a fix that only helps 2020 while breaking 2008 is not
an improvement.

Research-only. Does not touch any production file, model weight, live
signal, or allocation.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_a_plus_defensive_basket import DEFENSIVE_BASKETS, _recovery_ramp_regime
from backtest_group_a_plus_policy_signal import (
    DEFAULT_DECISION_POINTER,
    TICKERS,
    _load,
    _load_policy_signal,
    _normalize,
    _resolve,
    _weights_from_group_a,
    _weights_from_group_a_plus,
)
from backtest_group_a_plus_switch_policy import (
    DB_PATH,
    SwitchRule,
    _chip_data_is_stale,
    _load_chip_features,
    _load_prices,
    _metrics,
    _regime_features,
    _simulate_regime_curve,
)
from backtest_group_a_plus_warmup_consistency import _warmup_start
from group_a_plus.runners.a2111 import _build_switch_rule, _resolve_golden_signal_path
from scripts.misc.backtest_group_a_plus_latest_vs_golden1_0531_five_crises_20260706 import (
    FOLDS,
    _load_fold_data,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INITIAL_VALUE = 1_000_000.0
CHIP_DATA_FALLBACK_MAX_STALE_DAYS = 10
RISK_LOOKBACK_DAYS = 5  # fixed at the already-established value
MOMENTUM_FAST_EXIT_CANDIDATES = [None, 0.06, 0.08, 0.10, 0.12]  # None = no fast-exit path (baseline)


def _switch_returns_risk_lookback_momentum_exit(
    prices: pd.DataFrame,
    chip_features: pd.DataFrame | None,
    rule: SwitchRule,
    lookback_days: int,
    momentum_fast_exit_min: float | None,
    chip_data_fallback_max_stale_days: int | None = None,
    momentum_fast_exit_ma_gap_min: float | None = None,
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """`momentum_fast_exit_ma_gap_min` (2026-07-06 refinement): direct inspection
    found the pure-momentum fast exit fires on 2008-11-03 (+14.4% 5d return,
    HIGHER than 2020-03-26's +12.6% that we actually want) -- a well-known
    dead-cat-bounce deep inside the 2008 bear market (ma_gap=-23.7%,
    drawdown=-39.2% that day), which momentum magnitude alone cannot tell
    apart from a genuine V-shaped recovery (2020-03-26: ma_gap=-4.4%,
    drawdown=-21.7% -- a much shallower context). When set, the fast-exit
    path additionally requires `ma_gap >= momentum_fast_exit_ma_gap_min`,
    i.e. "close enough to trend" that a momentum burst is more likely a real
    recovery than a rally inside a still-deep bear market.
    """
    features = _regime_features(prices, rule, chip_features)
    window = max(int(lookback_days), 1)
    features["total_risk_score_lookback_max"] = (
        features["total_risk_score"].rolling(window, min_periods=1).max()
    )

    in_defense = False
    hold_days = 0
    events: list[dict[str, Any]] = []
    regimes = []
    for dt, row in features.iterrows():
        price_enter = row["ma_gap"] <= rule.enter_ma_gap or row["drawdown"] <= rule.enter_drawdown
        cost_enter = False
        if rule.enter_cost_gap_below is not None:
            cost_enter = cost_enter or float(row["smart_money_cost_gap_20d"]) <= float(rule.enter_cost_gap_below)
        if rule.enter_cost_gap_above is not None:
            cost_enter = cost_enter or float(row["smart_money_cost_gap_20d"]) >= float(rule.enter_cost_gap_above)
        override_enter = (
            rule.override_risk_score > 0
            and int(row["total_risk_score"]) >= int(rule.override_risk_score)
            and float(row["drawdown"]) <= float(rule.override_drawdown_threshold)
        )
        tail_override_enter = False
        if rule.override_tail_risk_score > 0 and int(row["tail_risk_score"]) >= int(rule.override_tail_risk_score):
            tail_drawdown_enter = float(row["drawdown"]) <= float(rule.override_tail_drawdown_threshold)
            tail_var_enter = bool(
                rule.override_tail_use_var_breach
                and float(row["return_0050_1d"]) <= float(row["hist_var_0050_20d_5pct"])
            )
            tail_override_enter = tail_drawdown_enter or tail_var_enter
        chip_ok = int(row["chip_score"]) >= int(rule.require_chip_score)
        derivative_ok = int(row["derivative_score"]) >= int(rule.require_derivative_score)
        total_risk_ok = int(row["total_risk_score_lookback_max"]) >= int(rule.require_total_risk_score)
        tail_risk_ok = int(row["tail_risk_score"]) >= int(rule.require_tail_risk_score)
        fallback_days_since_update = row.get(
            "chip_data_core_days_since_source_update",
            row.get("chip_data_days_since_source_update", 0),
        )
        if chip_data_fallback_max_stale_days is not None and _chip_data_is_stale(
            fallback_days_since_update, chip_data_fallback_max_stale_days
        ):
            chip_ok = True
            derivative_ok = True
            total_risk_ok = True
        enter = (
            ((price_enter or cost_enter or override_enter) and chip_ok and derivative_ok and total_risk_ok and tail_risk_ok)
            or tail_override_enter
        )
        effective_exit_ma_gap = rule.exit_ma_gap
        if (
            rule.low_risk_exit_ma_gap is not None
            and int(row["total_risk_score"]) <= int(rule.low_risk_exit_score_threshold)
        ):
            effective_exit_ma_gap = rule.low_risk_exit_ma_gap
        base_exit = row["ma_gap"] >= effective_exit_ma_gap and row["exit_momentum"] > 0.0
        momentum_fast_exit = (
            momentum_fast_exit_min is not None and float(row["exit_momentum"]) >= float(momentum_fast_exit_min)
        )
        if momentum_fast_exit and momentum_fast_exit_ma_gap_min is not None:
            momentum_fast_exit = float(row["ma_gap"]) >= float(momentum_fast_exit_ma_gap_min)
        exit_ = base_exit or momentum_fast_exit

        if in_defense:
            hold_days += 1
            if hold_days >= rule.min_hold_days and exit_:
                in_defense = False
                hold_days = 0
                events.append({
                    "date": str(dt.date()),
                    "action": "switch_to_golden",
                    "via_momentum_fast_exit": bool(momentum_fast_exit and not base_exit),
                })
        elif enter:
            in_defense = True
            hold_days = 1
            events.append({"date": str(dt.date()), "action": "switch_to_group_a_plus_defensive"})
        regimes.append("group_a_plus_defensive" if in_defense else "golden1")

    regime_frame = features.copy()
    regime_frame["regime"] = regimes
    return events, regime_frame


def _run_curve(
    prices: pd.DataFrame,
    chip_features: pd.DataFrame,
    rule: SwitchRule,
    momentum_fast_exit_min: float | None,
    golden_weights: dict[str, float],
    basket: dict[str, float],
    current_defensive: dict[str, float],
) -> tuple[pd.Series, pd.Series, list[dict[str, Any]]]:
    events, frame = _switch_returns_risk_lookback_momentum_exit(
        prices, chip_features, rule, RISK_LOOKBACK_DAYS, momentum_fast_exit_min,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    )
    execution_regime = _recovery_ramp_regime(frame["regime"], frame)
    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": basket,
        "group_a_plus_recovery": current_defensive,
    }
    curve = _simulate_regime_curve(prices, execution_regime, weights_by_regime, INITIAL_VALUE)
    return curve, execution_regime, events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="results/group_a_plus_momentum_fast_exit_candidate_20260706.json")
    args = parser.parse_args()

    db_path = _resolve(str(DB_PATH))
    policy_signal, _ = _load_policy_signal(_resolve(str(DEFAULT_DECISION_POINTER)))
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
    basket = _normalize(DEFENSIVE_BASKETS["bond30_cash30"])
    latest_golden_signal = _load(_resolve_golden_signal_path())
    latest_golden_weights = _normalize(_weights_from_group_a(latest_golden_signal))
    rule = _build_switch_rule()

    windows: dict[str, dict[str, Any]] = dict(FOLDS)
    live_start = "2025-01-02"
    live_load_start = _warmup_start(live_start, 180)
    live_full_prices = _load_prices(db_path, list(TICKERS), live_load_start, "2026-07-03")
    live_full_chip = _load_chip_features(db_path, live_full_prices.index, live_load_start, "2026-07-03")

    results: dict[str, Any] = {
        "prepared_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": (
            "test an independent momentum-based fast-exit path (on top of the already-"
            "established risk-score-lookback(5) entry fix) to see if it recovers the 2020 "
            "final-value drag without causing premature bear-rally exits in 2008/2011 or "
            "whipsaw in the current live window"
        ),
        "risk_lookback_days": RISK_LOOKBACK_DAYS,
        "momentum_fast_exit_candidates": [c for c in MOMENTUM_FAST_EXIT_CANDIDATES],
        "windows": {},
    }

    for name, spec in windows.items():
        prices, chip_features = _load_fold_data(name, spec, db_path)
        report_start = spec["report_start"]
        report_end = spec["report_end"]

        window_result: dict[str, Any] = {"label": spec["label"], "momentum_fast_exit_min": {}}
        for m in MOMENTUM_FAST_EXIT_CANDIDATES:
            curve, execution_regime, events = _run_curve(
                prices, chip_features, rule, m, latest_golden_weights, basket, current_defensive
            )
            report_curve = curve.loc[report_start:] if report_end is None else curve.loc[report_start:report_end]
            report_regime = execution_regime.loc[report_curve.index]
            defensive_days = int((report_regime == "group_a_plus_defensive").sum())
            fast_exit_events = [e for e in events if e.get("via_momentum_fast_exit")]
            key = "none" if m is None else str(m)
            window_result["momentum_fast_exit_min"][key] = {
                "metrics": _metrics(report_curve, float(report_curve.iloc[0])),
                "defensive_days": defensive_days,
                "fast_exit_event_count": len(fast_exit_events),
                "fast_exit_dates": [e["date"] for e in fast_exit_events],
            }
        results["windows"][name] = window_result

    live_window_result: dict[str, Any] = {"label": "Current live 2025-01-02..2026-07-03 (real data)", "momentum_fast_exit_min": {}}
    for m in MOMENTUM_FAST_EXIT_CANDIDATES:
        curve, execution_regime, events = _run_curve(
            live_full_prices, live_full_chip, rule, m, latest_golden_weights, basket, current_defensive
        )
        report_curve = curve.loc[live_start:]
        report_regime = execution_regime.loc[report_curve.index]
        defensive_days = int((report_regime == "group_a_plus_defensive").sum())
        fast_exit_events = [e for e in events if e.get("via_momentum_fast_exit")]
        key = "none" if m is None else str(m)
        live_window_result["momentum_fast_exit_min"][key] = {
            "metrics": _metrics(report_curve, float(report_curve.iloc[0])),
            "defensive_days": defensive_days,
            "fast_exit_event_count": len(fast_exit_events),
            "fast_exit_dates": [e["date"] for e in fast_exit_events],
        }
    results["windows"]["live_2025_2026"] = live_window_result

    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Output: {output_path}")
    print()
    header = f"{'Window':<20} {'MomExitMin':>11} {'FinalValue':>14} {'TotalRet':>10} {'Sharpe':>8} {'MDD':>8} {'DefDays':>8} {'FastExits':>9}"
    print(header)
    print("-" * len(header))
    for name, window_result in results["windows"].items():
        for key, r in window_result["momentum_fast_exit_min"].items():
            m = r["metrics"]
            print(
                f"{name:<20} {key:>11} {m['final_value']:>14,.0f} {m['total_return']:>10.2%} "
                f"{m['sharpe_ratio']:>8.3f} {m['max_drawdown']:>8.2%} {r['defensive_days']:>8} {r['fast_exit_event_count']:>9}"
            )


if __name__ == "__main__":
    main()
