#!/usr/bin/env python3
"""Does adding 00635U.TW (gold futures ETF) to the a2118 defensive basket
help 2022 (stocks-and-bonds-down) without hurting COVID V-recovery or
long-bull terminal value, 2017-2026?

Research-only. Reuses backtest_group_a_plus_defensive_basket.py's entire
regime-detection (A207_RULE via _switch_returns), cost-simulation
(_simulate_costed_curve, _episode_curve), and episode-selection machinery
UNMODIFIED ON DISK -- this script imports that module and monkey-patches its
module-level TICKERS tuple and DEFENSIVE_BASKETS dict IN THIS PROCESS ONLY
(never writes to the .py file), so every function in that module picks up
00635U.TW transparently via Python's normal global-name lookup. The live
production a2118 basket ("bond0_cash60") and every existing DEFENSIVE_BASKETS
entry are left untouched; three new entries are appended in memory.

Motivation: a2118's defensive basket is currently 0050 40% / cash 60%
(00679B bonds were removed 2026-08-18 after 2601.21447 follow-up research
found bonds only hedged 1 of 7 defensive episodes and fell *more* than 0050
in 2022 and 2025-03 -- see feedback_golden1_0531_immutable_naming's sibling
memory project_a2118_defensive_basket_00679b_removed_promoted_20260818).
2022 was specifically a stocks-and-bonds-down regime (rate-hike driven),
which is exactly the scenario gold sometimes decouples from. This asks
whether gold succeeds where bonds failed, without giving back the COVID
V-shaped recovery capture or long-bull compounding that motivated moving
to cash in the first place.

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

GOLD_TICKER = "00635U.TW"
GOLD_BASKETS = {
    "gold0_cash60": {"0050.TW": 0.40, GOLD_TICKER: 0.00, "cash": 0.60},
    "gold10_cash50": {"0050.TW": 0.40, GOLD_TICKER: 0.10, "cash": 0.50},
    "gold20_cash40": {"0050.TW": 0.40, GOLD_TICKER: 0.20, "cash": 0.40},
}
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_defensive_basket_gold_00635u_20260821.json"


def _episode_label(start, end) -> str:
    """Coarse label for readability -- COVID/2022/other -- by date overlap."""
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

    # Monkey-patch the imported modules' globals in THIS process only --
    # neither .py file on disk is ever touched. Two modules need patching,
    # not one: backtest_group_a_plus_defensive_basket.TICKERS controls the
    # simulation loop, but _normalize() (and _weights_from_group_a/_plus)
    # are DEFINED in backtest_group_a_plus_policy_signal and read THAT
    # module's own TICKERS global -- missed on the first attempt, which
    # silently dropped 00635U.TW during _normalize() and renormalized its
    # weight onto 0050.TW instead (caught by manually recomputing the
    # expected blended return for the COVID episode and finding gold's
    # +9.7% return somehow made the episode WORSE, not better -- traced to
    # _normalize()'s output missing the 00635U.TW key entirely).
    original_tickers = basket_mod.TICKERS
    original_policy_tickers = policy_signal_mod.TICKERS
    extended_tickers = tuple(original_tickers) + (GOLD_TICKER,)
    basket_mod.TICKERS = extended_tickers
    policy_signal_mod.TICKERS = extended_tickers
    basket_mod.DEFENSIVE_BASKETS = dict(basket_mod.DEFENSIVE_BASKETS)
    basket_mod.DEFENSIVE_BASKETS.update(GOLD_BASKETS)

    policy_signal, _ = _load_policy_signal(_resolve(args.decision_pointer))
    golden_signal = _load(_resolve(args.golden_signal))
    current_defensive = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)

    keep_baskets = ["current_a207", "bond0_cash60", "gold0_cash60", "gold10_cash50", "gold20_cash40"]
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

    # ── Full-window base-scenario comparison (no delay/cost stress) ──
    rows: list[dict[str, Any]] = []
    curves: dict[str, Any] = {}
    for basket_name, defensive_weights in baskets.items():
        weights_by_regime = {"golden1": golden_weights, "group_a_plus_defensive": defensive_weights}
        curve, execution = basket_mod._simulate_costed_curve(
            total_return_prices, frame["regime"], weights_by_regime,
            args.initial_value, args.commission_rate, args.slippage_rate, args.equity_etf_sell_tax,
        )
        metrics = _metrics(curve, args.initial_value)
        rows.append({"basket": basket_name, **metrics, **execution})
        curves[basket_name] = curve

    print("\n=== full-window (2017-2026) ===")
    for row in rows:
        print(
            f"  {row['basket']}: final_value={row['final_value']:,.0f} sharpe={row['sharpe_ratio']:.3f} "
            f"mdd={row['max_drawdown']:.4f} rebalances={row['rebalance_count']}"
        )

    # ── Stress-episode breakdown (COVID / 2022 / post-2023), reusing the
    # module's own episode detector so labels line up with its own A207
    # thresholds rather than a hand-picked date range. ──
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

    # ── Per-episode detail for the gold baskets specifically, tagged with
    # coarse COVID/2022/post-2023 labels for direct reading. ──
    per_episode_detail: list[dict[str, Any]] = []
    for ep in stress_episodes:
        import pandas as pd

        start, end = pd.Timestamp(ep["start"]), pd.Timestamp(ep["end"])
        segment = total_return_prices.loc[start:end]
        row: dict[str, Any] = {
            "episode": ep["episode"], "start": ep["start"], "end": ep["end"],
            "label": _episode_label(start, end), "trading_days": ep["trading_days"],
        }
        for basket_name in ("bond0_cash60", "gold0_cash60", "gold10_cash50", "gold20_cash40"):
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
            f"gold0={row['gold0_cash60_total_return']:+.4f} "
            f"gold10={row['gold10_cash50_total_return']:+.4f} "
            f"gold20={row['gold20_cash40_total_return']:+.4f}"
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

    # restore (harmless in a one-shot script, but keeps the monkey-patch
    # scoped/explicit if this module is ever imported elsewhere in-process)
    basket_mod.TICKERS = original_tickers
    policy_signal_mod.TICKERS = original_policy_tickers


if __name__ == "__main__":
    main()
