#!/usr/bin/env python3
"""Candidate fix for the 2020-fold same-day signal misalignment (2026-07-06 finding).

Root cause (confirmed by direct inspection of the A21.11 switch rule's
features frame during the Feb-Mar 2020 COVID crash): `total_risk_score`
peaked at 6 (the rule's `require_total_risk_score` threshold) on 2020-03-06,
while `drawdown` only reached -10.4% that day (short of the -11%
`enter_drawdown` threshold). By 2020-03-09, drawdown had breached -11% (and
kept falling to -30% by 2020-03-19), but `total_risk_score` had already
faded back under 6 and never returned to >=6 for the rest of the crash
window (checked day-by-day 2020-02-15..2020-04-15: `price_enter AND
total_risk_ok` was never simultaneously True on any single day). The switch
rule requires both conditions on the *same* day, so a V-shaped crash where
the two signals peak on different days is structurally invisible to it --
this is a timing-alignment defect in the rule, not a chip-data-availability
problem (institutional_data/margin_data/taifex_options_daily are all real
for 2020).

Candidate fix: relax `total_risk_ok` from "today's total_risk_score >=
threshold" to "max total_risk_score over the last N trading days >=
threshold" (a short rolling-max lookback). This keeps the price-side trigger
(`price_enter`) evaluated same-day as today (react as soon as price actually
breaches), but lets a risk-score peak from a few days earlier still count as
confirmation, directly targeting the misalignment above.

This is NOT a modification to the shared `_switch_returns` function (used by
every other backtest/runner in this repo) -- it is a standalone
reimplementation of the same entry/exit loop with exactly one condition
changed, following the same "duplicate the base and vary one dial" pattern
`group_a_plus/runners/a2118.py`'s `_apply_*_overlay` functions already use to
extend A21.11 without touching it. Tested here across all five crisis folds
from GROUP_A_PLUS_FIVE_CRISES (2026-07-06) plus the current live decision
window, because a rule that fixes 2020 but adds whipsaw/false triggers to the
2025-2026 live period is not a net improvement -- that trade-off is the
actual promotion question.

Research-only. Does not touch any production file, model weight, live
signal, or allocation. Read-only against stock_data.db and the prepared
crisis proxy/real CSVs from earlier in this session.
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
    DEFAULT_GOLDEN_SIGNAL,
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
    _switch_returns,
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
LOOKBACK_CANDIDATES = [0, 3, 5, 10]  # 0 = baseline (today-only, current production behavior)


def _switch_returns_risk_lookback(
    prices: pd.DataFrame,
    chip_features: pd.DataFrame | None,
    rule: SwitchRule,
    lookback_days: int,
    chip_data_fallback_max_stale_days: int | None = None,
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """Same entry/exit loop as `_switch_returns`, with one change: `total_risk_ok`
    uses a rolling max of `total_risk_score` over the last `lookback_days`
    trading days (inclusive of today) instead of only today's value.
    `lookback_days=0` reproduces `_switch_returns` exactly (single-day lookback).
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
        exit_ = row["ma_gap"] >= effective_exit_ma_gap and row["exit_momentum"] > 0.0
        if rule.exit_cost_gap_below is not None:
            exit_ = exit_ and float(row["smart_money_cost_gap_20d"]) >= float(rule.exit_cost_gap_below)
        if rule.exit_max_chip_score is not None:
            exit_ = exit_ and int(row["chip_score"]) <= int(rule.exit_max_chip_score)
        if rule.exit_max_derivative_score is not None:
            exit_ = exit_ and int(row["derivative_score"]) <= int(rule.exit_max_derivative_score)
        if rule.exit_max_total_risk_score is not None:
            exit_ = exit_ and int(row["total_risk_score"]) <= int(rule.exit_max_total_risk_score)
        if rule.exit_max_tail_risk_score is not None:
            exit_ = exit_ and int(row["tail_risk_score"]) <= int(rule.exit_max_tail_risk_score)

        if in_defense:
            hold_days += 1
            if hold_days >= rule.min_hold_days and exit_:
                in_defense = False
                hold_days = 0
                events.append({"date": str(dt.date()), "action": "switch_to_golden"})
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
    lookback_days: int,
    golden_weights: dict[str, float],
    basket: dict[str, float],
    current_defensive: dict[str, float],
) -> tuple[pd.Series, pd.Series, list[dict[str, Any]]]:
    events, frame = _switch_returns_risk_lookback(
        prices, chip_features, rule, lookback_days,
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
    parser.add_argument("--output", default="results/group_a_plus_risk_score_lookback_candidate_20260706.json")
    args = parser.parse_args()

    db_path = _resolve(str(DB_PATH))
    policy_signal, _ = _load_policy_signal(_resolve(str(DEFAULT_DECISION_POINTER)))
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
    basket = _normalize(DEFENSIVE_BASKETS["bond30_cash30"])
    latest_golden_signal = _load(_resolve_golden_signal_path())
    latest_golden_weights = _normalize(_weights_from_group_a(latest_golden_signal))
    rule = _build_switch_rule()

    windows: dict[str, dict[str, Any]] = dict(FOLDS)
    # Add the current live 2025-2026 window: same start a2111/a2118 use by
    # default, full real chip/derivative data, to check for whipsaw/false-
    # trigger regression -- the actual cost side of this candidate.
    live_start = "2025-01-02"
    live_load_start = _warmup_start(live_start, 180)
    live_full_prices = _load_prices(db_path, list(TICKERS), live_load_start, "2026-07-03")
    live_full_chip = _load_chip_features(db_path, live_full_prices.index, live_load_start, "2026-07-03")

    results: dict[str, Any] = {
        "prepared_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": (
            "test whether relaxing total_risk_score to a rolling-max lookback fixes the "
            "2020 same-day signal misalignment without adding whipsaw/false triggers to "
            "the current 2025-2026 live window"
        ),
        "lookback_candidates_days": LOOKBACK_CANDIDATES,
        "windows": {},
    }

    for name, spec in windows.items():
        prices, chip_features = _load_fold_data(name, spec, db_path)
        report_start = spec["report_start"]
        report_end = spec["report_end"]

        window_result: dict[str, Any] = {"label": spec["label"], "lookback_days": {}}
        for lb in LOOKBACK_CANDIDATES:
            curve, execution_regime, events = _run_curve(
                prices, chip_features, rule, lb, latest_golden_weights, basket, current_defensive
            )
            report_curve = curve.loc[report_start:] if report_end is None else curve.loc[report_start:report_end]
            report_regime = execution_regime.loc[report_curve.index]
            defensive_days = int((report_regime == "group_a_plus_defensive").sum())
            switch_events_in_window = [
                e for e in events
                if pd.Timestamp(report_start) <= pd.Timestamp(e["date"]) <= (pd.Timestamp(report_end) if report_end else prices.index[-1])
            ]
            window_result["lookback_days"][str(lb)] = {
                "metrics": _metrics(report_curve, float(report_curve.iloc[0])),
                "defensive_days": defensive_days,
                "switch_event_count": len(switch_events_in_window),
            }
        results["windows"][name] = window_result

    # Live 2025-2026 window (no CSV trim needed; use full real DB data as-is)
    live_window_result: dict[str, Any] = {"label": "Current live 2025-01-02..2026-07-03 (real data)", "lookback_days": {}}
    for lb in LOOKBACK_CANDIDATES:
        curve, execution_regime, events = _run_curve(
            live_full_prices, live_full_chip, rule, lb, latest_golden_weights, basket, current_defensive
        )
        report_curve = curve.loc[live_start:]
        report_regime = execution_regime.loc[report_curve.index]
        defensive_days = int((report_regime == "group_a_plus_defensive").sum())
        switch_events_in_window = [e for e in events if pd.Timestamp(e["date"]) >= pd.Timestamp(live_start)]
        live_window_result["lookback_days"][str(lb)] = {
            "metrics": _metrics(report_curve, float(report_curve.iloc[0])),
            "defensive_days": defensive_days,
            "switch_event_count": len(switch_events_in_window),
        }
    results["windows"]["live_2025_2026"] = live_window_result

    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Output: {output_path}")
    print()
    header = f"{'Window':<20} {'Lookback(d)':>11} {'FinalValue':>14} {'TotalRet':>10} {'Sharpe':>8} {'MDD':>8} {'DefenseDays':>12} {'Switches':>9}"
    print(header)
    print("-" * len(header))
    for name, window_result in results["windows"].items():
        for lb_str, r in window_result["lookback_days"].items():
            m = r["metrics"]
            print(
                f"{name:<20} {lb_str:>11} {m['final_value']:>14,.0f} {m['total_return']:>10.2%} "
                f"{m['sharpe_ratio']:>8.3f} {m['max_drawdown']:>8.2%} {r['defensive_days']:>12} {r['switch_event_count']:>9}"
            )


if __name__ == "__main__":
    main()
