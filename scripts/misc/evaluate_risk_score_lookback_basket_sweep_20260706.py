#!/usr/bin/env python3
"""Sweep defensive-basket choice for the risk-score-lookback candidate (2026-07-06).

The risk-score-lookback fix (lookback_days=5, see
`scripts/misc/evaluate_risk_score_lookback_candidate_20260706.py`) fixed the
2020 same-day signal misalignment (MDD -30.97% -> -19.64%, Sharpe 1.253 ->
1.439) but failed the multi-window gate's `max_final_drawdown_pct=0.02` check
on that same fold (-3.10% final-value drag) because `bond30_cash30` (0050
40% / 00679B 30% / cash 30%) only keeps 40% equity exposure while defensive,
missing most of the March-April 2020 V-shaped rebound during the 27
defensive days (2020-03-09..2020-04-17, confirmed via direct event
inspection -- exit only fires once ma_gap climbs back above +1%, which took
until the rebound was already well underway).

This sweeps `DEFENSIVE_BASKETS` alternatives (more equity exposure while
defensive) against the fixed lookback_days=5 candidate, across the same six
windows (five crisis folds + current live), to see whether a less
conservative basket recovers enough of the missed rebound to clear the
final-value floor without giving back the MDD/Sharpe gains that made the
lookback fix worth trying in the first place.

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

from backtest_group_a_plus_defensive_basket import DEFENSIVE_BASKETS
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
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _metrics
from backtest_group_a_plus_warmup_consistency import _warmup_start
from group_a_plus.runners.a2111 import _build_switch_rule, _resolve_golden_signal_path
from scripts.misc.backtest_group_a_plus_latest_vs_golden1_0531_five_crises_20260706 import (
    FOLDS,
    _load_fold_data,
)
from scripts.misc.evaluate_risk_score_lookback_candidate_20260706 import _run_curve

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOOKBACK_DAYS = 5
BASKET_CANDIDATES = ["bond30_cash30", "cash30", "bond20", "bond40", "cash40"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="results/group_a_plus_risk_score_lookback_basket_sweep_20260706.json")
    args = parser.parse_args()

    db_path = _resolve(str(DB_PATH))
    policy_signal, _ = _load_policy_signal(_resolve(str(DEFAULT_DECISION_POINTER)))
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
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
            "sweep defensive-basket choice for the risk-score-lookback(5) candidate to see "
            "if a less conservative basket recovers the 2020 final-value drag without giving "
            "back the MDD/Sharpe improvement"
        ),
        "lookback_days": LOOKBACK_DAYS,
        "basket_candidates": {name: DEFENSIVE_BASKETS[name] for name in BASKET_CANDIDATES},
        "windows": {},
    }

    for name, spec in windows.items():
        prices, chip_features = _load_fold_data(name, spec, db_path) if name in FOLDS else (live_full_prices, live_full_chip)
        report_start = spec["report_start"]
        report_end = spec["report_end"]

        window_result: dict[str, Any] = {"label": spec["label"], "baskets": {}}
        for basket_name in BASKET_CANDIDATES:
            basket = _normalize(DEFENSIVE_BASKETS[basket_name])
            curve, execution_regime, events = _run_curve(
                prices, chip_features, rule, LOOKBACK_DAYS, latest_golden_weights, basket, current_defensive
            )
            report_curve = curve.loc[report_start:] if report_end is None else curve.loc[report_start:report_end]
            report_regime = execution_regime.loc[report_curve.index]
            defensive_days = int((report_regime == "group_a_plus_defensive").sum())
            window_result["baskets"][basket_name] = {
                "metrics": _metrics(report_curve, float(report_curve.iloc[0])),
                "defensive_days": defensive_days,
            }
        results["windows"][name] = window_result

    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Output: {output_path}")
    print()
    header = f"{'Window':<20} {'Basket':<14} {'FinalValue':>14} {'TotalRet':>10} {'Sharpe':>8} {'MDD':>8} {'DefDays':>8}"
    print(header)
    print("-" * len(header))
    for name, window_result in results["windows"].items():
        for basket_name, r in window_result["baskets"].items():
            m = r["metrics"]
            print(
                f"{name:<20} {basket_name:<14} {m['final_value']:>14,.0f} {m['total_return']:>10.2%} "
                f"{m['sharpe_ratio']:>8.3f} {m['max_drawdown']:>8.2%} {r['defensive_days']:>8}"
            )


if __name__ == "__main__":
    main()
