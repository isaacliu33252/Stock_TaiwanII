#!/usr/bin/env python3
"""Shadow backtest for Group A meta ensemble v1.

This does not train or promote a model.  PPO is the released Golden1 model.
A2C and SAC are explicit allocation proxies until matching Group A checkpoints
exist.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_a_tdcc_latest import (
    DEFAULT_CONFIG,
    DEFAULT_DB,
    DEFAULT_RESULT_JSON,
    PROJECT_ROOT,
    TICKERS,
    _load_prices,
    _metrics,
    _resolve,
    _run_base_backtest,
    _simulate_tdcc_overlay,
)
from evaluate_group_a_tdcc_overlay_variants import (
    Variant,
    _apply_hysteresis,
    _overlay_weights,
    _raw_tdcc_state,
)
from train_dual_group_2024_2026 import DEFAULT_INITIAL_CASH


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_meta_ensemble_v1_backtest_202506_20260603.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json", default=str(DEFAULT_RESULT_JSON))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--start", default="2025-06-01")
    parser.add_argument("--end", default="2026-06-03")
    parser.add_argument("--download-end", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--fee-rate", type=float, default=0.001425)
    return parser.parse_args()


def _cash_weight(weights: dict[str, float]) -> float:
    return max(0.0, 1.0 - sum(max(float(v), 0.0) for v in weights.values()))


def _normalize(weights: dict[str, float], cash: float | None = None) -> tuple[dict[str, float], float]:
    cleaned = {ticker: max(0.0, float(weights.get(ticker, 0.0))) for ticker in TICKERS}
    cash_weight = _cash_weight(cleaned) if cash is None else max(0.0, float(cash))
    total = sum(cleaned.values()) + cash_weight
    if total <= 0:
        return {"0050.TW": 0.0, "00631L.TW": 0.0, "00632R.TW": 0.0}, 1.0
    return {ticker: cleaned[ticker] / total for ticker in TICKERS}, cash_weight / total


def _cap_and_scale(
    base: dict[str, float],
    *,
    max_equity: float,
    leverage_cap: float,
    inverse_cap: float = 0.0,
) -> tuple[dict[str, float], float]:
    weights = {ticker: float(base.get(ticker, 0.0)) for ticker in TICKERS}
    weights["00631L.TW"] = min(weights["00631L.TW"], leverage_cap)
    weights["00632R.TW"] = min(weights["00632R.TW"], inverse_cap)
    equity = sum(weights.values())
    if equity > max_equity and equity > 0:
        scale = max_equity / equity
        weights = {ticker: value * scale for ticker, value in weights.items()}
    return _normalize(weights, 1.0 - sum(weights.values()))


def _a2c_proxy(base: dict[str, float], regime: str) -> tuple[dict[str, float], float]:
    if regime == "risk_on":
        return _cap_and_scale(base, max_equity=0.75, leverage_cap=0.10)
    if regime == "risk_off":
        return _cap_and_scale(base, max_equity=0.45, leverage_cap=0.0, inverse_cap=0.03)
    return _cap_and_scale(base, max_equity=0.65, leverage_cap=0.05)


def _sac_proxy(base: dict[str, float], regime: str) -> tuple[dict[str, float], float]:
    weights = {ticker: float(base.get(ticker, 0.0)) for ticker in TICKERS}
    if regime == "risk_on":
        cash = _cash_weight(weights)
        boost = min(0.08, max(0.0, cash - 0.10))
        weights["00631L.TW"] = min(0.28, weights["00631L.TW"] + boost)
        return _normalize(weights, max(0.10, 1.0 - sum(weights.values())))
    if regime == "risk_off":
        return _cap_and_scale(base, max_equity=0.35, leverage_cap=0.0, inverse_cap=0.05)
    weights["00631L.TW"] = min(0.10, weights["00631L.TW"])
    return _cap_and_scale(weights, max_equity=0.70, leverage_cap=0.10)


def _rule_strategy(regime: str) -> tuple[dict[str, float], float]:
    if regime == "risk_on":
        return _normalize({"0050.TW": 0.65, "00631L.TW": 0.10, "00632R.TW": 0.0}, 0.25)
    if regime == "risk_off":
        return _normalize({"0050.TW": 0.45, "00631L.TW": 0.0, "00632R.TW": 0.05}, 0.50)
    return _normalize({"0050.TW": 0.60, "00631L.TW": 0.0, "00632R.TW": 0.0}, 0.40)


def _allocator_weights(regime: str) -> dict[str, float]:
    if regime == "risk_on":
        return {"ppo": 0.50, "a2c_proxy": 0.10, "sac_proxy": 0.30, "rule_based": 0.10}
    if regime == "risk_off":
        return {"ppo": 0.20, "a2c_proxy": 0.25, "sac_proxy": 0.00, "rule_based": 0.55}
    return {"ppo": 0.45, "a2c_proxy": 0.15, "sac_proxy": 0.05, "rule_based": 0.35}


def _price_regimes(prices: pd.DataFrame, tdcc_states: dict[pd.Timestamp, str]) -> dict[pd.Timestamp, str]:
    close = prices["0050.TW"]
    ma60 = close.rolling(60, min_periods=20).mean()
    mom21 = close.pct_change(21)
    regimes: dict[pd.Timestamp, str] = {}
    for dt in prices.index:
        tdcc_state = tdcc_states[dt]
        if tdcc_state == "risk_off":
            regimes[dt] = "risk_off"
        elif pd.notna(ma60.loc[dt]) and pd.notna(mom21.loc[dt]) and close.loc[dt] < ma60.loc[dt] and mom21.loc[dt] < 0:
            regimes[dt] = "risk_off"
        elif tdcc_state == "normal" and pd.notna(ma60.loc[dt]) and pd.notna(mom21.loc[dt]) and close.loc[dt] >= ma60.loc[dt] and mom21.loc[dt] > 0:
            regimes[dt] = "risk_on"
        else:
            regimes[dt] = "neutral"
    return regimes


def _blend_targets(
    ppo_weights: dict[str, float],
    regime: str,
) -> tuple[dict[str, float], float, dict[str, Any]]:
    ppo_weights, ppo_cash = _normalize(ppo_weights, _cash_weight(ppo_weights))
    a2c_weights, a2c_cash = _a2c_proxy(ppo_weights, regime)
    sac_weights, sac_cash = _sac_proxy(ppo_weights, regime)
    rule_weights, rule_cash = _rule_strategy(regime)
    sleeves = {
        "ppo": (ppo_weights, ppo_cash),
        "a2c_proxy": (a2c_weights, a2c_cash),
        "sac_proxy": (sac_weights, sac_cash),
        "rule_based": (rule_weights, rule_cash),
    }
    alloc = _allocator_weights(regime)
    blended = {ticker: 0.0 for ticker in TICKERS}
    cash = 0.0
    for name, sleeve_weight in alloc.items():
        weights, sleeve_cash = sleeves[name]
        for ticker in TICKERS:
            blended[ticker] += sleeve_weight * weights.get(ticker, 0.0)
        cash += sleeve_weight * sleeve_cash
    blended, cash = _normalize(blended, cash)
    diagnostics = {
        "regime": regime,
        "allocator_weights": alloc,
        "sleeves": {
            name: {"weights": weights, "cash": sleeve_cash}
            for name, (weights, sleeve_cash) in sleeves.items()
        },
    }
    return blended, cash, diagnostics


def _simulate_meta_ensemble(
    prices: pd.DataFrame,
    events: list[dict[str, Any]],
    config: dict[str, Any],
    db_path: Path,
    *,
    initial_cash: float,
    fee_rate: float,
    dca_history: list[dict[str, Any]],
) -> dict[str, Any]:
    event_by_date = {
        pd.Timestamp(event["date"]).normalize(): dict(event["target_weights"])
        for event in events
    }
    raw = {dt: _raw_tdcc_state(config, db_path, dt) for dt in prices.index}
    raw_states = [str(raw[dt]["state"]) for dt in prices.index]
    effective_states = _apply_hysteresis(raw_states, Variant("latest_default", risk_off_cap=float(config["risk_off"]["leverage_weight_cap"])))
    tdcc_state_by_date = dict(zip(prices.index, effective_states))
    regime_by_date = _price_regimes(prices, tdcc_state_by_date)
    variant = Variant(
        "latest_default",
        risk_off_cap=float(config["risk_off"]["leverage_weight_cap"]),
        caution_cap=float(config["caution"]["leverage_weight_cap"]),
        destination=str(config.get("released_leverage_budget_destination", "cash")),
        primary_fraction=float(config.get("released_to_primary_fraction", 0.5)),
    )
    dca_by_date = {pd.Timestamp(item["date"]).normalize(): item for item in dca_history}

    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = initial_cash
    fees = 0.0
    contributions = 0.0
    rebalances = 0
    last_base_weights: dict[str, float] | None = None
    last_target_weights: dict[str, float] | None = None
    last_target_cash: float | None = None
    last_tdcc_state: str | None = None
    last_regime: str | None = None
    curve: list[dict[str, Any]] = []
    meta_events: list[dict[str, Any]] = []
    state_counts = {"normal": 0, "caution": 0, "risk_off": 0, "insufficient_data": 0}
    regime_counts = {"risk_on": 0, "neutral": 0, "risk_off": 0}

    for dt, row in prices.iterrows():
        tdcc_state = tdcc_state_by_date[dt]
        regime = regime_by_date[dt]
        state_counts[tdcc_state] = state_counts.get(tdcc_state, 0) + 1
        regime_counts[regime] = regime_counts.get(regime, 0) + 1

        if dt in dca_by_date:
            item = dca_by_date[dt]
            purchase = item.get("purchases", {}).get("0050.TW")
            amount = float(item.get("total_contribution", 0.0))
            if purchase and amount > 0:
                fee = amount * fee_rate / (1.0 + fee_rate)
                buy_value = amount - fee
                shares["0050.TW"] += buy_value / float(row["0050.TW"])
                fees += fee
                contributions += amount
            elif amount > 0:
                cash += amount
                contributions += amount

        total_value = cash + sum(shares[ticker] * float(row[ticker]) for ticker in TICKERS)
        if dt in event_by_date:
            last_base_weights = event_by_date[dt]

        tdcc_changed = last_tdcc_state is not None and tdcc_state != last_tdcc_state
        regime_changed = last_regime is not None and regime != last_regime
        should_rebalance = (dt in event_by_date) or ((tdcc_changed or regime_changed) and last_base_weights is not None)
        if should_rebalance and last_base_weights is not None:
            blended_weights, blended_cash, diagnostics = _blend_targets(last_base_weights, regime)
            target_weights, target_cash = _overlay_weights(
                blended_weights,
                blended_cash,
                tdcc_state,
                variant,
                config,
                raw[dt],
            )
            target_weights, target_cash = _normalize(target_weights, target_cash)
            changed = (
                last_target_weights is None
                or any(abs(target_weights.get(t, 0.0) - last_target_weights.get(t, 0.0)) > 1e-12 for t in TICKERS)
                or abs(target_cash - float(last_target_cash or 0.0)) > 1e-12
            )
            if changed:
                target_values = {ticker: total_value * target_weights.get(ticker, 0.0) for ticker in TICKERS}
                trade_value = sum(abs(target_values[ticker] - shares[ticker] * float(row[ticker])) for ticker in TICKERS)
                fee = trade_value * fee_rate
                total_after_fee = max(total_value - fee, 0.0)
                shares = {
                    ticker: total_after_fee * target_weights.get(ticker, 0.0) / float(row[ticker])
                    for ticker in TICKERS
                }
                cash = total_after_fee * target_cash
                fees += fee
                rebalances += 1
                last_target_weights = dict(target_weights)
                last_target_cash = float(target_cash)
                total_value = cash + sum(shares[ticker] * float(row[ticker]) for ticker in TICKERS)
                meta_events.append(
                    {
                        "date": str(dt.date()),
                        "tdcc_state": tdcc_state,
                        "regime": regime,
                        "base_ppo_weights": last_base_weights,
                        "pre_tdcc_meta_weights": blended_weights,
                        "pre_tdcc_meta_cash_weight": blended_cash,
                        "target_weights": target_weights,
                        "target_cash_weight": target_cash,
                        "fee": float(fee),
                        "diagnostics": diagnostics,
                    }
                )

        last_tdcc_state = tdcc_state
        last_regime = regime
        curve.append({"date": str(dt.date()), "value": float(total_value), "tdcc_state": tdcc_state, "regime": regime})

    values = pd.Series([item["value"] for item in curve], index=pd.to_datetime([item["date"] for item in curve]))
    final_value = float(values.iloc[-1])
    final_weights = {
        ticker: float(shares[ticker] * float(prices.iloc[-1][ticker]) / final_value)
        for ticker in TICKERS
    }
    return {
        "metrics": _metrics(values, initial_cash, contributions, fees, rebalances),
        "tdcc_state_counts": state_counts,
        "regime_counts": regime_counts,
        "events": meta_events,
        "equity_curve": curve,
        "final_shares": shares,
        "final_cash": float(cash),
        "final_weights": final_weights,
        "final_cash_weight": float(cash / max(final_value, 1.0)),
    }


def main() -> None:
    args = _parse_args()
    result_json = _resolve(args.result_json)
    config_path = _resolve(args.config)
    db_path = _resolve(args.db)
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    download_end = args.download_end or args.end
    base, panel, events, _tickers = _run_base_backtest(
        payload,
        result_json,
        start=args.start,
        end=args.end,
        download_end=download_end,
    )
    dates = [pd.Timestamp(value).normalize() for value in panel["date"].tolist()]
    prices = _load_prices(db_path, dates)
    initial_cash = float(payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH))
    latest_tdcc = _simulate_tdcc_overlay(
        prices,
        events,
        config,
        db_path,
        initial_cash=initial_cash,
        fee_rate=float(args.fee_rate),
        dca_history=base["dca_purchase_history"],
    )
    meta = _simulate_meta_ensemble(
        prices,
        events,
        config,
        db_path,
        initial_cash=initial_cash,
        fee_rate=float(args.fee_rate),
        dca_history=base["dca_purchase_history"],
    )
    report = {
        "experiment": "GroupA_meta_ensemble_v1_shadow",
        "method_note": (
            "No retraining and no production promotion. PPO is Golden1_0531. "
            "A2C and SAC are allocation proxies because no Group A A2C/SAC checkpoints were found. "
            "Rule-based sleeve is deterministic risk control. Regime controls sleeve weights, then TDCC caps are applied."
        ),
        "requested_window": {"start": args.start, "end": args.end, "download_end": download_end},
        "actual_window": {"start": base["actual_start"], "end": base["actual_end"], "rows": base["rows"]},
        "models_inventory": {
            "ppo": "Golden1_0531 released PPO model from result payload",
            "a2c": "proxy_only_no_group_a_checkpoint_found",
            "sac": "proxy_only_no_group_a_checkpoint_found",
            "rule_based": "deterministic regime risk-control sleeve",
        },
        "regime_allocator": {
            "risk_on": _allocator_weights("risk_on"),
            "neutral": _allocator_weights("neutral"),
            "risk_off": _allocator_weights("risk_off"),
        },
        "base_strategy": "Golden1_0531",
        "latest_tdcc_strategy": config["strategy_name"],
        "meta_strategy": "GroupA_meta_ensemble_v1_shadow",
        "base_exact_backtest": base,
        "latest_tdcc_overlay_replay": latest_tdcc,
        "meta_ensemble_replay": meta,
        "delta_meta_vs_base_exact": {
            "final_value": meta["metrics"]["final_value"] - base["final_value"],
            "sharpe_ratio": meta["metrics"]["sharpe_ratio"] - base["sharpe_ratio"],
            "max_drawdown": meta["metrics"]["max_drawdown"] - base["max_drawdown"],
            "fees_paid_estimate": meta["metrics"]["fees_paid_estimate"] - base["fees_paid_estimate"],
            "num_trades_or_rebalances": meta["metrics"]["num_rebalances"] - base["num_trades"],
        },
        "delta_meta_vs_latest_tdcc": {
            "final_value": meta["metrics"]["final_value"] - latest_tdcc["metrics"]["final_value"],
            "sharpe_ratio": meta["metrics"]["sharpe_ratio"] - latest_tdcc["metrics"]["sharpe_ratio"],
            "max_drawdown": meta["metrics"]["max_drawdown"] - latest_tdcc["metrics"]["max_drawdown"],
            "fees_paid_estimate": meta["metrics"]["fees_paid_estimate"] - latest_tdcc["metrics"]["fees_paid_estimate"],
            "num_rebalances": meta["metrics"]["num_rebalances"] - latest_tdcc["metrics"]["num_rebalances"],
        },
    }

    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    rows = [
        {"strategy": "Golden1_0531_base_exact", **{k: v for k, v in base.items() if isinstance(v, (int, float, str))}},
        {"strategy": "Golden1_0531_tdcc_v1_latest", **latest_tdcc["metrics"]},
        {"strategy": "GroupA_meta_ensemble_v1_shadow", **meta["metrics"]},
    ]
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Actual window: {base['actual_start']} ~ {base['actual_end']} ({base['rows']} rows)")
    print(
        "Base exact: "
        f"final={base['final_value']:.2f}, sharpe={base['sharpe_ratio']:.4f}, "
        f"mdd={base['max_drawdown']:.4%}, trades={base['num_trades']}, fees={base['fees_paid_estimate']:.2f}"
    )
    latest_metrics = latest_tdcc["metrics"]
    print(
        "Latest TDCC: "
        f"final={latest_metrics['final_value']:.2f}, sharpe={latest_metrics['sharpe_ratio']:.4f}, "
        f"mdd={latest_metrics['max_drawdown']:.4%}, rebalances={latest_metrics['num_rebalances']}, "
        f"fees={latest_metrics['fees_paid_estimate']:.2f}"
    )
    meta_metrics = meta["metrics"]
    print(
        "Meta ensemble v1 shadow: "
        f"final={meta_metrics['final_value']:.2f}, sharpe={meta_metrics['sharpe_ratio']:.4f}, "
        f"mdd={meta_metrics['max_drawdown']:.4%}, rebalances={meta_metrics['num_rebalances']}, "
        f"fees={meta_metrics['fees_paid_estimate']:.2f}"
    )


if __name__ == "__main__":
    try:
        import numpy.core.numeric as _numpy_core_numeric

        sys.modules.setdefault("numpy._core.numeric", _numpy_core_numeric)
    except ImportError:
        pass
    main()
