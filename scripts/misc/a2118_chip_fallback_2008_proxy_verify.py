#!/usr/bin/env python3
"""Read-only verification: does chip_data_fallback_max_stale_days actually let
a2118's real switch rule defend during the 2008 TWII proxy crash, and does it
change anything on real 2025-2026 data (where chip data is genuinely fresh)?

Does not modify backtest_group_a_plus_switch_policy.py's defaults, a2111.py,
a2118.py, group_a_plus_config.json, or any report/* file. Read-only research
using the new opt-in `chip_data_fallback_max_stale_days` param added to
`_switch_returns` (see GROUP_A_PLUS_FABLE_AUDIT_MARKET_STATE_ARBITRATION_HANDOFF_20260704.md).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from twii_proxy_utils import build_group_a_twii_proxy_data  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _switch_returns  # noqa: E402
from group_a_plus.runners.a2111 import _build_switch_rule  # noqa: E402

START_2008, END_2008 = "2007-07-01", "2010-12-31"
START_MODERN, END_MODERN = "2025-01-02", "2026-07-02"
MAX_STALE_DAYS = 10


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


def _run_2008() -> dict:
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

    # real_rule: today's actual behavior, no fallback -- reproduces the bug.
    events_real, frame_real = _switch_returns(prices[["0050.TW"]], None, rule)
    # fallback_enabled: the fix, opt-in, using chip_features=None (which now
    # carries chip_data_days_since_source_update=999_999 -- maximally stale,
    # exactly representing "no chip data ecosystem exists for this window").
    events_fb, frame_fb = _switch_returns(
        prices[["0050.TW"]], None, rule, chip_data_fallback_max_stale_days=MAX_STALE_DAYS
    )

    # idealized: gate removed entirely (not a real rule -- upper-bound reference,
    # matches scripts/misc/market_state_2008_proxy_backtest.py's construction).
    price_enter = (frame_real["ma_gap"] <= rule.enter_ma_gap) | (frame_real["drawdown"] <= rule.enter_drawdown)
    price_exit = (frame_real["ma_gap"] >= rule.exit_ma_gap) & (frame_real["exit_momentum"] > 0.0)
    idealized = []
    in_def, hold = False, 0
    for enter_flag, exit_flag in zip(price_enter, price_exit):
        if in_def:
            hold += 1
            if hold >= rule.min_hold_days and exit_flag:
                in_def = False
                hold = 0
        elif enter_flag:
            in_def = True
            hold = 1
        idealized.append("group_a_plus_defensive" if in_def else "golden1")
    idealized_regime = pd.Series(idealized, index=frame_real.index)

    aggressive_ret = prices["00631L.TW"].pct_change()
    cash_ret = pd.Series(0.0, index=prices.index)
    inverse_ret = prices["00632R.TW"].pct_change()

    variants = {
        "real_rule": frame_real["regime"],
        "fallback_enabled": frame_fb["regime"],
        "idealized": idealized_regime,
    }
    results = {}
    for name, regime in variants.items():
        defensive_days = int((regime == "group_a_plus_defensive").sum())
        results[name] = {
            "defensive_trading_days": defensive_days,
            "defensive_day_pct": defensive_days / len(regime),
            "n_switch_to_defensive_events": sum(
                1 for e in (events_real if name == "real_rule" else events_fb if name == "fallback_enabled" else [])
                if e.get("action") == "switch_to_group_a_plus_defensive"
            ) if name != "idealized" else None,
            "vs_cash": _metrics_from_curve(_simulate(regime, aggressive_ret, cash_ret)),
            "vs_00632r_hedge": _metrics_from_curve(_simulate(regime, aggressive_ret, inverse_ret)),
        }
    results["buy_and_hold_00631l"] = _metrics_from_curve((1.0 + aggressive_ret.fillna(0.0)).cumprod())
    return results


def _run_modern_equivalence_check() -> dict:
    prices = _load_prices(DB_PATH, ["0050.TW"], START_MODERN, END_MODERN)
    chip_features = _load_chip_features(DB_PATH, prices.index, START_MODERN, END_MODERN)
    rule = _build_switch_rule()

    events_baseline, frame_baseline = _switch_returns(prices, chip_features, rule)
    events_fb, frame_fb = _switch_returns(
        prices, chip_features, rule, chip_data_fallback_max_stale_days=MAX_STALE_DAYS
    )

    max_days_since_update = int(chip_features["chip_data_days_since_source_update"].max())
    max_core_days_since_update = int(chip_features["chip_data_core_days_since_source_update"].max())
    regimes_identical = frame_baseline["regime"].equals(frame_fb["regime"])
    events_identical = events_baseline == events_fb

    return {
        "window": {"start": START_MODERN, "end": END_MODERN, "rows": len(prices)},
        "max_chip_data_days_since_source_update_observed": max_days_since_update,
        "max_chip_data_core_days_since_source_update_observed": max_core_days_since_update,
        "regimes_identical_with_and_without_fallback": regimes_identical,
        "events_identical_with_and_without_fallback": events_identical,
        "baseline_defensive_days": int((frame_baseline["regime"] == "group_a_plus_defensive").sum()),
        "fallback_defensive_days": int((frame_fb["regime"] == "group_a_plus_defensive").sum()),
    }


def main() -> None:
    result_2008 = _run_2008()
    result_modern = _run_modern_equivalence_check()

    print("=== 2008 TWII proxy: real_rule vs fallback_enabled vs idealized ===")
    for name, r in result_2008.items():
        if name == "buy_and_hold_00631l":
            print(f"{name}: {r}")
            continue
        print(f"-- {name} --")
        print(f"  defensive_trading_days: {r['defensive_trading_days']} ({r['defensive_day_pct']:.1%})")
        print(f"  vs_cash: {r['vs_cash']}")
        print(f"  vs_00632r_hedge: {r['vs_00632r_hedge']}")

    print("\n=== 2025-2026 modern equivalence check (chip data genuinely fresh) ===")
    print(json.dumps(result_modern, indent=2, ensure_ascii=False))

    out_path = PROJECT_ROOT / "results" / "a2118_chip_fallback_2008_proxy_verify_20260704.json"
    out_path.write_text(
        json.dumps({"proxy_2008": result_2008, "modern_equivalence_check": result_modern}, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
