#!/usr/bin/env python3
"""Evaluate an A20.8 candidate with coverage-normalized entry risk."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
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
RISK_SOURCE_QUERIES = {
    "chip_inst_risk": ("institutional_data", "ticker = '0050.TW'", 5, 5),
    "chip_foreign_risk": ("institutional_data", "ticker = '0050.TW'", 5, 5),
    "chip_margin_risk": ("margin_data", "ticker = '0050.TW'", 5, 5),
    "chip_market_margin_risk": ("market_margin_data", "1 = 1", 5, 5),
    "chip_tdcc_risk": ("shareholding_distribution", "stock_id = '0050'", 10, 2),
    "chip_foreign_shareholding_risk": ("foreign_shareholding_data", "ticker = '0050.TW'", 5, 5),
    "chip_short_balance_risk": ("short_sale_balance_data", "ticker = '0050.TW'", 5, 5),
    "chip_securities_lending_risk": ("securities_lending_data", "ticker = '0050.TW'", 5, 5),
    "chip_day_trading_risk": ("day_trading_data", "ticker = '0050.TW'", 5, 5),
    "chip_dealer_tx_risk": ("dealer_futures_data", "futures_id = 'TX' AND is_after_hour = 0", 5, 5),
    "chip_dealer_txo_risk": ("dealer_options_data", "option_id = 'TXO' AND is_after_hour = 0", 5, 5),
    "derivative_futures_foreign_risk": (
        "derivative_institutional_data",
        "market = 'futures' AND product_id = 'TX' AND institutional_investors = '外資'",
        5,
        5,
    ),
    "derivative_options_foreign_risk": (
        "derivative_institutional_data",
        "market = 'options' AND product_id = 'TXO' AND institutional_investors = '外資'",
        5,
        5,
    ),
}


def _parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def _parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _availability_from_dates(
    index: pd.DatetimeIndex,
    observation_dates: pd.Series | list[Any],
    max_stale_trading_days: int,
    min_observations: int,
) -> pd.Series:
    observed = pd.Series(False, index=index, dtype=bool)
    dates = pd.DatetimeIndex(pd.to_datetime(observation_dates, errors="coerce")).dropna().normalize()
    observed.loc[observed.index.normalize().isin(dates)] = True
    recent = observed.rolling(max_stale_trading_days + 1, min_periods=1).max().astype(bool)
    mature = observed.astype(int).cumsum() >= min_observations
    return (recent & mature).astype(int)


def _load_risk_availability(db_path: Path, index: pd.DatetimeIndex) -> pd.DataFrame:
    availability = pd.DataFrame(index=index)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {
            row[0]
            for row in con.execute("SELECT table_name FROM information_schema.tables").fetchall()
        }
        for risk_column, (table, where, stale_days, min_obs) in RISK_SOURCE_QUERIES.items():
            if table not in tables:
                availability[risk_column] = 0
                continue
            rows = con.execute(
                f"SELECT DISTINCT dt FROM {table} WHERE {where} AND dt BETWEEN ? AND ? ORDER BY dt",
                [str(index[0].date()), str(index[-1].date())],
            ).fetchdf()
            availability[risk_column] = _availability_from_dates(
                index,
                rows["dt"] if not rows.empty else [],
                stale_days,
                min_obs,
            )
    finally:
        con.close()
    availability["smart_money_cost_risk"] = (
        availability["chip_inst_risk"].astype(bool) & availability["chip_margin_risk"].astype(bool)
    ).astype(int)
    return availability


def _coverage_normalized_regime(
    features: pd.DataFrame,
    availability: pd.DataFrame,
    risk_ratio_threshold: float,
    min_available_features: int,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    risk_columns = list(availability.columns)
    available_count = availability.sum(axis=1).astype(int)
    available_risk_count = (features[risk_columns].astype(int) * availability).sum(axis=1).astype(int)
    risk_ratio = available_risk_count.div(available_count.where(available_count > 0)).astype(float)

    in_defense = False
    hold_days = 0
    regimes: list[str] = []
    events: list[dict[str, Any]] = []
    entry_mode: list[str] = []
    for dt, row in features.iterrows():
        enough_coverage = int(available_count.loc[dt]) >= min_available_features
        normalized_risk_ok = bool(risk_ratio.loc[dt] >= risk_ratio_threshold) if pd.notna(risk_ratio.loc[dt]) else False
        fallback_risk_ok = int(row["total_risk_score"]) >= A207_RULE.require_total_risk_score
        risk_ok = normalized_risk_ok if enough_coverage else fallback_risk_ok
        mode = "normalized" if enough_coverage else "a207_fallback"
        price_enter = row["ma_gap"] <= A207_RULE.enter_ma_gap or row["drawdown"] <= A207_RULE.enter_drawdown
        enter = bool(price_enter and risk_ok)
        exit_ = bool(
            row["ma_gap"] >= A207_RULE.exit_ma_gap
            and row["exit_momentum"] > 0.0
            and int(row["total_risk_score"]) <= int(A207_RULE.exit_max_total_risk_score or 999)
        )

        action = None
        if in_defense:
            hold_days += 1
            if hold_days >= A207_RULE.min_hold_days and exit_:
                in_defense = False
                hold_days = 0
                action = "switch_to_golden"
        elif enter:
            in_defense = True
            hold_days = 1
            action = "switch_to_group_a_plus_defensive"
        if action:
            events.append(
                {
                    "date": str(dt.date()),
                    "action": action,
                    "entry_mode": mode,
                    "available_features": int(available_count.loc[dt]),
                    "available_risk_count": int(available_risk_count.loc[dt]),
                    "coverage_risk_ratio": float(risk_ratio.loc[dt]) if pd.notna(risk_ratio.loc[dt]) else None,
                    "raw_total_risk_score": int(row["total_risk_score"]),
                    "ma_gap": float(row["ma_gap"]),
                    "drawdown": float(row["drawdown"]),
                }
            )
        regimes.append("group_a_plus_defensive" if in_defense else "golden1")
        entry_mode.append(mode)

    frame = features.copy()
    frame["available_risk_features"] = available_count
    frame["available_risk_count"] = available_risk_count
    frame["coverage_risk_ratio"] = risk_ratio.astype(float)
    frame["coverage_entry_mode"] = entry_mode
    frame["regime"] = regimes
    return frame, events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--risk-ratios", default="0.35,0.40,0.45")
    parser.add_argument("--min-available-features", default="4,6,8")
    parser.add_argument("--output-prefix", default="results/group_a_plus_coverage_normalized_20260620")
    args = parser.parse_args()

    policy_signal, policy_signal_path = _load_policy_signal(_resolve(args.decision_pointer))
    golden_signal_path = _resolve(args.golden_signal)
    golden_signal = _load(golden_signal_path)
    defensive_weights = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)
    weights_by_regime = {"golden1": golden_weights, "group_a_plus_defensive": defensive_weights}

    prices = _load_prices(_resolve(args.db), list(TICKERS), args.start, args.end)
    chip_features = _load_chip_features(_resolve(args.db), prices.index, args.start, args.end)
    _base_events, a207_frame = _switch_returns(prices, chip_features, A207_RULE)
    baseline_curve = _simulate_regime_curve(prices, a207_frame["regime"], weights_by_regime, args.initial_value)
    baseline_metrics = _metrics(baseline_curve, args.initial_value)
    availability = _load_risk_availability(_resolve(args.db), prices.index)

    rows: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    events_by_variant: dict[str, list[dict[str, Any]]] = {}
    for ratio in _parse_float_list(args.risk_ratios):
        for min_features in _parse_int_list(args.min_available_features):
            variant = f"a208_covrisk_r{int(ratio * 100):02d}_m{min_features}"
            frame, events = _coverage_normalized_regime(a207_frame, availability, ratio, min_features)
            curve = _simulate_regime_curve(prices, frame["regime"], weights_by_regime, args.initial_value)
            metrics = _metrics(curve, args.initial_value)
            override_days = int((frame["regime"] != a207_frame["regime"]).sum())
            rows.append(
                {
                    "variant": variant,
                    **metrics,
                    "risk_ratio_threshold": ratio,
                    "min_available_features": min_features,
                    "effective_override_days": override_days,
                    "override_days": override_days,
                    "event_count": len(events),
                    "normalized_days": int((frame["coverage_entry_mode"] == "normalized").sum()),
                    "fallback_days": int((frame["coverage_entry_mode"] == "a207_fallback").sum()),
                    "available_features_min": int(frame["available_risk_features"].min()),
                    "available_features_median": float(frame["available_risk_features"].median()),
                    "available_features_max": int(frame["available_risk_features"].max()),
                }
            )
            frame["portfolio_value"] = curve
            frames[variant] = frame
            events_by_variant[variant] = events

    formal = [
        row for row in rows
        if row["final_value"] >= baseline_metrics["final_value"]
        and row["sharpe_ratio"] >= baseline_metrics["sharpe_ratio"]
        and row["max_drawdown"] >= baseline_metrics["max_drawdown"]
        and row["override_days"] > 0
    ]
    effective = [row for row in rows if row["override_days"] > 0]
    ranked = sorted(
        effective or rows,
        key=lambda row: (row in formal, row["sharpe_ratio"], row["max_drawdown"], row["final_value"]),
        reverse=True,
    )
    best = ranked[0]
    report = {
        "experiment": "group_a_plus_a208_coverage_normalized_risk",
        "method_note": (
            "Only A20.7 entry risk confirmation is normalized by observable feature coverage. "
            "Price entry, minimum hold, exit, weights, and fallback raw-risk behavior remain A20.7."
        ),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "actual_window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": len(prices)},
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
        "top_formal": formal[:10],
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
