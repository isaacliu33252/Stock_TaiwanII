#!/usr/bin/env python3
"""Sweep the ma_gap guard for the momentum fast-exit candidate (2026-07-06).

Follow-up to `scripts/misc/evaluate_momentum_fast_exit_candidate_20260706.py`.
That script found a pure `exit_momentum >= 0.10` fast-exit path fixes 2020
(final value beats the no-switch baseline, MDD -24.05% vs -30.97%) but also
fires once in 2008 (2008-11-03, +14.4% 5-day return -- HIGHER than 2020's
+12.6% trigger) which is a well-known dead-cat bounce deep in the 2008 bear
market (that day: ma_gap=-23.7%, drawdown=-39.2%), not a real recovery. Pure
momentum magnitude cannot tell the two apart (2008's bounce was literally
bigger). Direct feature inspection found `ma_gap` does separate them cleanly:
2020-03-26 (the genuine recovery we want) had ma_gap=-4.4%; 2008-11-03 (the
trap) had ma_gap=-23.7%; 2011's two similarly-genuine fast-exit dates
(2011-10-13, 2011-12-26) had ma_gap=-8.3% and -3.1%.

This sweeps `momentum_fast_exit_ma_gap_min` (require ma_gap >= this value in
addition to the momentum burst) at a fixed `momentum_fast_exit_min=0.10`,
across all six windows, to find the narrowest guard that still excludes the
2008 trap while keeping the 2020/2011 fast exits.

Research-only. Does not touch any production file, model weight, live
signal, or allocation.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

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
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _metrics, _simulate_regime_curve
from backtest_group_a_plus_warmup_consistency import _warmup_start
from group_a_plus.runners.a2111 import _build_switch_rule, _resolve_golden_signal_path
from scripts.misc.backtest_group_a_plus_latest_vs_golden1_0531_five_crises_20260706 import FOLDS, _load_fold_data
from scripts.misc.evaluate_momentum_fast_exit_candidate_20260706 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    RISK_LOOKBACK_DAYS,
    _switch_returns_risk_lookback_momentum_exit,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INITIAL_VALUE = 1_000_000.0
MOMENTUM_FAST_EXIT_MIN = 0.10
MA_GAP_GUARD_CANDIDATES = [None, -0.05, -0.08, -0.10, -0.15]


def _run_curve(prices, chip_features, rule, ma_gap_min, golden_weights, basket, current_defensive):
    events, frame = _switch_returns_risk_lookback_momentum_exit(
        prices, chip_features, rule, RISK_LOOKBACK_DAYS, MOMENTUM_FAST_EXIT_MIN,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        momentum_fast_exit_ma_gap_min=ma_gap_min,
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
    parser.add_argument("--output", default="results/group_a_plus_momentum_fast_exit_ma_gap_guard_sweep_20260706.json")
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
        "purpose": "find the narrowest ma_gap guard that excludes the 2008-11-03 dead-cat-bounce fast exit while keeping the 2020/2011 genuine ones",
        "momentum_fast_exit_min": MOMENTUM_FAST_EXIT_MIN,
        "risk_lookback_days": RISK_LOOKBACK_DAYS,
        "ma_gap_guard_candidates": MA_GAP_GUARD_CANDIDATES,
        "windows": {},
    }

    for name, spec in windows.items():
        prices, chip_features = _load_fold_data(name, spec, db_path)
        report_start, report_end = spec["report_start"], spec["report_end"]
        window_result: dict[str, Any] = {"label": spec["label"], "ma_gap_guard": {}}
        for guard in MA_GAP_GUARD_CANDIDATES:
            curve, execution_regime, events = _run_curve(
                prices, chip_features, rule, guard, latest_golden_weights, basket, current_defensive
            )
            report_curve = curve.loc[report_start:] if report_end is None else curve.loc[report_start:report_end]
            fast_exit_events = [e for e in events if e.get("via_momentum_fast_exit")]
            key = "none" if guard is None else str(guard)
            window_result["ma_gap_guard"][key] = {
                "metrics": _metrics(report_curve, float(report_curve.iloc[0])),
                "fast_exit_dates": [e["date"] for e in fast_exit_events],
            }
        results["windows"][name] = window_result

    live_window_result: dict[str, Any] = {"label": "live_2025_2026", "ma_gap_guard": {}}
    for guard in MA_GAP_GUARD_CANDIDATES:
        curve, execution_regime, events = _run_curve(
            live_full_prices, live_full_chip, rule, guard, latest_golden_weights, basket, current_defensive
        )
        report_curve = curve.loc[live_start:]
        fast_exit_events = [e for e in events if e.get("via_momentum_fast_exit")]
        key = "none" if guard is None else str(guard)
        live_window_result["ma_gap_guard"][key] = {
            "metrics": _metrics(report_curve, float(report_curve.iloc[0])),
            "fast_exit_dates": [e["date"] for e in fast_exit_events],
        }
    results["windows"]["live_2025_2026"] = live_window_result

    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Output: {output_path}")
    print()
    header = f"{'Window':<20} {'MaGapGuard':>11} {'FinalValue':>14} {'Sharpe':>8} {'MDD':>8} {'FastExitDates'}"
    print(header)
    print("-" * 100)
    for name, window_result in results["windows"].items():
        for key, r in window_result["ma_gap_guard"].items():
            m = r["metrics"]
            print(f"{name:<20} {key:>11} {m['final_value']:>14,.0f} {m['sharpe_ratio']:>8.3f} {m['max_drawdown']:>8.2%}  {r['fast_exit_dates']}")


if __name__ == "__main__":
    main()
