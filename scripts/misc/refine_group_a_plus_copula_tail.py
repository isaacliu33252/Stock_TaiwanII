#!/usr/bin/env python3
"""Focused refinement for the GroupA+ copula tail overlay."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_a_plus_copula_tail import A207_RULE, MA20_RULE, _copula_tail_features
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


PROJECT_ROOT = Path(__file__).resolve().parent


def _parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def _parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _addon_regime(
    features: pd.DataFrame,
    a207_regime: pd.Series,
    min_score: int,
    min_intensity: float,
    max_return_5d: float,
    cooldown_days: int,
    require_a207_golden: bool,
) -> pd.DataFrame:
    regimes: list[str] = []
    cooldown = 0
    triggers: list[int] = []
    for dt, row in features.iterrows():
        if cooldown > 0:
            cooldown -= 1
        trigger = (
            cooldown == 0
            and int(row["joint_tail_score"]) >= min_score
            and float(row["joint_tail_intensity"]) >= min_intensity
            and float(row["return_0050_5d"]) <= max_return_5d
            and (not require_a207_golden or str(a207_regime.loc[dt]) == "golden1")
        )
        if trigger:
            cooldown = cooldown_days
        triggers.append(int(trigger))
        regimes.append("group_a_plus_defensive" if trigger else str(a207_regime.loc[dt]))
    frame = features.copy()
    frame["copula_addon_trigger"] = triggers
    frame["regime"] = regimes
    return frame


def _selector_regime(
    features: pd.DataFrame,
    a207_regime: pd.Series,
    ma20_regime: pd.Series,
    min_score: int,
    min_intensity: float,
    max_return_5d: float,
    require_a207_golden: bool,
) -> pd.DataFrame:
    trigger = (
        (features["joint_tail_score"] >= min_score)
        & (features["joint_tail_intensity"] >= min_intensity)
        & (features["return_0050_5d"] <= max_return_5d)
    )
    if require_a207_golden:
        trigger = trigger & a207_regime.eq("golden1")
    frame = features.copy()
    frame["copula_selector_trigger"] = trigger.astype(int)
    frame["regime"] = a207_regime.copy()
    frame.loc[trigger, "regime"] = ma20_regime.loc[trigger]
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--windows", default="40,60,90,126")
    parser.add_argument("--tail-qs", default="0.03,0.05,0.07,0.10")
    parser.add_argument("--min-scores", default="2,3,4")
    parser.add_argument("--min-intensities", default="0.0,0.25,0.50,0.70")
    parser.add_argument("--max-return-5d", default="-0.02,-0.03,-0.04,-0.06")
    parser.add_argument("--cooldown-days", default="0,5,10,20")
    parser.add_argument("--output-prefix", default="results/group_a_plus_copula_tail_refine_20260619")
    args = parser.parse_args()

    policy_signal, policy_signal_path = _load_policy_signal(_resolve(args.decision_pointer))
    golden_signal_path = _resolve(args.golden_signal)
    golden_signal = _load(golden_signal_path)
    defensive_weights = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)
    prices = _load_prices(_resolve(args.db), list(TICKERS), args.start, args.end)
    chip_features = _load_chip_features(_resolve(args.db), prices.index, args.start, args.end)
    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": defensive_weights,
    }
    _a207_events, a207_frame = _switch_returns(prices, chip_features, A207_RULE)
    _ma20_events, ma20_frame = _switch_returns(prices, chip_features, MA20_RULE)

    base_curves = {
        "a207": _simulate_regime_curve(prices, a207_frame["regime"], weights_by_regime, args.initial_value),
        "ma20": _simulate_regime_curve(prices, ma20_frame["regime"], weights_by_regime, args.initial_value),
    }

    rows: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    for window in _parse_int_list(args.windows):
        for tail_q in _parse_float_list(args.tail_qs):
            features = _copula_tail_features(prices, window, tail_q)
            for min_score in _parse_int_list(args.min_scores):
                for min_intensity in _parse_float_list(args.min_intensities):
                    for max_ret in _parse_float_list(args.max_return_5d):
                        for require_golden in (True, False):
                            label = (
                                f"selector_w{window}_q{int(tail_q*100):02d}_s{min_score}"
                                f"_i{int(min_intensity*100):02d}_r{int(abs(max_ret)*100):02d}"
                                f"_{'golden' if require_golden else 'any'}"
                            )
                            frame = _selector_regime(
                                features,
                                a207_frame["regime"],
                                ma20_frame["regime"],
                                min_score,
                                min_intensity,
                                max_ret,
                                require_golden,
                            )
                            curve = _simulate_regime_curve(prices, frame["regime"], weights_by_regime, args.initial_value)
                            metrics = _metrics(curve, args.initial_value)
                            rows.append(
                                {
                                    "variant": label,
                                    "mode": "selector",
                                    **metrics,
                                    "window": window,
                                    "tail_q": tail_q,
                                    "min_score": min_score,
                                    "min_intensity": min_intensity,
                                    "max_return_5d": max_ret,
                                    "cooldown_days": None,
                                    "require_a207_golden": require_golden,
                                    "trigger_days": int(frame["copula_selector_trigger"].sum()),
                                    "defense_days": int((frame["regime"] == "group_a_plus_defensive").sum()),
                                }
                            )
                            frames[label] = frame
                            for cooldown in _parse_int_list(args.cooldown_days):
                                addon_label = (
                                    f"addon_w{window}_q{int(tail_q*100):02d}_s{min_score}"
                                    f"_i{int(min_intensity*100):02d}_r{int(abs(max_ret)*100):02d}"
                                    f"_cd{cooldown}_{'golden' if require_golden else 'any'}"
                                )
                                addon_frame = _addon_regime(
                                    features,
                                    a207_frame["regime"],
                                    min_score,
                                    min_intensity,
                                    max_ret,
                                    cooldown,
                                    require_golden,
                                )
                                addon_curve = _simulate_regime_curve(
                                    prices,
                                    addon_frame["regime"],
                                    weights_by_regime,
                                    args.initial_value,
                                )
                                metrics = _metrics(addon_curve, args.initial_value)
                                rows.append(
                                    {
                                        "variant": addon_label,
                                        "mode": "addon",
                                        **metrics,
                                        "window": window,
                                        "tail_q": tail_q,
                                        "min_score": min_score,
                                        "min_intensity": min_intensity,
                                        "max_return_5d": max_ret,
                                        "cooldown_days": cooldown,
                                        "require_a207_golden": require_golden,
                                        "trigger_days": int(addon_frame["copula_addon_trigger"].sum()),
                                        "defense_days": int((addon_frame["regime"] == "group_a_plus_defensive").sum()),
                                    }
                                )
                                frames[addon_label] = addon_frame

    summary = {name: _metrics(curve, args.initial_value) for name, curve in base_curves.items()}
    a207_metrics = summary["a207"]
    passing = [
        row for row in rows
        if row["final_value"] >= a207_metrics["final_value"] * 0.98
        and row["sharpe_ratio"] >= a207_metrics["sharpe_ratio"]
        and row["max_drawdown"] >= a207_metrics["max_drawdown"]
    ]
    ranked = sorted(rows, key=lambda row: (row["sharpe_ratio"], row["max_drawdown"], row["final_value"]), reverse=True)
    best = (passing or ranked)[0]
    report = {
        "experiment": "group_a_plus_copula_tail_refine",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requested_window": {"start": args.start, "end": args.end},
        "actual_window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": int(len(prices))},
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
        },
        "weights": {
            "golden1_0531_1m": _normalize(golden_weights),
            "group_a_plus_defensive_1m": _normalize(defensive_weights),
        },
        "summary": summary,
        "rows": rows,
        "passing_count": len(passing),
        "top_passing": sorted(passing, key=lambda row: (row["final_value"], row["sharpe_ratio"]), reverse=True)[:10],
        "top_by_sharpe": ranked[:10],
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
    print(f"Window: {report['actual_window']['start']} ~ {report['actual_window']['end']} ({report['actual_window']['rows']} rows)")
    print(
        f"A20.7: final={a207_metrics['final_value']:,.0f}, sharpe={a207_metrics['sharpe_ratio']:.3f}, "
        f"mdd={a207_metrics['max_drawdown']:.2%}"
    )
    print(f"Passing: {len(passing)} / {len(rows)}")
    print(
        f"Best: {best['variant']} final={best['final_value']:,.0f}, sharpe={best['sharpe_ratio']:.3f}, "
        f"mdd={best['max_drawdown']:.2%}, triggers={best['trigger_days']}"
    )


if __name__ == "__main__":
    main()
