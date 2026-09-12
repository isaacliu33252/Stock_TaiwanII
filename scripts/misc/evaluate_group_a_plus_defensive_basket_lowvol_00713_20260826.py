#!/usr/bin/env python3
"""Does adding 00713.TW (Yuanta Taiwan Dividend Low-Volatility) to the a2118
defensive basket help -- unlike 00733 (mid/small-cap A-grade momentum,
already tested 2026-08-26 and rejected: dominated by 0050 on every axis, not
protective in 2 of 3 crash episodes, thin liquidity), 00713 is a min-variance
weighted high-dividend basket explicitly engineered to be low-beta. This
checks whether that lower-beta Taiwan equity character actually cushions the
defensive-window drawdowns 2020-2026, using the SAME reused-machinery
approach as evaluate_group_a_plus_defensive_basket_dividend_0056_20260821.py.

Research-only. Monkey-patches backtest_group_a_plus_defensive_basket.py and
backtest_group_a_plus_policy_signal.py's TICKERS tuples in-process; neither
file is written to. Does not touch target_weights, the database, or any
production file.

DIVIDEND DATA CAVEAT: 00713's pre-2020 history was backfilled today
(2026-08-26) via FinRL/data/stock_db.py's cmd_add(), which has the same
known dividends=0 bug documented in the 0056 script above (2020+ data was
already correctly populated by an earlier pipeline run and is unaffected).
Two real ex-dividend dates fall inside the affected 2017-2019 gap
(2018-11-22 NT$1.55, 2019-11-22 NT$1.60, fetched directly from yfinance) --
corrected in-memory below, same pattern as the 0056 script. This only
affects the full-window (2017-2026) aggregate; the COVID/2022/2025 episodes
below are all on the correctly-populated 2020+ data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import backtest_group_a_plus_defensive_basket as basket_mod
import backtest_group_a_plus_policy_signal as policy_signal_mod
from backtest_group_a_plus_policy_signal import (
    DEFAULT_DECISION_POINTER,
    DEFAULT_GOLDEN_SIGNAL,
    _load,
    _load_policy_signal,
    _normalize,
    _resolve,
    _weights_from_group_a,
    _weights_from_group_a_plus,
)
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _metrics, _switch_returns
from backtest_group_a_plus_warmup_consistency import _trim_window, _warmup_start
from group_a_plus.runners.a207 import A207_RULE

LV_TICKER = "00713.TW"
LV_BASKETS = {
    "lv0713_0_cash60": {"0050.TW": 0.40, LV_TICKER: 0.00, "cash": 0.60},
    "lv0713_10_cash50": {"0050.TW": 0.40, LV_TICKER: 0.10, "cash": 0.50},
    "lv0713_20_cash40": {"0050.TW": 0.40, LV_TICKER: 0.20, "cash": 0.40},
}
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_defensive_basket_lowvol_00713_20260826.json"


def _episode_label(start, end) -> str:
    if start.year == 2020 and start.month <= 6:
        return "covid_2020"
    if start.year == 2022 or (start.year == 2021 and start.month >= 11):
        return "bear_2022"
    if start.year >= 2023:
        return "post_2023"
    return "other"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2017-07-10")
    parser.add_argument("--end", default="2026-08-25")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    original_tickers = basket_mod.TICKERS
    original_policy_tickers = policy_signal_mod.TICKERS
    extended_tickers = tuple(original_tickers) + (LV_TICKER,)
    basket_mod.TICKERS = extended_tickers
    policy_signal_mod.TICKERS = extended_tickers
    basket_mod.DEFENSIVE_BASKETS = dict(basket_mod.DEFENSIVE_BASKETS)
    basket_mod.DEFENSIVE_BASKETS.update(LV_BASKETS)

    policy_signal, _ = _load_policy_signal(_resolve(args.decision_pointer))
    golden_signal = _load(_resolve(args.golden_signal))
    current_defensive = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)

    keep_baskets = ["current_a207", "bond0_cash60", "lv0713_0_cash60", "lv0713_10_cash50", "lv0713_20_cash40"]
    baskets = {
        name: _normalize(current_defensive if basket_mod.DEFENSIVE_BASKETS[name] is None else basket_mod.DEFENSIVE_BASKETS[name])
        for name in keep_baskets
    }

    load_start = _warmup_start(args.start, args.warmup_days)
    full_close = _load_prices(_resolve(str(DB_PATH)), list(extended_tickers), load_start, args.end)
    full_chip = _load_chip_features(_resolve(str(DB_PATH)), full_close.index, load_start, args.end)
    full_events, full_frame = _switch_returns(full_close, full_chip, A207_RULE)
    close_prices, frame, events = _trim_window(full_close, full_frame, full_events, args.start, args.end)
    total_return_prices, dividend_coverage = basket_mod._load_total_return_prices(_resolve(str(DB_PATH)), close_prices.index)

    missing_dividends = [
        ("2018-11-22", 1.55, 16.860695),
        ("2019-11-22", 1.60, 20.156414),
    ]
    import pandas as pd

    corrected = 0
    for date_str, div, close_px in missing_dividends:
        ts = pd.Timestamp(date_str)
        if ts in total_return_prices.index:
            factor = (close_px + div) / close_px
            total_return_prices.loc[ts:, LV_TICKER] *= factor
            corrected += 1
    print(f"Dividend correction applied: {corrected}/{len(missing_dividends)} known 00713 ex-dates inside window")

    print(f"Window: {close_prices.index[0].date()} .. {close_prices.index[-1].date()} ({len(close_prices)} rows)")
    print(f"Defensive days in window: {int((frame['regime'] == 'group_a_plus_defensive').sum())}")

    rows: list[dict[str, Any]] = []
    for basket_name, defensive_weights in baskets.items():
        weights_by_regime = {"golden1": golden_weights, "group_a_plus_defensive": defensive_weights}
        curve, execution = basket_mod._simulate_costed_curve(
            total_return_prices, frame["regime"], weights_by_regime,
            args.initial_value, args.commission_rate, args.slippage_rate, args.equity_etf_sell_tax,
        )
        metrics = _metrics(curve, args.initial_value)
        rows.append({"basket": basket_name, **metrics, **execution})

    print("\n=== full-window (2017-2026) ===")
    for row in rows:
        print(
            f"  {row['basket']}: final_value={row['final_value']:,.0f} sharpe={row['sharpe_ratio']:.3f} "
            f"mdd={row['max_drawdown']:.4f} rebalances={row['rebalance_count']}"
        )

    episode_summary, episode_selected_basket, stress_episodes = basket_mod._episode_selection(
        frame, total_return_prices, baskets, args.initial_value,
        args.commission_rate, args.slippage_rate, args.equity_etf_sell_tax,
    )

    print("\n=== stress episodes detected ===")
    for ep in stress_episodes:
        print(f"  #{ep['episode']}: {ep['start']} .. {ep['end']} ({ep['trading_days']} trading days) -> {_episode_label(__import__('pandas').Timestamp(ep['start']), __import__('pandas').Timestamp(ep['end']))}")

    print("\n=== episode-level summary (delta vs current_a207 baseline, median across episodes) ===")
    for summary in episode_summary:
        print(
            f"  {summary['basket']}: episodes={summary['episode_count']} joint_win={summary['joint_win_count']} "
            f"median_return_delta={summary['median_return_delta']:+.4f} worst_return_delta={summary['worst_return_delta']:+.4f} "
            f"median_mdd_delta={summary['median_mdd_delta']:+.4f} worst_mdd_delta={summary['worst_mdd_delta']:+.4f}"
        )

    per_episode_detail: list[dict[str, Any]] = []
    for ep in stress_episodes:
        import pandas as pd

        start, end = pd.Timestamp(ep["start"]), pd.Timestamp(ep["end"])
        segment = total_return_prices.loc[start:end]
        row: dict[str, Any] = {
            "episode": ep["episode"], "start": ep["start"], "end": ep["end"],
            "label": _episode_label(start, end), "trading_days": ep["trading_days"],
        }
        for basket_name in ("bond0_cash60", "lv0713_0_cash60", "lv0713_10_cash50", "lv0713_20_cash40"):
            curve, _cost = basket_mod._episode_curve(
                segment, baskets[basket_name], args.initial_value,
                args.commission_rate, args.slippage_rate, args.equity_etf_sell_tax,
            )
            m = _metrics(curve, args.initial_value)
            row[f"{basket_name}_total_return"] = m["total_return"]
            row[f"{basket_name}_max_drawdown"] = m["max_drawdown"]
        per_episode_detail.append(row)

    print("\n=== per-episode total_return by basket (labelled) ===")
    for row in per_episode_detail:
        print(
            f"  #{row['episode']} [{row['label']}] {row['start']}..{row['end']}: "
            f"bond0_cash60={row['bond0_cash60_total_return']:+.4f} "
            f"lv0={row['lv0713_0_cash60_total_return']:+.4f} "
            f"lv10={row['lv0713_10_cash50_total_return']:+.4f} "
            f"lv20={row['lv0713_20_cash40_total_return']:+.4f}"
        )

    payload = {
        "policy": "research_only_no_weight_change",
        "window": {"start": str(close_prices.index[0].date()), "end": str(close_prices.index[-1].date()), "rows": int(len(close_prices))},
        "defensive_days": int((frame["regime"] == "group_a_plus_defensive").sum()),
        "full_window_metrics": rows,
        "episode_summary": episode_summary,
        "episode_selected_basket": episode_selected_basket,
        "stress_episodes": stress_episodes,
        "per_episode_detail": per_episode_detail,
        "dividend_coverage": dividend_coverage,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved: {output_path}")

    basket_mod.TICKERS = original_tickers
    policy_signal_mod.TICKERS = original_policy_tickers


if __name__ == "__main__":
    main()
