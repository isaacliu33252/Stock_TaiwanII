#!/usr/bin/env python3
"""Refine scaling-tail overlays with warmup and valid Hill-alpha gating."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
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
from backtest_group_a_plus_scaling_tail import A207_RULE, _scaling_tail_features
from backtest_group_a_plus_switch_policy import (
    DB_PATH,
    _load_chip_features,
    _load_prices,
    _metrics,
    _simulate_regime_curve,
    _switch_returns,
)


PROJECT_ROOT = Path(__file__).resolve().parent


def _parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def _parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _warmup_start(start: str, warmup_days: int) -> str:
    return str((pd.Timestamp(start) - pd.Timedelta(days=warmup_days)).date())


def _addon_regime(
    features: pd.DataFrame,
    a207_regime: pd.Series,
    min_score: int,
    max_alpha: float,
    min_cluster: int,
    max_return_5d: float,
    hold_days: int,
) -> tuple[pd.DataFrame, list[str]]:
    alpha = features["hill_left_tail_alpha"].to_numpy()
    base_regime = a207_regime.to_numpy(dtype=object)
    stress = (
        (features["multi_scale_breach_score"].to_numpy() >= min_score)
        & (alpha > 0.0)
        & (alpha <= max_alpha)
        & (features["tail_breach_cluster_20d"].to_numpy() >= min_cluster)
        & (features["return_0050_5d"].to_numpy() <= max_return_5d)
        & (base_regime == "golden1")
    )
    regime = base_regime.copy()
    active = 0
    trigger_dates: list[str] = []
    for i, dt in enumerate(features.index):
        if active > 0:
            if base_regime[i] == "golden1":
                regime[i] = "group_a_plus_defensive"
            active -= 1
        elif stress[i]:
            regime[i] = "group_a_plus_defensive"
            active = hold_days - 1
            trigger_dates.append(str(dt.date()))
    frame = features.copy()
    frame["scaling_ready_trigger"] = stress.astype(int)
    frame["regime"] = regime
    return frame, trigger_dates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--warmup-days", type=int, default=900)
    parser.add_argument("--window", type=int, default=378)
    parser.add_argument("--tail-count", type=int, default=8)
    parser.add_argument("--quantile", type=float, default=0.03)
    parser.add_argument("--min-score", type=int, default=2)
    parser.add_argument("--max-alphas", default="2.6,3.0,3.5")
    parser.add_argument("--min-clusters", default="2,3")
    parser.add_argument("--max-return-5d", default="0.0,-0.01,-0.02")
    parser.add_argument("--hold-days", default="1,2,3,5")
    parser.add_argument("--output-prefix", default="results/group_a_plus_scaling_tail_ready_20260619")
    args = parser.parse_args()

    policy_signal, policy_signal_path = _load_policy_signal(_resolve(args.decision_pointer))
    golden_signal_path = _resolve(args.golden_signal)
    golden_signal = _load(golden_signal_path)
    defensive_weights = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)
    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": defensive_weights,
    }

    prices = _load_prices(_resolve(args.db), list(TICKERS), args.start, args.end)
    chip_features = _load_chip_features(_resolve(args.db), prices.index, args.start, args.end)
    _events, a207_frame = _switch_returns(prices, chip_features, A207_RULE)
    baseline_curve = _simulate_regime_curve(prices, a207_frame["regime"], weights_by_regime, args.initial_value)
    baseline_metrics = _metrics(baseline_curve, args.initial_value)

    warmup_start = _warmup_start(args.start, args.warmup_days)
    warmup_prices = _load_prices(_resolve(args.db), list(TICKERS), warmup_start, args.end)
    features = _scaling_tail_features(
        warmup_prices,
        args.window,
        args.tail_count,
        args.quantile,
    ).reindex(prices.index).fillna(0.0)

    rows: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    for max_alpha in _parse_float_list(args.max_alphas):
        for min_cluster in _parse_int_list(args.min_clusters):
            for max_return in _parse_float_list(args.max_return_5d):
                for hold_days in _parse_int_list(args.hold_days):
                    label = (
                        f"scaling_ready_w{args.window}_k{args.tail_count}_q{int(args.quantile * 100):02d}"
                        f"_s{args.min_score}_a{int(max_alpha * 10):02d}_c{min_cluster}"
                        f"_r{int(abs(max_return) * 100):02d}_h{hold_days}"
                    )
                    frame, trigger_dates = _addon_regime(
                        features,
                        a207_frame["regime"],
                        args.min_score,
                        max_alpha,
                        min_cluster,
                        max_return,
                        hold_days,
                    )
                    curve = _simulate_regime_curve(prices, frame["regime"], weights_by_regime, args.initial_value)
                    metrics = _metrics(curve, args.initial_value)
                    override_days = int((frame["regime"] != a207_frame["regime"]).sum())
                    rows.append(
                        {
                            "variant": label,
                            **metrics,
                            "window": args.window,
                            "tail_count": args.tail_count,
                            "quantile": args.quantile,
                            "min_score": args.min_score,
                            "max_alpha": max_alpha,
                            "min_cluster": min_cluster,
                            "max_return_5d": max_return,
                            "hold_days": hold_days,
                            "trigger_days": len(trigger_dates),
                            "override_days": override_days,
                            "trigger_dates": trigger_dates,
                        }
                    )
                    frames[label] = frame

    formal = [
        row
        for row in rows
        if row["final_value"] >= baseline_metrics["final_value"]
        and row["sharpe_ratio"] >= baseline_metrics["sharpe_ratio"]
        and row["max_drawdown"] >= baseline_metrics["max_drawdown"]
        and row["override_days"] > 0
    ]
    effective = [row for row in rows if row["override_days"] > 0]
    ranked = sorted(
        effective or rows,
        key=lambda row: (
            row in formal,
            row["sharpe_ratio"],
            row["max_drawdown"],
            row["final_value"],
        ),
        reverse=True,
    )
    best = ranked[0]
    report = {
        "experiment": "group_a_plus_scaling_tail_ready_addon",
        "method_note": (
            "Hill alpha must be positive, so insufficient rolling history is not treated as stress. "
            "Features use pre-window warmup data and can only override A20.7 while it is in golden1."
        ),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requested_window": {"start": args.start, "end": args.end},
        "warmup_start": warmup_start,
        "actual_window": {
            "start": str(prices.index[0].date()),
            "end": str(prices.index[-1].date()),
            "rows": int(len(prices)),
        },
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
        },
        "weights": {
            "golden1_0531_1m": _normalize(golden_weights),
            "group_a_plus_defensive_1m": _normalize(defensive_weights),
        },
        "summary": {"a207": baseline_metrics},
        "rows": rows,
        "effective_candidate_count": len(effective),
        "formal_upgrade_pass_count": len(formal),
        "top_formal": sorted(
            formal,
            key=lambda row: (row["sharpe_ratio"], row["max_drawdown"], row["final_value"]),
            reverse=True,
        )[:10],
        "best": best,
    }

    prefix = Path(args.output_prefix)
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    best_frame_path = prefix.with_name(prefix.name + "_best_frame.csv")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    frames[best["variant"]].to_csv(best_frame_path, encoding="utf-8-sig")

    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print(f"Best frame: {best_frame_path}")
    print(f"Formal passes: {len(formal)} / {len(rows)}")
    print(
        f"Best: {best['variant']} final={best['final_value']:,.0f}, "
        f"sharpe={best['sharpe_ratio']:.3f}, mdd={best['max_drawdown']:.2%}, "
        f"overrides={best['override_days']}"
    )


if __name__ == "__main__":
    main()
