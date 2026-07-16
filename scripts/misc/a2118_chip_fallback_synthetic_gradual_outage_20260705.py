#!/usr/bin/env python3
"""Synthetic gradual-outage replay for chip_data_fallback_max_stale_days (N).

Read-only research. Does not modify backtest_group_a_plus_switch_policy.py's
defaults, a2111.py, a2118.py, group_a_plus_config.json, or any report/* file.

Per GROUP_A_PLUS_A2118_CHIP_FALLBACK_HANDOFF_20260704.md: neither the 2008
proxy (core coverage absent from day one -- every N triggers immediately) nor
2025-2026 real data (core coverage never stale -- no N ever triggers) can
actually tune N. Both only prove the mechanism exists, not what a good
threshold is. This script builds a synthetic
`chip_data_core_days_since_source_update` ramp on top of real price series
(2008 TWII proxy crash, and 2025-2026 real prices for the calm-market check)
to test two things N must trade off:

1. False-trigger floor: does N survive plausible short reporting gaps during
   calm markets without spuriously bypassing the chip/derivative/total-risk
   gates?
2. Response-lag ceiling: when a real outage coincides with a crash, how many
   trading days does N cost before the fallback unlocks the defensive entry,
   and does that delay matter for the resulting equity/drawdown?
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from twii_proxy_utils import build_group_a_twii_proxy_data  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices, _switch_returns  # noqa: E402
from group_a_plus.runners.a2111 import _build_switch_rule  # noqa: E402

START_2008, END_2008 = "2007-07-01", "2010-12-31"
START_MODERN, END_MODERN = "2025-01-02", "2026-07-02"
N_VALUES = [1, 2, 3, 5, 7, 10, 15, 20, 30]

_ZERO_CHIP_COLUMNS = [
    "inst_0050_5d", "foreign_0050_5d", "margin_0050_balance_chg_5d",
    "market_margin_balance_chg_5d", "tdcc_0050_minority_chg_1w", "tdcc_0050_major_chg_1w",
    "foreign_shareholding_0050_ratio_chg_5d", "short_0050_margin_balance_chg_5d",
    "short_0050_sbl_balance_chg_5d", "securities_lending_0050_volume_5d",
    "day_trade_0050_volume_5d", "dealer_tx_volume_5d", "dealer_txo_volume_5d",
    "tx_foreign_net_oi", "tx_foreign_net_oi_chg_5d", "txo_foreign_call_net_oi",
    "txo_foreign_put_net_oi", "txo_foreign_put_call_net_oi", "txo_foreign_put_call_net_oi_chg_5d",
    "smart_money_cost_20d", "smart_money_cost_60d", "smart_money_cost_gap_20d",
    "smart_money_cost_gap_60d", "smart_money_pressure_20d", "smart_money_cost_risk",
]


def _synthetic_chip_features(index: pd.DatetimeIndex, core_days_since_update: pd.Series) -> pd.DataFrame:
    """A chip_features frame where every real chip/derivative signal is zero
    (chip_score/derivative_score always 0, matching a genuine full-feed
    outage), but the staleness clock follows a caller-supplied synthetic
    ramp instead of the constant 999_999 sentinel used by the
    chip_features=None shortcut.
    """
    frame = pd.DataFrame(0.0, index=index, columns=_ZERO_CHIP_COLUMNS)
    frame["chip_data_days_since_source_update"] = core_days_since_update.reindex(index)
    frame["chip_data_core_days_since_source_update"] = core_days_since_update.reindex(index)
    return frame


def _gap_ramp(index: pd.DatetimeIndex, gaps: list[tuple[int, int]]) -> pd.Series:
    """Build a days-since-update ramp with fresh coverage everywhere except
    the given (start_position, length) gaps, each of which ramps 1..length
    then drops back to 0 (coverage resumed) on the day after the gap ends.
    """
    values = [0] * len(index)
    for start_pos, length in gaps:
        for k in range(length):
            pos = start_pos + k
            if 0 <= pos < len(values):
                values[pos] = k + 1
    return pd.Series(values, index=index)


def _sustained_outage_ramp(index: pd.DatetimeIndex, outage_start_pos: int) -> pd.Series:
    """Fresh coverage (0) up to outage_start_pos, then an unrecovered,
    ever-growing gap for the rest of the window -- the worst case: the feed
    never comes back before the test window ends.
    """
    values = [0] * len(index)
    for pos in range(outage_start_pos, len(index)):
        values[pos] = pos - outage_start_pos + 1
    return pd.Series(values, index=index)


def _metrics_from_curve(curve: pd.Series) -> dict:
    running_max = curve.cummax()
    return {
        "final_value": float(curve.iloc[-1]),
        "max_drawdown": float((curve / running_max - 1.0).min()),
    }


def _simulate(regime: pd.Series, aggressive_ret: pd.Series, defensive_ret: pd.Series) -> pd.Series:
    daily_ret = aggressive_ret.where(regime.reindex(aggressive_ret.index) == "golden1", defensive_ret)
    return (1.0 + daily_ret.fillna(0.0)).cumprod()


def _first_true_position(mask: pd.Series, *, skip: int = 0) -> int | None:
    trimmed = mask.copy()
    if skip:
        trimmed.iloc[:skip] = False
    hits = trimmed.to_numpy().nonzero()[0]
    return int(hits[0]) if len(hits) else None


def _calm_market_false_trigger_check() -> dict:
    """Scenario A: isolated, fully-recovering reporting gaps sprinkled through
    the earliest (pre-crash) part of the 2008 proxy window. Checks which N
    values would spuriously bypass the chip/derivative/total-risk gates
    during a plausible calm-market data hiccup (e.g. a public holiday cluster
    delaying a vendor's refresh), rather than during a genuine outage.
    """
    stock_data, _ = build_group_a_twii_proxy_data(START_2008, END_2008)
    prices = pd.DataFrame(
        {
            "0050.TW": pd.Series(
                stock_data["0050.TW"]["close"].to_numpy(),
                index=pd.to_datetime(stock_data["0050.TW"]["date"]).dt.normalize(),
            )
        }
    ).sort_index()
    index = prices.index
    # Gaps of length 1, 2, 3, 5, 7 trading days, spaced well apart, all inside
    # the first 200 trading days (well before the 2008 crash begins).
    gaps = [(10, 1), (40, 2), (80, 3), (120, 5), (160, 7)]
    ramp = _gap_ramp(index, gaps)
    max_gap_len = max(length for _, length in gaps)
    triggered = {str(n): bool((ramp >= n).any()) for n in N_VALUES}
    return {
        "gaps_tested_trading_days": [length for _, length in gaps],
        "max_gap_length": max_gap_len,
        "n_would_false_trigger_on_calm_gap": triggered,
        "conclusion": (
            f"With isolated calm-market gaps up to {max_gap_len} trading days, "
            f"N values <= {max_gap_len} would spuriously bypass the chip/"
            "derivative/total-risk gates during a normal reporting hiccup, not "
            "a real outage. N=10 (production default) survives every gap "
            "tested here. This is an assumption-based bound, not empirical -- "
            "real 2025-2026 data has never shown a core-source gap at all "
            "(see a2118_chip_fallback_threshold_sweep_20260704.json), so there "
            "is no historical precedent for how large a real reporting hiccup "
            "could be."
        ),
    }


def _sustained_outage_response_lag_check() -> dict:
    """Scenarios B & C: a permanent, unrecovered outage starting either
    exactly at the crash's first price-eligible day (worst-case timing) or
    well before it (best-case timing), replayed with each candidate N.
    """
    stock_data, _ = build_group_a_twii_proxy_data(START_2008, END_2008)
    prices = pd.DataFrame(
        {
            t: pd.Series(
                stock_data[t]["close"].to_numpy(),
                index=pd.to_datetime(stock_data[t]["date"]).dt.normalize(),
            )
            for t in ("0050.TW", "00631L.TW", "00632R.TW")
        }
    ).dropna().sort_index()
    index = prices.index
    rule = _build_switch_rule()

    # Locate the crash's first price-eligible day using the real (unfallback'd) frame.
    # ma_gap/drawdown are fillna(0.0) during the rolling-window warm-up, and
    # enter_ma_gap is positive (0.0 <= enter_ma_gap), so the unwarmed rows
    # spuriously read as "eligible" -- skip the warm-up window before looking
    # for the first genuine trigger.
    _events_real, frame_real = _switch_returns(prices[["0050.TW"]], None, rule)
    price_enter = (frame_real["ma_gap"] <= rule.enter_ma_gap) | (frame_real["drawdown"] <= rule.enter_drawdown)
    warmup = max(rule.ma_window, rule.drawdown_window)
    crash_pos = _first_true_position(price_enter, skip=warmup)
    assert crash_pos is not None, "2008 proxy did not produce a price-eligible entry day"
    crisis_peak_pos = int(frame_real["drawdown"].to_numpy().argmin())

    aggressive_ret = prices["00631L.TW"].pct_change()
    cash_ret = pd.Series(0.0, index=prices.index)
    inverse_ret = prices["00632R.TW"].pct_change()

    scenarios = {
        "worst_case_outage_starts_at_first_eligible_trigger": crash_pos,
        "best_case_outage_starts_90d_before_first_eligible_trigger": max(crash_pos - 90, 0),
        "outage_starts_at_deepest_crisis_drawdown": crisis_peak_pos,
    }
    results: dict[str, dict] = {}
    for scenario_name, outage_pos in scenarios.items():
        ramp = _sustained_outage_ramp(index, outage_pos)
        chip_features = _synthetic_chip_features(index, ramp)
        per_n = {}
        for n in N_VALUES:
            events_n, frame_n = _switch_returns(
                prices[["0050.TW"]], chip_features, rule, chip_data_fallback_max_stale_days=n
            )
            regime = frame_n["regime"]
            entry_pos = _first_true_position(regime == "group_a_plus_defensive")
            days_after_outage_start = None
            if entry_pos is not None and entry_pos >= outage_pos:
                days_after_outage_start = entry_pos - outage_pos
            per_n[str(n)] = {
                "first_defensive_entry_position": entry_pos,
                "trading_days_after_outage_start": days_after_outage_start,
                "defensive_trading_days": int((regime == "group_a_plus_defensive").sum()),
                "n_switch_to_defensive_events": sum(
                    1 for e in events_n if e.get("action") == "switch_to_group_a_plus_defensive"
                ),
                "vs_cash": _metrics_from_curve(_simulate(regime, aggressive_ret, cash_ret)),
                "vs_00632r_hedge": _metrics_from_curve(_simulate(regime, aggressive_ret, inverse_ret)),
            }
        # Reference: no fallback at all (the original bug, reproduced under this outage).
        events_nofb, frame_nofb = _switch_returns(prices[["0050.TW"]], chip_features, rule)
        regime_nofb = frame_nofb["regime"]
        results[scenario_name] = {
            "outage_start_position": outage_pos,
            "crash_trigger_position": crash_pos,
            "no_fallback_reference": {
                "defensive_trading_days": int((regime_nofb == "group_a_plus_defensive").sum()),
                "vs_cash": _metrics_from_curve(_simulate(regime_nofb, aggressive_ret, cash_ret)),
                "vs_00632r_hedge": _metrics_from_curve(_simulate(regime_nofb, aggressive_ret, inverse_ret)),
            },
            "by_n": per_n,
        }
    return results


def main() -> None:
    calm = _calm_market_false_trigger_check()
    sustained = _sustained_outage_response_lag_check()

    result = {
        "scenario_a_calm_market_false_trigger": calm,
        "scenario_b_c_sustained_outage_response_lag": sustained,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    out = PROJECT_ROOT / "results" / "a2118_chip_fallback_synthetic_gradual_outage_20260705.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
