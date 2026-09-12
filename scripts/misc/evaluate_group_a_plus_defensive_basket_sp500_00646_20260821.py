#!/usr/bin/env python3
"""Does adding 00646.TW (Yuanta S&P500) to the a2118 defensive basket
improve long-term growth capture, without giving up 2022/COVID downside
protection, 2017-2026?

Research-only. Same reused-machinery approach as
evaluate_group_a_plus_defensive_basket_gold_00635u_20260821.py (see that
file for the fuller explanation): imports
backtest_group_a_plus_defensive_basket.py and backtest_group_a_plus_policy_
signal.py UNMODIFIED ON DISK, monkey-patches both modules' TICKERS tuples
in-process, and adds new DEFENSIVE_BASKETS entries to an in-memory copy of
the dict. Neither file is written to.

Different question from the closed_negative 2026-08-09 00646 research
(project_00646_addition_shadow_20260809, evaluate_00646_sp500_addition_
shadow.py): that one carved a fixed fraction OUT OF the golden1 0050 sleeve
(i.e. during growth/bull regime), and found it was a net drag because
Taiwan/semiconductor rallied more often than the sample's systemic-risk
periods. This script instead asks about the DEFENSIVE sleeve specifically:
instead of parking part of the defensive basket in idle cash, would holding
some S&P500 exposure during defensive windows let you keep compounding
through periods when Taiwan is out of favor but the US market isn't -- a
different mechanism (growth participation during risk-off, not a bull-market
carve) that the 2026-08-09 research did not test.

Does not touch target_weights or any production file.
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

SP500_TICKER = "00646.TW"
SP500_BASKETS = {
    "sp5000_cash60": {"0050.TW": 0.40, SP500_TICKER: 0.00, "cash": 0.60},
    "sp50010_cash50": {"0050.TW": 0.40, SP500_TICKER: 0.10, "cash": 0.50},
    "sp50020_cash40": {"0050.TW": 0.40, SP500_TICKER: 0.20, "cash": 0.40},
}
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_defensive_basket_sp500_00646_20260821.json"


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
    parser.add_argument("--end", default="2026-08-20")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    original_tickers = basket_mod.TICKERS
    original_policy_tickers = policy_signal_mod.TICKERS
    extended_tickers = tuple(original_tickers) + (SP500_TICKER,)
    basket_mod.TICKERS = extended_tickers
    policy_signal_mod.TICKERS = extended_tickers
    basket_mod.DEFENSIVE_BASKETS = dict(basket_mod.DEFENSIVE_BASKETS)
    basket_mod.DEFENSIVE_BASKETS.update(SP500_BASKETS)

    policy_signal, _ = _load_policy_signal(_resolve(args.decision_pointer))
    golden_signal = _load(_resolve(args.golden_signal))
    current_defensive = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)

    keep_baskets = ["current_a207", "bond0_cash60", "sp5000_cash60", "sp50010_cash50", "sp50020_cash40"]
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
        for basket_name in ("bond0_cash60", "sp5000_cash60", "sp50010_cash50", "sp50020_cash40"):
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
            f"sp5000={row['sp5000_cash60_total_return']:+.4f} "
            f"sp50010={row['sp50010_cash50_total_return']:+.4f} "
            f"sp50020={row['sp50020_cash40_total_return']:+.4f}"
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
