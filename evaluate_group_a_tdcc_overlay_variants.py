#!/usr/bin/env python3
"""Evaluate Group A TDCC overlay variants on the TDCC-available replay window.

This is an overlay replay harness, not a full PPO retrain/backtest. It starts
from the released Golden1_0531 PVA rebalance history and applies TDCC variants
with historical availability cutoffs.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd

from run_group_a_shareholding_shadow import _load_weekly_features, _ticker_snapshot, assess_shadow_signal


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RESULT_JSON = PROJECT_ROOT / "results" / "group_a_backtest_20250101_20260525_20260526_193252.json"
DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_CONFIG = PROJECT_ROOT / "group_a_tdcc_improved_config.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_tdcc_overlay_variant_sweep_20260603.json"
TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]


@dataclass(frozen=True)
class Variant:
    name: str
    risk_off_cap: float | None = None
    caution_cap: float = 0.10
    destination: str = "cash"
    primary_fraction: float = 0.5
    enter_confirm: int = 1
    exit_confirm: int = 1
    cooldown_days: int = 0
    score_based: bool = False
    inverse_weight: float = 0.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json", default=str(DEFAULT_RESULT_JSON))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--start", default="2025-06-06")
    parser.add_argument("--end", default=None)
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--fee-rate", type=float, default=0.001425)
    return parser.parse_args()


def _load_prices(db_path: Path, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        prices = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN (?, ?, ?) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*TICKERS, start, end],
        ).fetchdf()
    finally:
        con.close()
    if prices.empty:
        raise RuntimeError("No OHLCV rows for replay window")
    pivot = prices.pivot(index="dt", columns="ticker", values="close").sort_index()
    pivot.index = pd.to_datetime(pivot.index)
    return pivot.dropna(subset=TICKERS)


def _load_base_events(result_json: Path, start: str, end: str) -> pd.DataFrame:
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    history = payload["group_a"]["result"]["pva_sigmoid_history"]
    rows = []
    for item in history:
        ts = pd.Timestamp(item["date"]).normalize()
        if pd.Timestamp(start) <= ts <= pd.Timestamp(end):
            weights = {str(k): float(v) for k, v in item["target_weights"].items()}
            rows.append({"date": ts, **weights})
    if not rows:
        raise RuntimeError("No Golden1 PVA events in replay window")
    return pd.DataFrame(rows).drop_duplicates("date", keep="last").set_index("date").sort_index()


def _state_level(state: str) -> int:
    return {"normal": 0, "caution": 1, "risk_off": 2}.get(state, -1)


def _raw_tdcc_state(config: dict[str, object], db_path: Path, as_of: pd.Timestamp) -> dict[str, object]:
    lag_days = int(config["availability_lag_days"])
    cutoff = as_of.date() - timedelta(days=lag_days)
    snapshots = {
        str(ticker): _ticker_snapshot(
            _load_weekly_features(db_path, str(ticker), str(cutoff)),
            int(config["lookback_weeks"]),
        )
        for ticker in config["tickers"]
    }
    assessment = assess_shadow_signal(config, snapshots)
    return {
        **assessment,
        "availability_cutoff_date": str(cutoff),
        "snapshots": snapshots,
    }


def _apply_hysteresis(raw_states: list[str], variant: Variant) -> list[str]:
    effective: list[str] = []
    current = "normal"
    candidate = current
    streak = 0
    cooldown = 0
    for raw in raw_states:
        if raw == "insufficient_data":
            effective.append(current)
            continue
        if cooldown > 0 and _state_level(raw) < _state_level(current):
            cooldown -= 1
            effective.append(current)
            continue
        required = variant.enter_confirm if _state_level(raw) > _state_level(current) else variant.exit_confirm
        if raw == current:
            candidate = raw
            streak = 0
        elif raw == candidate:
            streak += 1
        else:
            candidate = raw
            streak = 1
        if streak >= max(1, required):
            if current != raw and _state_level(raw) > _state_level(current):
                cooldown = variant.cooldown_days
            current = raw
            streak = 0
        effective.append(current)
    return effective


def _score_based_cap(config: dict[str, object], assessment: dict[str, object]) -> float | None:
    leverage = assessment.get("snapshots", {}).get(str(config["leverage_ticker"]), {})
    if not leverage.get("available"):
        return None
    risk_cfg = dict(config["risk_off"])
    minority_ratio = float(leverage["minority_percent_change"]) / float(risk_cfg["leverage_minority_percent_change"])
    people_ratio = float(leverage["total_people_change_ratio"]) / float(risk_cfg["leverage_total_people_change_ratio"])
    score = max(minority_ratio, people_ratio)
    if score >= 1.20:
        return 0.00
    if score >= 1.00:
        return 0.03
    if score >= 0.80:
        return 0.05
    if score >= 0.60:
        return 0.10
    return None


def _overlay_weights(
    base_weights: dict[str, float],
    base_cash: float,
    state: str,
    variant: Variant,
    config: dict[str, object],
    assessment: dict[str, object],
) -> tuple[dict[str, float], float]:
    weights = dict(base_weights)
    cash = float(base_cash)
    leverage = f"{config['leverage_ticker']}.TW"
    primary = f"{config['primary_ticker']}.TW"
    inverse = f"{config['inverse_ticker']}.TW"
    cap = None
    if variant.score_based:
        cap = _score_based_cap(config, assessment)
    if cap is None and state == "risk_off":
        cap = variant.risk_off_cap
    elif cap is None and state == "caution":
        cap = variant.caution_cap
    if cap is not None:
        prior = weights.get(leverage, 0.0)
        weights[leverage] = min(prior, cap)
        released = prior - weights[leverage]
        if variant.destination == "primary":
            weights[primary] = weights.get(primary, 0.0) + released
        elif variant.destination == "split_primary_cash":
            weights[primary] = weights.get(primary, 0.0) + released * variant.primary_fraction
            cash += released * (1.0 - variant.primary_fraction)
        else:
            cash += released
    if state == "risk_off" and variant.inverse_weight > 0.0:
        add = min(variant.inverse_weight, max(cash, 0.0))
        weights[inverse] = weights.get(inverse, 0.0) + add
        cash -= add
    return weights, cash


def _build_variants() -> list[Variant]:
    variants = [Variant("baseline_golden1", risk_off_cap=None)]
    for cap in [0.00, 0.03, 0.05, 0.08]:
        variants.append(Variant(f"riskoff_cap_{cap:.2f}_cash", risk_off_cap=cap))
    variants.extend(
        [
            Variant("riskoff_cap_0_primary", risk_off_cap=0.00, destination="primary"),
            Variant("riskoff_cap_0_split50", risk_off_cap=0.00, destination="split_primary_cash", primary_fraction=0.50),
            Variant("riskoff_cap_0_hysteresis_2x2", risk_off_cap=0.00, enter_confirm=2, exit_confirm=2),
            Variant("riskoff_cap_0_cooldown_10d", risk_off_cap=0.00, cooldown_days=10),
            Variant("score_based_cap_cash", score_based=True),
            Variant("riskoff_cap_0_inverse5", risk_off_cap=0.00, inverse_weight=0.05),
        ]
    )
    return variants


def _simulate(
    prices: pd.DataFrame,
    events: pd.DataFrame,
    states: dict[pd.Timestamp, dict[str, object]],
    variant: Variant,
    config: dict[str, object],
    *,
    initial_value: float,
    fee_rate: float,
) -> dict[str, object]:
    raw_states = [str(states[dt]["state"]) for dt in prices.index]
    eff_states = _apply_hysteresis(raw_states, variant)
    eff_state_by_date = dict(zip(prices.index, eff_states))
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = initial_value
    curve = []
    rebalances = 0
    fees = 0.0
    state_counts = {"normal": 0, "caution": 0, "risk_off": 0}
    target_weight_history = []
    last_base_weights: dict[str, float] | None = None
    last_target_weights: dict[str, float] | None = None
    last_target_cash: float | None = None
    last_state: str | None = None
    for dt, price_row in prices.iterrows():
        total_value = cash + sum(shares[t] * float(price_row[t]) for t in TICKERS)
        state = eff_state_by_date[dt]
        if state in state_counts:
            state_counts[state] += 1
        has_base_event = dt in events.index
        if has_base_event:
            last_base_weights = {t: float(events.loc[dt, t]) for t in TICKERS}
        state_changed = last_state is not None and state != last_state
        should_rebalance = has_base_event or (state_changed and last_base_weights is not None)
        if should_rebalance and last_base_weights is not None:
            base_weights = dict(last_base_weights)
            base_cash = max(0.0, 1.0 - sum(base_weights.values()))
            if variant.name == "baseline_golden1":
                target_weights, target_cash = base_weights, base_cash
            else:
                target_weights, target_cash = _overlay_weights(
                    base_weights,
                    base_cash,
                    state,
                    variant,
                    config,
                    states[dt],
                )
            changed_target = (
                last_target_weights is None
                or any(abs(target_weights.get(t, 0.0) - last_target_weights.get(t, 0.0)) > 1e-12 for t in TICKERS)
                or abs(target_cash - float(last_target_cash or 0.0)) > 1e-12
            )
            if not changed_target:
                last_state = state
                curve.append({"date": str(dt.date()), "value": float(total_value), "state": state})
                continue
            target_values = {t: total_value * target_weights.get(t, 0.0) for t in TICKERS}
            trade_value = sum(abs(target_values[t] - shares[t] * float(price_row[t])) for t in TICKERS)
            fee = trade_value * fee_rate
            total_after_fee = max(total_value - fee, 0.0)
            shares = {
                t: (total_after_fee * target_weights.get(t, 0.0) / float(price_row[t]))
                for t in TICKERS
            }
            cash = total_after_fee * target_cash
            total_value = cash + sum(shares[t] * float(price_row[t]) for t in TICKERS)
            fees += fee
            rebalances += 1
            last_target_weights = dict(target_weights)
            last_target_cash = float(target_cash)
            target_weight_history.append({"date": str(dt.date()), "state": state, **target_weights, "cash": target_cash})
        last_state = state
        curve.append({"date": str(dt.date()), "value": float(total_value), "state": state})
    values = pd.Series([row["value"] for row in curve], index=pd.to_datetime([row["date"] for row in curve]))
    returns = values.pct_change().dropna()
    total_return = float(values.iloc[-1] / values.iloc[0] - 1.0)
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1e-9)
    annual_return = float((values.iloc[-1] / values.iloc[0]) ** (1.0 / years) - 1.0)
    volatility = float(returns.std() * math.sqrt(252)) if not returns.empty else 0.0
    sharpe = float((returns.mean() / returns.std()) * math.sqrt(252)) if len(returns) > 1 and returns.std() > 0 else 0.0
    drawdown = values / values.cummax() - 1.0
    max_drawdown = float(drawdown.min())
    return {
        "variant": variant.__dict__,
        "metrics": {
            "start_date": str(values.index[0].date()),
            "end_date": str(values.index[-1].date()),
            "final_value": float(values.iloc[-1]),
            "total_return": total_return,
            "annual_return": annual_return,
            "volatility": volatility,
            "sharpe": sharpe,
            "max_drawdown": max_drawdown,
            "rebalances": rebalances,
            "fees": float(fees),
            "state_counts": state_counts,
        },
        "last_targets": target_weight_history[-5:],
    }


def main() -> None:
    args = _parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    end = args.end
    if end is None:
        payload = json.loads(Path(args.result_json).read_text(encoding="utf-8"))
        end = payload["group_a"]["result"]["backtest_end"]
    prices = _load_prices(Path(args.db), args.start, end)
    events = _load_base_events(Path(args.result_json), str(prices.index[0].date()), str(prices.index[-1].date()))
    states = {
        dt: _raw_tdcc_state(config, Path(args.db), dt)
        for dt in prices.index
    }
    results = [
        _simulate(
            prices,
            events,
            states,
            variant,
            config,
            initial_value=float(args.initial_value),
            fee_rate=float(args.fee_rate),
        )
        for variant in _build_variants()
    ]
    baseline = next(item for item in results if item["variant"]["name"] == "baseline_golden1")
    for item in results:
        metrics = item["metrics"]
        base_metrics = baseline["metrics"]
        item["delta_vs_baseline"] = {
            "final_value": metrics["final_value"] - base_metrics["final_value"],
            "total_return": metrics["total_return"] - base_metrics["total_return"],
            "sharpe": metrics["sharpe"] - base_metrics["sharpe"],
            "max_drawdown": metrics["max_drawdown"] - base_metrics["max_drawdown"],
            "fees": metrics["fees"] - base_metrics["fees"],
        }
    ranked = sorted(
        results,
        key=lambda item: (
            item["metrics"]["max_drawdown"] >= baseline["metrics"]["max_drawdown"],
            item["metrics"]["final_value"],
            item["metrics"]["sharpe"],
        ),
        reverse=True,
    )
    report = {
        "experiment": "group_a_tdcc_overlay_variant_sweep",
        "scope_note": (
            "Overlay replay on TDCC-available dates only. Uses Golden1_0531 PVA rebalance "
            "events and historical TDCC availability cutoffs; it is not a full PPO retrain."
        ),
        "inputs": {
            "result_json": str(Path(args.result_json).resolve()),
            "db": str(Path(args.db).resolve()),
            "config": str(Path(args.config).resolve()),
            "start": str(prices.index[0].date()),
            "end": str(prices.index[-1].date()),
            "price_rows": int(len(prices)),
            "base_rebalance_events": int(len(events)),
            "fee_rate": float(args.fee_rate),
        },
        "baseline": baseline,
        "ranked_variant_names": [item["variant"]["name"] for item in ranked],
        "results": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = []
    for item in results:
        rows.append({"variant": item["variant"]["name"], **item["metrics"], **{f"delta_{k}": v for k, v in item["delta_vs_baseline"].items()}})
    csv_path = output.with_suffix(".csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print("Top variants:")
    for name in report["ranked_variant_names"][:5]:
        item = next(result for result in results if result["variant"]["name"] == name)
        print(
            f"  {name}: final={item['metrics']['final_value']:.0f}, "
            f"ret={item['metrics']['total_return']:.3%}, "
            f"sharpe={item['metrics']['sharpe']:.3f}, "
            f"mdd={item['metrics']['max_drawdown']:.3%}"
        )


if __name__ == "__main__":
    main()
