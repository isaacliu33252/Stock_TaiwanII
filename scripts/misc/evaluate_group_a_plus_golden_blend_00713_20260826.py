#!/usr/bin/env python3
"""Untested angle from the 00713 defensive-basket rejection (2026-08-26): does
00713 help as a GOLDEN/bull-regime diversifier (partial substitute for
0050.TW's 60% golden-regime weight) rather than as a defensive-cash
substitute (already rejected -- see
evaluate_group_a_plus_defensive_basket_lowvol_00713_20260826.py)?

00713's standalone total-return correlation to 0050 is 0.38 (much lower than
00631L/00632R's near +-1.0 by construction) with a shallower standalone MDD
(-25.8% vs -33.8%, 2020-2026). This checks whether trading some golden-regime
0050 exposure for 00713 exposure changes full-window and crisis-episode
Sharpe/MDD. Defensive-regime weights are left at the current production
basket (unchanged) so this isolates the golden-regime question only.

Research-only, same reused-machinery / monkey-patch approach as the sibling
defensive-basket scripts. Does not touch target_weights, the database, or
any production file.
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

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_golden_blend_00713_20260826.json"


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
    parser.add_argument("--start", default="2020-01-02")  # avoids the pre-2020 cmd_add zeroed-dividend gap for 00713
    parser.add_argument("--end", default="2026-08-25")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--blend-ticker", default="00713.TW")
    args = parser.parse_args()
    LV_TICKER = args.blend_ticker

    original_tickers = basket_mod.TICKERS
    original_policy_tickers = policy_signal_mod.TICKERS
    extended_tickers = tuple(original_tickers) + (LV_TICKER,)
    basket_mod.TICKERS = extended_tickers
    policy_signal_mod.TICKERS = extended_tickers

    policy_signal, _ = _load_policy_signal(_resolve(args.decision_pointer))
    golden_signal = _load(_resolve(args.golden_signal))
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
    golden_weights = _weights_from_group_a(golden_signal)

    # golden blends: move X pp of the 60% 0050 golden weight into 00713,
    # leave 00631L / cash untouched.
    golden_blends = {
        "current_a207": dict(golden_weights),
        "golden_00713_20pp": {**golden_weights, "0050.TW": golden_weights["0050.TW"] - 0.20, LV_TICKER: 0.20},
        "golden_00713_40pp": {**golden_weights, "0050.TW": golden_weights["0050.TW"] - 0.40, LV_TICKER: 0.40},
    }
    for name, w in golden_blends.items():
        golden_blends[name] = _normalize(w)

    load_start = _warmup_start(args.start, args.warmup_days)
    full_close = _load_prices(_resolve(str(DB_PATH)), list(extended_tickers), load_start, args.end)
    full_chip = _load_chip_features(_resolve(str(DB_PATH)), full_close.index, load_start, args.end)
    full_events, full_frame = _switch_returns(full_close, full_chip, A207_RULE)
    close_prices, frame, events = _trim_window(full_close, full_frame, full_events, args.start, args.end)
    total_return_prices, dividend_coverage = basket_mod._load_total_return_prices(_resolve(str(DB_PATH)), close_prices.index)

    print(f"Window: {close_prices.index[0].date()} .. {close_prices.index[-1].date()} ({len(close_prices)} rows)")

    rows: list[dict[str, Any]] = []
    for name, golden_w in golden_blends.items():
        weights_by_regime = {"golden1": golden_w, "group_a_plus_defensive": current_defensive}
        curve, execution = basket_mod._simulate_costed_curve(
            total_return_prices, frame["regime"], weights_by_regime,
            args.initial_value, args.commission_rate, args.slippage_rate, args.equity_etf_sell_tax,
        )
        metrics = _metrics(curve, args.initial_value)
        rows.append({"basket": name, "golden_weights": golden_w, **metrics, **execution})

    print("\n=== full-window ===")
    for row in rows:
        print(
            f"  {row['basket']}: final_value={row['final_value']:,.0f} sharpe={row['sharpe_ratio']:.3f} "
            f"mdd={row['max_drawdown']:.4f} rebalances={row['rebalance_count']}"
        )

    episode_summary, episode_selected_basket, stress_episodes = basket_mod._episode_selection(
        frame, total_return_prices, golden_blends, args.initial_value,
        args.commission_rate, args.slippage_rate, args.equity_etf_sell_tax,
    )
    print("\n=== episode-level summary (delta vs golden_00713_0pp baseline) ===")
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
        for basket_name in golden_blends:
            curve, _cost = basket_mod._episode_curve(
                segment, golden_blends[basket_name], args.initial_value,
                args.commission_rate, args.slippage_rate, args.equity_etf_sell_tax,
            )
            m = _metrics(curve, args.initial_value)
            row[f"{basket_name}_total_return"] = m["total_return"]
            row[f"{basket_name}_max_drawdown"] = m["max_drawdown"]
        per_episode_detail.append(row)

    print("\n=== per-episode total_return by golden blend (labelled) ===")
    for row in per_episode_detail:
        print(
            f"  #{row['episode']} [{row['label']}] {row['start']}..{row['end']}: "
            f"0pp={row['current_a207_total_return']:+.4f} "
            f"20pp={row['golden_00713_20pp_total_return']:+.4f} "
            f"40pp={row['golden_00713_40pp_total_return']:+.4f}"
        )

    payload = {
        "policy": "research_only_no_weight_change",
        "window": {"start": str(close_prices.index[0].date()), "end": str(close_prices.index[-1].date()), "rows": int(len(close_prices))},
        "full_window_metrics": rows,
        "episode_summary": episode_summary,
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
