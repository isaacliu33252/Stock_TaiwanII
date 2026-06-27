"""Standardized runner for the formal GroupA+ A20.7 switch baseline."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

import pandas as pd

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
    _load_chip_features,
    _load_prices,
    _metrics,
    _simulate_regime_curve,
    _switch_returns,
)
from group_a_plus.paths import PROJECT_ROOT
from tw_output_standard import OutputStandardizer, write_standard_output


A207_RULE = SwitchRule(
    "risk_ma75_dd11_total6_hold5_eg0175_xg020",
    75,
    -0.0175,
    0.02,
    75,
    -0.11,
    5,
    5,
    0,
    None,
    0,
    None,
    6,
    6,
)


def run_a207(start: str, end: str, initial_value: float, db: Path) -> tuple[dict, pd.DataFrame]:
    policy_signal, policy_signal_path = _load_policy_signal(_resolve(DEFAULT_DECISION_POINTER))
    golden_signal_path = _resolve(DEFAULT_GOLDEN_SIGNAL)
    golden_signal = _load(golden_signal_path)
    defensive_weights = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)
    prices = _load_prices(_resolve(db), list(TICKERS), start, end)
    chip_features = _load_chip_features(_resolve(db), prices.index, start, end)
    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": defensive_weights,
    }
    events, frame = _switch_returns(prices, chip_features, A207_RULE)
    curve = _simulate_regime_curve(prices, frame["regime"], weights_by_regime, initial_value)
    out_frame = frame.copy()
    out_frame["portfolio_value"] = curve
    report = {
        "experiment": "group_a_plus_a207_standard_runner",
        "strategy": A207_RULE.name,
        "window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": int(len(prices))},
        "metrics": _metrics(curve, initial_value),
        "events": events,
        "rule": asdict(A207_RULE),
        "weights": {
            "golden1_0531_1m": _normalize(golden_weights),
            "group_a_plus_defensive_1m": _normalize(defensive_weights),
        },
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
        },
    }
    return report, out_frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output", default="results/group_a_plus_runner_a207_2025_2026_20260619.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a207_2025_2026_20260619_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a207")
    try:
        report, frame = run_a207(args.start, args.end, args.initial_value, Path(args.db))
        Path(args.frame_output).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.frame_output, encoding="utf-8-sig")
        payload = std.success(report, frame_output=args.frame_output)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Runner JSON: {Path(args.output).resolve()}")
    print(f"Runner frame: {Path(args.frame_output).resolve()}")


if __name__ == "__main__":
    main()

