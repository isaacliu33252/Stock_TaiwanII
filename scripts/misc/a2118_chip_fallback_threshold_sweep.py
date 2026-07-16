#!/usr/bin/env python3
"""Threshold sensitivity check for chip_data_fallback_max_stale_days.

Read-only research. Does not modify _build_switch_rule() defaults, a2111.py,
a2118.py, group_a_plus_config.json, or report/*.

Key finding (see report): after splitting source freshness into any-source
coverage and core-source coverage, the 2008 proxy correctly treats the
decision-relevant chip/derivative ecosystem as stale even though broad
market_margin_data exists. The N sweep is still not a real tuning surface in
the proxy: every N in this sweep is active from day one because core coverage
never existed in that window.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from twii_proxy_utils import build_group_a_twii_proxy_data  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _regime_features  # noqa: E402
from group_a_plus.runners.a2111 import _build_switch_rule  # noqa: E402

START_2008, END_2008 = "2007-07-01", "2010-12-31"
START_MODERN, END_MODERN = "2025-01-02", "2026-07-02"
N_VALUES = [1, 2, 3, 5, 7, 10, 15, 20, 30]


def _2008_real_query_check() -> dict:
    """Use the REAL _load_chip_features() DB query for 2008, not
    chip_features=None. The diagnostic any-source clock stays fresh because
    market_margin_data exists, while the core-source clock remains stale
    because ETF/institutional/derivative sources do not cover this proxy
    window.
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
    chip = _load_chip_features(DB_PATH, prices.index, START_2008, END_2008)
    rule = _build_switch_rule()
    frame = _regime_features(prices, rule, chip)
    any_days = chip["chip_data_days_since_source_update"]
    core_days = chip["chip_data_core_days_since_source_update"]
    return {
        "rows": int(len(any_days)),
        "any_source_days_since_update_max": int(any_days.max()),
        "any_source_days_since_update_all_zero": bool((any_days == 0).all()),
        "core_source_days_since_update_min": int(core_days.min()),
        "core_source_days_since_update_max": int(core_days.max()),
        "core_source_days_since_update_all_sentinel": bool((core_days == 999_999).all()),
        "total_risk_score_max": int(frame["total_risk_score"].max()),
        "days_total_risk_score_ge_6": int((frame["total_risk_score"] >= 6).sum()),
        "would_any_source_clock_trigger_fallback": {
            str(n): int((any_days >= n).sum()) for n in N_VALUES
        },
        "would_core_source_clock_trigger_fallback": {
            str(n): int((core_days >= n).sum()) for n in N_VALUES
        },
        "conclusion": (
            "any-source days_since_update is 0 for the entire 2008 window "
            "because market_margin_data alone has broad-market rows since "
            "2007. core-source days_since_update is the 999999 sentinel for "
            "the entire window because ETF/institutional/derivative sources "
            "do not cover this proxy period. The fallback should therefore "
            "use the core clock, not the any-source clock. For the 2008 "
            "proxy, all N values in the sweep trigger identically from day "
            "one, so this window verifies the outage fix but cannot tune N."
        ),
    }


def _2008_none_shortcut_check() -> dict:
    """Reproduce the prior verify script's chip_features=None path to show
    why sweeping N there is *also* uninformative, just in the opposite way:
    chip_features=None forces chip_data_days_since_source_update to a
    constant 999_999 sentinel for every row (see _regime_features), so
    every N in {1..30} triggers the fallback from day 1 -- there's no
    ramp-up to be sensitive to.
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
    rule = _build_switch_rule()
    frame = _regime_features(prices, rule, None)
    days = frame["chip_data_days_since_source_update"]
    return {
        "days_since_update_constant_value": int(days.iloc[0]),
        "all_rows_identical": bool((days == days.iloc[0]).all()),
        "conclusion": (
            "chip_features=None makes every row read the 999_999 sentinel "
            "from the first day, so all N in the sweep are equivalent "
            "(fallback active for the entire window regardless of N). "
            "This is why the earlier verify script's N=10 result "
            "(436 defensive days, matching `idealized`) can't be used to "
            "infer anything about *how quickly* the mechanism reacts -- "
            "it was testing a 'total blackout from day one' scenario, not "
            "a realistic gradual-outage scenario."
        ),
    }


def _2025_2026_distribution_check() -> dict:
    prices = _load_prices(DB_PATH, ["0050.TW"], START_MODERN, END_MODERN)
    chip = _load_chip_features(DB_PATH, prices.index, START_MODERN, END_MODERN)
    any_days = chip["chip_data_days_since_source_update"]
    core_days = chip["chip_data_core_days_since_source_update"]
    any_value_counts = any_days.value_counts().sort_index()
    core_value_counts = core_days.value_counts().sort_index()
    return {
        "rows": int(len(any_days)),
        "any_source_max": int(any_days.max()),
        "any_source_all_zero": bool((any_days == 0).all()),
        "any_source_value_counts": {str(int(k)): int(v) for k, v in any_value_counts.items()},
        "core_source_max": int(core_days.max()),
        "core_source_all_zero": bool((core_days == 0).all()),
        "core_source_value_counts": {str(int(k)): int(v) for k, v in core_value_counts.items()},
        "n_values_that_would_false_trigger_core_clock": {
            str(n): int((core_days >= n).sum()) for n in N_VALUES
        },
    }


def main() -> None:
    result = {
        "2008_real_query_path": _2008_real_query_check(),
        "2008_none_shortcut_path": _2008_none_shortcut_check(),
        "2025_2026_distribution": _2025_2026_distribution_check(),
        "n_sweep_verdict": (
            "The 2008 proxy verifies that the core-source fallback fixes the "
            "data-outage failure, but it cannot tune N because core coverage "
            "is absent from the first row and every tested N is active for "
            "the whole window. On 2025-2026 real data, all N in "
            "{1,2,3,5,7,10,15,20,30} are equally safe from false triggers "
            "because core-source days_since_update is 0 for all 361 rows. "
            "A true N choice still needs a synthetic gradual-outage replay "
            "or a real partial-outage incident."
        ),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    out = PROJECT_ROOT / "results" / "a2118_chip_fallback_threshold_sweep_20260704.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
