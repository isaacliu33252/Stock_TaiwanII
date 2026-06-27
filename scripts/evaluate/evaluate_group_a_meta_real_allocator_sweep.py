#!/usr/bin/env python3
"""Sweep regime allocator weights for the real Group A meta ensemble."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_a_meta_ensemble import _normalize, _price_regimes, _rule_strategy
from backtest_group_a_tdcc_latest import DEFAULT_CONFIG, DEFAULT_DB, PROJECT_ROOT, TICKERS, _load_prices, _metrics, _resolve
from evaluate_group_a_tdcc_overlay_variants import Variant, _apply_hysteresis, _overlay_weights, _raw_tdcc_state


DEFAULT_SOURCE = PROJECT_ROOT / "results" / "group_a_meta_ensemble_real_backtest_20250601_20260603.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_meta_real_allocator_sweep_20260603.json"


VARIANTS: dict[str, dict[str, dict[str, float]]] = {
    "current_defensive": {
        "risk_on": {"ppo": 0.50, "a2c": 0.10, "sac": 0.30, "rule_based": 0.10},
        "neutral": {"ppo": 0.45, "a2c": 0.15, "sac": 0.05, "rule_based": 0.35},
        "risk_off": {"ppo": 0.20, "a2c": 0.25, "sac": 0.00, "rule_based": 0.55},
    },
    "balanced_less_cash": {
        "risk_on": {"ppo": 0.55, "a2c": 0.05, "sac": 0.35, "rule_based": 0.05},
        "neutral": {"ppo": 0.55, "a2c": 0.15, "sac": 0.10, "rule_based": 0.20},
        "risk_off": {"ppo": 0.35, "a2c": 0.25, "sac": 0.00, "rule_based": 0.40},
    },
    "ppo_core": {
        "risk_on": {"ppo": 0.65, "a2c": 0.05, "sac": 0.25, "rule_based": 0.05},
        "neutral": {"ppo": 0.70, "a2c": 0.10, "sac": 0.05, "rule_based": 0.15},
        "risk_off": {"ppo": 0.45, "a2c": 0.25, "sac": 0.00, "rule_based": 0.30},
    },
    "tdcc_overlay_only_like": {
        "risk_on": {"ppo": 0.80, "a2c": 0.00, "sac": 0.15, "rule_based": 0.05},
        "neutral": {"ppo": 0.80, "a2c": 0.05, "sac": 0.00, "rule_based": 0.15},
        "risk_off": {"ppo": 0.70, "a2c": 0.10, "sac": 0.00, "rule_based": 0.20},
    },
    "ppo_dominant_tdcc_cap": {
        "risk_on": {"ppo": 0.85, "a2c": 0.00, "sac": 0.10, "rule_based": 0.05},
        "neutral": {"ppo": 0.90, "a2c": 0.00, "sac": 0.00, "rule_based": 0.10},
        "risk_off": {"ppo": 0.85, "a2c": 0.00, "sac": 0.00, "rule_based": 0.15},
    },
    "ppo_a2c_guard": {
        "risk_on": {"ppo": 0.80, "a2c": 0.05, "sac": 0.10, "rule_based": 0.05},
        "neutral": {"ppo": 0.80, "a2c": 0.10, "sac": 0.00, "rule_based": 0.10},
        "risk_off": {"ppo": 0.75, "a2c": 0.15, "sac": 0.00, "rule_based": 0.10},
    },
    "sac_risk_on_only": {
        "risk_on": {"ppo": 0.45, "a2c": 0.05, "sac": 0.45, "rule_based": 0.05},
        "neutral": {"ppo": 0.65, "a2c": 0.15, "sac": 0.00, "rule_based": 0.20},
        "risk_off": {"ppo": 0.45, "a2c": 0.25, "sac": 0.00, "rule_based": 0.30},
    },
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--fee-rate", type=float, default=0.001425)
    return parser.parse_args()


def _event_map(events: list[dict[str, Any]]) -> dict[pd.Timestamp, dict[str, float]]:
    return {pd.Timestamp(event["date"]).normalize(): dict(event["target_weights"]) for event in events}


def _blend(
    ppo: dict[str, float],
    a2c: dict[str, float],
    sac: dict[str, float],
    regime: str,
    allocators: dict[str, dict[str, float]],
) -> tuple[dict[str, float], float]:
    rule, rule_cash = _rule_strategy(regime)
    ppo, ppo_cash = _normalize(ppo, max(0.0, 1.0 - sum(ppo.values())))
    a2c, a2c_cash = _normalize(a2c, max(0.0, 1.0 - sum(a2c.values())))
    sac, sac_cash = _normalize(sac, max(0.0, 1.0 - sum(sac.values())))
    sleeves = {
        "ppo": (ppo, ppo_cash),
        "a2c": (a2c, a2c_cash),
        "sac": (sac, sac_cash),
        "rule_based": (rule, rule_cash),
    }
    alloc = allocators[regime]
    total_alloc = sum(max(v, 0.0) for v in alloc.values())
    if total_alloc <= 0:
        alloc = {"ppo": 1.0, "a2c": 0.0, "sac": 0.0, "rule_based": 0.0}
        total_alloc = 1.0
    weights = {ticker: 0.0 for ticker in TICKERS}
    cash = 0.0
    for name, raw_weight in alloc.items():
        sleeve_weight = max(float(raw_weight), 0.0) / total_alloc
        sleeve_weights, sleeve_cash = sleeves[name]
        for ticker in TICKERS:
            weights[ticker] += sleeve_weight * sleeve_weights.get(ticker, 0.0)
        cash += sleeve_weight * sleeve_cash
    return _normalize(weights, cash)


def _simulate(
    prices: pd.DataFrame,
    source: dict[str, Any],
    config: dict[str, Any],
    db_path: Path,
    allocators: dict[str, dict[str, float]],
    fee_rate: float,
) -> dict[str, Any]:
    base = source["base_exact_backtest"]
    ppo_by_date = _event_map(base["rebalance_events"])
    a2c_by_date = _event_map(source["a2c_shadow_backtest"]["rebalance_events"])
    sac_by_date = _event_map(source["sac_shadow_backtest"]["rebalance_events"])
    raw = {dt: _raw_tdcc_state(config, db_path, dt) for dt in prices.index}
    raw_states = [str(raw[dt]["state"]) for dt in prices.index]
    effective_states = _apply_hysteresis(raw_states, Variant("latest_default", risk_off_cap=float(config["risk_off"]["leverage_weight_cap"])))
    tdcc_by_date = dict(zip(prices.index, effective_states))
    regime_by_date = _price_regimes(prices, tdcc_by_date)
    variant = Variant(
        "latest_default",
        risk_off_cap=float(config["risk_off"]["leverage_weight_cap"]),
        caution_cap=float(config["caution"]["leverage_weight_cap"]),
        destination=str(config.get("released_leverage_budget_destination", "cash")),
        primary_fraction=float(config.get("released_to_primary_fraction", 0.5)),
    )
    dca_by_date = {pd.Timestamp(item["date"]).normalize(): item for item in base["dca_purchase_history"]}
    initial_cash = float(base["total_invested_capital"] - base["dca_total_contributions"])
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = initial_cash
    fees = 0.0
    contributions = 0.0
    rebalances = 0
    last_ppo = last_a2c = last_sac = None
    last_target = None
    last_cash = None
    last_state = None
    last_regime = None
    curve = []
    events = []
    for dt, row in prices.iterrows():
        state = tdcc_by_date[dt]
        regime = regime_by_date[dt]
        if dt in dca_by_date:
            item = dca_by_date[dt]
            amount = float(item.get("total_contribution", 0.0))
            purchase = item.get("purchases", {}).get("0050.TW")
            if purchase and amount > 0:
                fee = amount * fee_rate / (1.0 + fee_rate)
                shares["0050.TW"] += (amount - fee) / float(row["0050.TW"])
                fees += fee
                contributions += amount
            elif amount > 0:
                cash += amount
                contributions += amount
        total_value = cash + sum(shares[ticker] * float(row[ticker]) for ticker in TICKERS)
        updated = False
        if dt in ppo_by_date:
            last_ppo = ppo_by_date[dt]
            updated = True
        if dt in a2c_by_date:
            last_a2c = a2c_by_date[dt]
            updated = True
        if dt in sac_by_date:
            last_sac = sac_by_date[dt]
            updated = True
        changed_state = last_state is not None and state != last_state
        changed_regime = last_regime is not None and regime != last_regime
        if (updated or changed_state or changed_regime) and last_ppo is not None:
            blended, blended_cash = _blend(last_ppo, last_a2c or last_ppo, last_sac or last_ppo, regime, allocators)
            target, target_cash = _overlay_weights(blended, blended_cash, state, variant, config, raw[dt])
            target, target_cash = _normalize(target, target_cash)
            changed = (
                last_target is None
                or any(abs(target.get(t, 0.0) - last_target.get(t, 0.0)) > 1e-12 for t in TICKERS)
                or abs(target_cash - float(last_cash or 0.0)) > 1e-12
            )
            if changed:
                target_values = {ticker: total_value * target.get(ticker, 0.0) for ticker in TICKERS}
                trade_value = sum(abs(target_values[ticker] - shares[ticker] * float(row[ticker])) for ticker in TICKERS)
                fee = trade_value * fee_rate
                after_fee = max(total_value - fee, 0.0)
                shares = {ticker: after_fee * target.get(ticker, 0.0) / float(row[ticker]) for ticker in TICKERS}
                cash = after_fee * target_cash
                fees += fee
                rebalances += 1
                last_target = dict(target)
                last_cash = target_cash
                total_value = cash + sum(shares[ticker] * float(row[ticker]) for ticker in TICKERS)
                events.append({"date": str(dt.date()), "tdcc_state": state, "regime": regime, "target_weights": target, "target_cash_weight": target_cash, "fee": fee})
        last_state = state
        last_regime = regime
        curve.append({"date": str(dt.date()), "value": float(total_value), "tdcc_state": state, "regime": regime})
    values = pd.Series([item["value"] for item in curve], index=pd.to_datetime([item["date"] for item in curve]))
    final_value = float(values.iloc[-1])
    return {
        "metrics": _metrics(values, initial_cash, contributions, fees, rebalances),
        "events": events,
        "equity_curve": curve,
        "final_shares": shares,
        "final_cash": cash,
        "final_weights": {ticker: float(shares[ticker] * float(prices.iloc[-1][ticker]) / final_value) for ticker in TICKERS},
        "final_cash_weight": float(cash / max(final_value, 1.0)),
    }


def main() -> None:
    args = _parse_args()
    source_path = _resolve(args.source)
    config_path = _resolve(args.config)
    db_path = _resolve(args.db)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    dates = [pd.Timestamp(item["date"]).normalize() for item in source["latest_tdcc_overlay_replay"]["equity_curve"]]
    prices = _load_prices(db_path, dates)
    results = []
    details = {}
    base = source["base_exact_backtest"]
    latest = source["latest_tdcc_overlay_replay"]["metrics"]
    for name, allocators in VARIANTS.items():
        replay = _simulate(prices, source, config, db_path, allocators, float(args.fee_rate))
        metrics = replay["metrics"]
        row = {
            "variant": name,
            **metrics,
            "delta_final_vs_base": metrics["final_value"] - base["final_value"],
            "delta_sharpe_vs_base": metrics["sharpe_ratio"] - base["sharpe_ratio"],
            "delta_mdd_vs_base": metrics["max_drawdown"] - base["max_drawdown"],
            "delta_final_vs_tdcc": metrics["final_value"] - latest["final_value"],
            "delta_sharpe_vs_tdcc": metrics["sharpe_ratio"] - latest["sharpe_ratio"],
            "delta_mdd_vs_tdcc": metrics["max_drawdown"] - latest["max_drawdown"],
            "final_cash_weight": replay["final_cash_weight"],
            **{f"final_{ticker}": replay["final_weights"][ticker] for ticker in TICKERS},
        }
        results.append(row)
        details[name] = {"allocators": allocators, "replay": replay}
    results = sorted(results, key=lambda row: (row["final_value"], row["sharpe_ratio"]), reverse=True)
    report = {
        "experiment": "GroupA_meta_real_allocator_sweep",
        "source": str(source_path.resolve()),
        "actual_window": source["actual_window"],
        "base_final_value": base["final_value"],
        "tdcc_final_value": latest["final_value"],
        "variants": results,
        "details": details,
    }
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    pd.DataFrame(results).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    for row in results:
        print(
            f"{row['variant']}: final={row['final_value']:.2f}, sharpe={row['sharpe_ratio']:.4f}, "
            f"mdd={row['max_drawdown']:.4%}, rebalances={row['num_rebalances']}, cash={row['final_cash_weight']:.2%}"
        )


if __name__ == "__main__":
    main()
