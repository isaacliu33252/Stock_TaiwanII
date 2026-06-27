#!/usr/bin/env python3
"""Test staged defensive exposure and adaptive recovery around A20.7."""

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
from group_a_plus.runners.a207 import A207_RULE


PROJECT_ROOT = Path(__file__).resolve().parent
EXPOSURE_LEVELS = (0.0, 0.1, 0.2, 0.25, 0.5, 0.75, 1.0)


def _parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def _parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _blend_weights(
    golden_weights: dict[str, float], defensive_weights: dict[str, float], defensive_share: float
) -> dict[str, float]:
    share = min(max(float(defensive_share), 0.0), 1.0)
    keys = set(golden_weights) | set(defensive_weights)
    return _normalize(
        {
            key: (1.0 - share) * float(golden_weights.get(key, 0.0) or 0.0)
            + share * float(defensive_weights.get(key, 0.0) or 0.0)
            for key in keys
        }
    )


def _level_name(defensive_share: float) -> str:
    return f"defense_{int(round(defensive_share * 100)):03d}"


def _dynamic_exposure(
    features: pd.DataFrame,
    warn_score: int,
    warn_ma_gap: float,
    warn_drawdown: float,
    initial_defense_share: float,
    recovery_step: float,
    min_tail_score: int = 0,
    warning_confirm_days: int = 1,
    vol_trigger: float = 1.2,
    vol_ma_relief: float = 0.005,
    vol_drawdown_relief: float = 0.015,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Map A20.7 plus early warnings to discrete defensive-weight shares."""
    current = 0.0
    events: list[dict[str, Any]] = []
    shares: list[float] = []
    desired_shares: list[float] = []
    reasons: list[str] = []
    warning_streak = 0

    for dt, row in features.iterrows():
        baseline_defense = str(row["regime"]) == "group_a_plus_defensive"
        high_vol = float(row["realized_vol_ratio_20_60"]) >= vol_trigger
        ma_limit = warn_ma_gap + (vol_ma_relief if high_vol else 0.0)
        drawdown_limit = warn_drawdown + (vol_drawdown_relief if high_vol else 0.0)
        price_warning = float(row["ma_gap"]) <= ma_limit or float(row["drawdown"]) <= drawdown_limit
        risk_score = int(row["total_risk_score"])
        tail_confirmed = int(row.get("tail_risk_score", 0)) >= min_tail_score
        raw_warning = price_warning and risk_score >= warn_score and tail_confirmed
        warning_streak = warning_streak + 1 if raw_warning else 0
        warning_confirmed = warning_streak >= max(1, warning_confirm_days)

        if baseline_defense:
            desired = 1.0
            reason = "a207_full_defense"
        elif warning_confirmed and risk_score >= warn_score + 1:
            desired = min(0.75, initial_defense_share * 2.0)
            reason = "strong_warning"
        elif warning_confirmed:
            desired = initial_defense_share
            reason = "warning"
        else:
            desired = 0.0
            reason = "normal"

        previous = current
        if desired >= current:
            current = desired
        else:
            calm_recovery = float(row["exit_momentum"]) > 0.0 and not high_vol
            step = recovery_step if calm_recovery else min(recovery_step, 0.25)
            current = max(desired, current - step)
            reason = "calm_recovery" if calm_recovery else "cautious_recovery"
        current = min(EXPOSURE_LEVELS, key=lambda level: abs(level - current))

        if current != previous:
            events.append(
                {
                    "date": str(dt.date()),
                    "from_defensive_share": previous,
                    "to_defensive_share": current,
                    "baseline_regime": str(row["regime"]),
                    "ma_gap": float(row["ma_gap"]),
                    "drawdown": float(row["drawdown"]),
                    "total_risk_score": risk_score,
                    "vol_ratio_20_60": float(row["realized_vol_ratio_20_60"]),
                }
            )
        shares.append(current)
        desired_shares.append(desired)
        reasons.append(reason)

    frame = features.copy()
    frame["defensive_share"] = shares
    frame["desired_defensive_share"] = desired_shares
    frame["exposure_reason"] = reasons
    frame["dynamic_regime"] = [_level_name(value) for value in shares]
    return frame, events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--warn-scores", default="4,5")
    parser.add_argument("--warn-ma-gaps", default="-0.005,-0.01")
    parser.add_argument("--warn-drawdowns", default="-0.06,-0.08")
    parser.add_argument("--initial-defense-shares", default="0.25,0.5")
    parser.add_argument("--recovery-steps", default="0.25,0.5")
    parser.add_argument("--min-tail-scores", default="0")
    parser.add_argument("--warning-confirm-days", default="1")
    parser.add_argument("--output-prefix", default="results/group_a_plus_dynamic_exposure_20260619")
    args = parser.parse_args()

    policy_signal, policy_signal_path = _load_policy_signal(_resolve(args.decision_pointer))
    golden_signal_path = _resolve(args.golden_signal)
    golden_signal = _load(golden_signal_path)
    defensive_weights = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)
    weights_by_regime = {
        _level_name(level): _blend_weights(golden_weights, defensive_weights, level)
        for level in EXPOSURE_LEVELS
    }

    prices = _load_prices(_resolve(args.db), list(TICKERS), args.start, args.end)
    chip_features = _load_chip_features(_resolve(args.db), prices.index, args.start, args.end)
    _base_events, a207_frame = _switch_returns(prices, chip_features, A207_RULE)
    baseline_weights = {
        "golden1": golden_weights,
        "group_a_plus_defensive": defensive_weights,
    }
    baseline_curve = _simulate_regime_curve(prices, a207_frame["regime"], baseline_weights, args.initial_value)
    baseline_metrics = _metrics(baseline_curve, args.initial_value)

    rows: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    for warn_score in _parse_int_list(args.warn_scores):
        for warn_ma_gap in _parse_float_list(args.warn_ma_gaps):
            for warn_drawdown in _parse_float_list(args.warn_drawdowns):
                for initial_share in _parse_float_list(args.initial_defense_shares):
                    for recovery_step in _parse_float_list(args.recovery_steps):
                        for min_tail_score in _parse_int_list(args.min_tail_scores):
                            for confirm_days in _parse_int_list(args.warning_confirm_days):
                                variant = (
                                    f"dynamic_ws{warn_score}_ma{int(abs(warn_ma_gap) * 1000):03d}"
                                    f"_dd{int(abs(warn_drawdown) * 100):02d}_d{int(initial_share * 100):02d}"
                                    f"_r{int(recovery_step * 100):02d}_t{min_tail_score}_c{confirm_days}"
                                )
                                frame, events = _dynamic_exposure(
                                    a207_frame,
                                    warn_score,
                                    warn_ma_gap,
                                    warn_drawdown,
                                    initial_share,
                                    recovery_step,
                                    min_tail_score,
                                    confirm_days,
                                )
                                curve = _simulate_regime_curve(
                                    prices, frame["dynamic_regime"], weights_by_regime, args.initial_value
                                )
                                metrics = _metrics(curve, args.initial_value)
                                baseline_share = (a207_frame["regime"] == "group_a_plus_defensive").astype(float)
                                override_days = int((frame["defensive_share"] != baseline_share).sum())
                                rows.append(
                                    {
                                        "variant": variant,
                                        **metrics,
                                        "warn_score": warn_score,
                                        "warn_ma_gap": warn_ma_gap,
                                        "warn_drawdown": warn_drawdown,
                                        "initial_defense_share": initial_share,
                                        "recovery_step": recovery_step,
                                        "min_tail_score": min_tail_score,
                                        "warning_confirm_days": confirm_days,
                                        "effective_override_days": override_days,
                                        "override_days": override_days,
                                        "rebalance_events": len(events),
                                        "full_defense_days": int((frame["defensive_share"] == 1.0).sum()),
                                        "partial_defense_days": int(frame["defensive_share"].between(0.01, 0.99).sum()),
                                    }
                                )
                                frame["portfolio_value"] = curve
                                frames[variant] = frame

    formal = [
        row
        for row in rows
        if row["final_value"] >= baseline_metrics["final_value"]
        and row["sharpe_ratio"] >= baseline_metrics["sharpe_ratio"]
        and row["max_drawdown"] >= baseline_metrics["max_drawdown"]
        and row["effective_override_days"] > 0
    ]
    effective = [row for row in rows if row["effective_override_days"] > 0]
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
        "experiment": "group_a_plus_a207_dynamic_exposure",
        "method_note": (
            "A20.7 full-defense signals remain authoritative. Early price/risk warnings use partial "
            "defensive weights; recovery is stepped and faster only with positive momentum and calm volatility."
        ),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "actual_window": {
            "start": str(prices.index[0].date()),
            "end": str(prices.index[-1].date()),
            "rows": int(len(prices)),
        },
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
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
    prefix.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(prefix.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    frames[best["variant"]].to_csv(prefix.with_name(prefix.name + "_best_frame.csv"), encoding="utf-8-sig")
    print(f"JSON: {prefix.with_suffix('.json')}")
    print(f"Best: {best['variant']}")


if __name__ == "__main__":
    main()
