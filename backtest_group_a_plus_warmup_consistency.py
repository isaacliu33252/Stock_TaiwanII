#!/usr/bin/env python3
"""Evaluate A20.7 with pre-window feature warmup for start-date consistency."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

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
    _load_chip_features,
    _load_prices,
    _metrics,
    _simulate_regime_curve,
    _switch_returns,
)
from group_a_plus.runners.a207 import A207_RULE, run_a207


PROJECT_ROOT = Path(__file__).resolve().parent


def _parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _warmup_start(start: str, warmup_days: int) -> str:
    return str((pd.Timestamp(start) - pd.Timedelta(days=warmup_days)).date())


def _trim_window(
    prices: pd.DataFrame,
    frame: pd.DataFrame,
    events: list[dict[str, Any]],
    start: str,
    end: str,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    mask = (prices.index >= start_ts) & (prices.index <= end_ts)
    trimmed_prices = prices.loc[mask].copy()
    trimmed_frame = frame.reindex(trimmed_prices.index).copy()
    trimmed_events = [
        event for event in events
        if start_ts <= pd.Timestamp(event["date"]) <= end_ts
    ]
    return trimmed_prices, trimmed_frame, trimmed_events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--warmup-days", default="180,365,540")
    parser.add_argument("--output-prefix", default="results/group_a_plus_warmup_consistency_20260620")
    args = parser.parse_args()

    policy_signal, policy_signal_path = _load_policy_signal(_resolve(args.decision_pointer))
    golden_signal_path = _resolve(args.golden_signal)
    golden_signal = _load(golden_signal_path)
    defensive_weights = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)
    weights_by_regime = {"golden1": golden_weights, "group_a_plus_defensive": defensive_weights}

    baseline_report, baseline_frame = run_a207(args.start, args.end, args.initial_value, Path(args.db))
    baseline_metrics = baseline_report["metrics"]
    rows: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    events_by_variant: dict[str, list[dict[str, Any]]] = {}
    for warmup_days in _parse_int_list(args.warmup_days):
        load_start = _warmup_start(args.start, warmup_days)
        full_prices = _load_prices(_resolve(args.db), list(TICKERS), load_start, args.end)
        full_chip = _load_chip_features(_resolve(args.db), full_prices.index, load_start, args.end)
        full_events, full_frame = _switch_returns(full_prices, full_chip, A207_RULE)
        prices, frame, events = _trim_window(full_prices, full_frame, full_events, args.start, args.end)
        if prices.empty:
            raise RuntimeError(f"No requested-window prices after warmup from {load_start}")
        curve = _simulate_regime_curve(prices, frame["regime"], weights_by_regime, args.initial_value)
        metrics = _metrics(curve, args.initial_value)
        variant = f"a209_warmup_{warmup_days}d"
        override_days = int((frame["regime"] != baseline_frame.reindex(frame.index)["regime"]).sum())
        rows.append(
            {
                "variant": variant,
                **metrics,
                "warmup_days": warmup_days,
                "warmup_start": load_start,
                "effective_override_days": override_days,
                "override_days": override_days,
                "event_count": len(events),
                "initial_regime": str(frame["regime"].iloc[0]),
                "event_dates": [event["date"] for event in events],
            }
        )
        out_frame = frame.copy()
        out_frame["portfolio_value"] = curve
        frames[variant] = out_frame
        events_by_variant[variant] = events

    formal = [
        row for row in rows
        if row["final_value"] >= baseline_metrics["final_value"]
        and row["sharpe_ratio"] >= baseline_metrics["sharpe_ratio"]
        and row["max_drawdown"] >= baseline_metrics["max_drawdown"]
        and row["override_days"] > 0
    ]
    stable_groups: dict[tuple[str, ...], list[str]] = {}
    for row in rows:
        stable_groups.setdefault(tuple(row["event_dates"]), []).append(row["variant"])
    stable = len(stable_groups) == 1
    ranked = sorted(
        rows,
        key=lambda row: (row in formal, row["sharpe_ratio"], row["max_drawdown"], row["final_value"]),
        reverse=True,
    )
    best = ranked[0]
    report = {
        "experiment": "group_a_plus_a209_warmup_consistency",
        "method_note": (
            "A20.7 features and state are computed before the requested start, then prices, regimes, "
            "events, and performance are trimmed to the requested evaluation window."
        ),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "actual_window": {
            "start": str(baseline_frame.index[0].date()),
            "end": str(baseline_frame.index[-1].date()),
            "rows": int(len(baseline_frame)),
        },
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
        },
        "weights": {
            "golden1_0531_1m": _normalize(golden_weights),
            "group_a_plus_defensive_1m": _normalize(defensive_weights),
        },
        "summary": {"a207_no_warmup": baseline_metrics},
        "baseline_events": baseline_report["events"],
        "rows": rows,
        "warmup_event_stable": stable,
        "event_groups": [
            {"event_dates": list(event_dates), "variants": variants}
            for event_dates, variants in stable_groups.items()
        ],
        "formal_upgrade_pass_count": len(formal),
        "top_formal": formal,
        "best": best,
        "best_events": events_by_variant[best["variant"]],
    }

    prefix = Path(args.output_prefix)
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(prefix.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    frames[best["variant"]].to_csv(prefix.with_name(prefix.name + "_best_frame.csv"), encoding="utf-8-sig")
    print(f"JSON: {prefix.with_suffix('.json')}")
    print(f"Best: {best['variant']}")


if __name__ == "__main__":
    main()
