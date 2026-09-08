#!/usr/bin/env python3
"""Direction #5 rebuild (2026-09-08 audit follow-up).

The original retrospective "regret on known recovery events" script
(cited as `scripts/misc/test_reentry_timing_regret_20260908.py` in
GROUP_A_PLUS_20260908_FABLE_10_DIRECTIONS_HANDOFF.md and in memory file
project_fable_direction5_reentry_timing_promising_caveat_20260908.md, which
claims "11/11 events have positive regret at a 5-day earlier re-entry")
does not exist anywhere in the repo. An independent audit confirmed this via
a full-repo file search. The claim that kicked off the whole direction-5
research thread was therefore unreproducible as committed.

This rebuilds that analysis from the method description in the memory file,
using the SAME production switch rule and defensive basket as the committed
2026-09-09 follow-up (test_reentry_earlier_exit_forward_test_20260909.py) --
group_a_plus.runners.a2111._build_switch_rule() and the bond30_cash30
basket -- to independently confirm or refute the "11/11" claim.

Method: run the real production switch rule across the full available
history, find every switch_to_golden (defensive -> risk-on re-entry) event,
and for each one compute "regret" = cumulative return of holding GOLDEN1
weights minus cumulative return of holding the DEFENSIVE basket over the N
trading days immediately before the event date (N in {1, 3, 5, 10}).
Positive regret means staying in defensive cost real money relative to
having already re-entered N days earlier.

Read-only research. Does not touch any production/live file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from backtest_group_a_plus_switch_policy import (
    DB_PATH,
    _load_chip_features,
    _load_prices,
    _simulate_regime_curve,
    _switch_returns,
)
from backtest_group_a_plus_defensive_basket import DEFENSIVE_BASKETS
from group_a_plus.runners.a2111 import _build_switch_rule
from backtest_group_a_plus_policy_signal import TICKERS as ALL_TICKERS

RULE = _build_switch_rule()
TICKERS = list(ALL_TICKERS)
GOLDEN1 = {"0050.TW": 0.50, "00631L.TW": 0.20, "cash": 0.30}
# NOTE (2026-09-08 audit correction): production's defensive basket has been
# bond0_cash60 (0050 40% / cash 60%) since the 2026-08-18 promotion -- see
# group_a_plus/runners/a2118.py line ~838. bond30_cash30 (which the committed
# 2026-09-09 direction-5 follow-up script and an earlier draft of this script
# used) is the SUPERSEDED pre-08-18 basket. Using it here would silently
# re-test a basket that has not been in production for 3+ weeks.
DEFENSIVE = dict(DEFENSIVE_BASKETS["bond0_cash60"])  # {0050:40%, cash:60%}
INITIAL_VALUE = 1_000_000.0

# Matches BASELINE_KW in test_reentry_earlier_exit_forward_test_20260909.py
# and report/group_a_plus/latest/strategy.json (current production values).
PRODUCTION_KW = dict(
    risk_score_lookback_days=5,
    momentum_fast_exit_min=0.10,
    momentum_fast_exit_ma_gap_min=-0.08,
)

SHIFTS_TRADING_DAYS = [1, 3, 5, 10]

# 00713.TW (part of the shared TICKERS universe used by _rebalance/_mark_to_market)
# only has price history from 2017-09-19 onward, so that bounds how far back
# "full history" actually goes regardless of the requested start date below.
LOAD_START = "2016-01-01"
LOAD_END = "2026-09-07"


def _window_return(prices: pd.DataFrame, weights: dict[str, float]) -> float:
    if len(prices) < 2:
        return float("nan")
    regimes = pd.Series(["w"] * len(prices), index=prices.index)
    curve = _simulate_regime_curve(prices[TICKERS], regimes, {"w": weights}, INITIAL_VALUE)
    return float(curve.iloc[-1] / curve.iloc[0] - 1.0)


def main() -> None:
    prices = _load_prices(DB_PATH, TICKERS, LOAD_START, LOAD_END)
    chip_features = _load_chip_features(DB_PATH, prices.index, LOAD_START, LOAD_END)
    events, _ = _switch_returns(prices, chip_features, RULE, **PRODUCTION_KW)

    reentry_events = [e for e in events if e["action"] == "switch_to_golden"]
    print(f"Data range actually used: {prices.index.min().date()} .. {prices.index.max().date()}")
    print(f"Found {len(reentry_events)} switch_to_golden (re-entry) events under the production rule:")
    for e in reentry_events:
        print(f"  {e['date']}")
    print()

    dates = prices.index
    results: dict[str, object] = {
        "data_range_used": [str(dates.min().date()), str(dates.max().date())],
        "reentry_event_dates": [e["date"] for e in reentry_events],
        "by_shift": {},
    }
    for shift in SHIFTS_TRADING_DAYS:
        per_event = []
        positive = 0
        for e in reentry_events:
            event_date = pd.Timestamp(e["date"])
            pos = int(dates.searchsorted(event_date))
            if pos <= 0 or pos >= len(dates):
                continue
            start_pos = max(pos - shift, 0)
            window = prices.iloc[start_pos : pos + 1]
            if len(window) < 2:
                continue
            golden_ret = _window_return(window, GOLDEN1)
            defensive_ret = _window_return(window, DEFENSIVE)
            regret = golden_ret - defensive_ret
            if regret > 0:
                positive += 1
            per_event.append(
                {
                    "event_date": e["date"],
                    "window_start": str(window.index[0].date()),
                    "golden1_return": golden_ret,
                    "defensive_return": defensive_ret,
                    "regret": regret,
                }
            )
        results["by_shift"][f"shift_{shift}d"] = {
            "positive_count": positive,
            "total_count": len(per_event),
            "events": per_event,
        }
        print(f"Shift -{shift}d: {positive}/{len(per_event)} events have positive regret")
        for row in per_event:
            print(
                f"    {row['event_date']} (window from {row['window_start']}): "
                f"golden1={row['golden1_return']*100:+.2f}% defensive={row['defensive_return']*100:+.2f}% "
                f"regret={row['regret']*100:+.2f}pp"
            )
        print()

    out_path = PROJECT_ROOT / "results" / "reentry_timing_regret_rebuild_20260908.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
