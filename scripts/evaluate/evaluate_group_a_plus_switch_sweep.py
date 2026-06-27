#!/usr/bin/env python3
"""針對 GroupA+ / Golden1 switch policy 做小網格掃描。"""

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
    SwitchRule,
    _load_chip_features,
    _load_prices,
    _metrics,
    _simulate_regime_curve,
    _switch_returns,
)


PROJECT_ROOT = Path(__file__).resolve().parent


def _parse_ints(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _parse_floats(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def _build_rules(
    ma_windows: list[int],
    drawdowns: list[float],
    hold_days: list[int],
    enter_ma_gaps: list[float],
    exit_ma_gaps: list[float],
    chip_scores: list[int],
    derivative_scores: list[int],
    total_risk_scores: list[int],
    tail_risk_scores: list[int],
    cost_gap_below: list[float | None],
    cost_gap_above: list[float | None],
) -> list[SwitchRule]:
    rules: list[SwitchRule] = []
    seen: set[str] = set()
    for ma in ma_windows:
        for dd in drawdowns:
            for hold in hold_days:
                for enter_gap in enter_ma_gaps:
                    for exit_gap in exit_ma_gaps:
                        for chip in chip_scores:
                            for deriv in derivative_scores:
                                for total_risk in total_risk_scores:
                                    for tail_risk in tail_risk_scores:
                                        for below in cost_gap_below:
                                            for above in cost_gap_above:
                                                if below is not None and above is not None:
                                                    continue
                                                suffix = f"ma{ma}_dd{int(abs(dd) * 100):02d}_hold{hold}_eg{int(abs(enter_gap)*1000):03d}_xg{int(exit_gap*1000):03d}"
                                                if chip:
                                                    suffix = f"chip{chip}_" + suffix
                                                if deriv:
                                                    suffix = f"deriv{deriv}_" + suffix
                                                if total_risk:
                                                    suffix = f"risk{total_risk}_" + suffix
                                                if tail_risk:
                                                    suffix = f"tail{tail_risk}_" + suffix
                                                if below is not None:
                                                    suffix = f"costb{int(abs(below)*1000):03d}_" + suffix
                                                if above is not None:
                                                    suffix = f"costa{int(abs(above)*1000):03d}_" + suffix
                                                if suffix in seen:
                                                    continue
                                                seen.add(suffix)
                                                rules.append(
                                                    SwitchRule(
                                                        suffix,
                                                        ma,
                                                        enter_gap,
                                                        exit_gap,
                                                        ma,
                                                        dd,
                                                        max(5, min(hold, 20)),
                                                        hold,
                                                        chip,
                                                        chip if chip else None,
                                                        deriv,
                                                        deriv if deriv else None,
                                                        total_risk,
                                                        total_risk if total_risk else None,
                                                        below,
                                                        above,
                                                        0.0 if below is not None else None,
                                                        tail_risk,
                                                        tail_risk if tail_risk else None,
                                                    )
                                                )
    return rules


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-17")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--ma-windows", default="90,120,150")
    parser.add_argument("--drawdowns", default="-0.08,-0.10,-0.12,-0.15")
    parser.add_argument("--hold-days", default="5,10,15,20")
    parser.add_argument("--enter-ma-gaps", default="-0.02,-0.03,-0.04")
    parser.add_argument("--exit-ma-gaps", default="0.01,0.015,0.02")
    parser.add_argument("--chip-scores", default="0")
    parser.add_argument("--derivative-scores", default="0,1")
    parser.add_argument("--total-risk-scores", default="0")
    parser.add_argument("--tail-risk-scores", default="0")
    parser.add_argument("--cost-gap-below", default="none")
    parser.add_argument("--cost-gap-above", default="none")
    parser.add_argument("--output", default="results/group_a_plus_switch_sweep_a20_20260618.json")
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
    baseline_curves = {
        "golden1_0531_1m": _simulate_regime_curve(
            prices,
            pd.Series("golden1", index=prices.index),
            weights_by_regime,
            args.initial_value,
        ),
        "group_a_plus_defensive_1m": _simulate_regime_curve(
            prices,
            pd.Series("group_a_plus_defensive", index=prices.index),
            weights_by_regime,
            args.initial_value,
        ),
    }
    baseline_summary = {name: _metrics(curve, args.initial_value) for name, curve in baseline_curves.items()}

    rules = _build_rules(
        _parse_ints(args.ma_windows),
        _parse_floats(args.drawdowns),
        _parse_ints(args.hold_days),
        _parse_floats(args.enter_ma_gaps),
        _parse_floats(args.exit_ma_gaps),
        _parse_ints(args.chip_scores),
        _parse_ints(args.derivative_scores),
        _parse_ints(args.total_risk_scores),
        _parse_ints(args.tail_risk_scores),
        [None] if args.cost_gap_below.strip().lower() == "none" else [None, *_parse_floats(args.cost_gap_below)],
        [None] if args.cost_gap_above.strip().lower() == "none" else [None, *_parse_floats(args.cost_gap_above)],
    )

    rows: list[dict[str, Any]] = []
    best_regime: pd.DataFrame | None = None
    best_variant = ""
    for rule in rules:
        events, regime_frame = _switch_returns(prices, chip_features, rule)
        curve = _simulate_regime_curve(prices, regime_frame["regime"], weights_by_regime, args.initial_value)
        metrics = _metrics(curve, args.initial_value)
        defense_days = int((regime_frame["regime"] == "group_a_plus_defensive").sum())
        row = {
            "variant": f"switch_{rule.name}",
            "rule": rule.__dict__,
            **metrics,
            "defense_days": defense_days,
            "defense_day_ratio": defense_days / max(len(regime_frame), 1),
            "switch_count": len(events),
            "events": events,
        }
        rows.append(row)
        if not best_variant:
            best_variant = row["variant"]
            best_regime = regime_frame

    eligible = [
        row for row in rows
        if row["final_value"] >= baseline_summary["golden1_0531_1m"]["final_value"] * 0.98
        and row["max_drawdown"] >= baseline_summary["golden1_0531_1m"]["max_drawdown"]
    ]
    ranked = sorted(
        eligible or rows,
        key=lambda row: (
            row["sharpe_ratio"],
            row["max_drawdown"],
            row["final_value"],
            -row["switch_count"],
        ),
        reverse=True,
    )
    best = ranked[0]
    for rule in rules:
        if f"switch_{rule.name}" == best["variant"]:
            _events, best_regime = _switch_returns(prices, chip_features, rule)
            break

    report = {
        "experiment": "group_a_plus_switch_policy_sweep",
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
        "baseline_summary": baseline_summary,
        "eligible_count": len(eligible),
        "rules_total": len(rows),
        "best": best,
        "top10": ranked[:10],
        "rows": rows,
    }

    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame([{k: v for k, v in row.items() if k not in {"rule", "events"}} for row in rows]).to_csv(
        output.with_suffix(".csv"),
        index=False,
        encoding="utf-8-sig",
    )
    if best_regime is not None:
        best_regime.to_csv(output.with_name(output.stem + "_best_regime.csv"), encoding="utf-8-sig")

    print(f"JSON: {output}")
    print(f"CSV:  {output.with_suffix('.csv')}")
    print(f"Best: {best['variant']}")
    print(
        f"final={best['final_value']:,.0f}, return={best['total_return']:.2%}, "
        f"sharpe={best['sharpe_ratio']:.3f}, mdd={best['max_drawdown']:.2%}, "
        f"switches={best['switch_count']}"
    )
    print(f"Eligible: {len(eligible)} / {len(rows)}")


if __name__ == "__main__":
    main()
