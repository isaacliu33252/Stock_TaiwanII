#!/usr/bin/env python3
"""Sweep Group A TDCC improvements without PPO retraining."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import pandas as pd
import duckdb

import backtest_group_a_tdcc_latest as latest_module
from backtest_group_a_tdcc_latest import (
    DEFAULT_DB,
    DEFAULT_INITIAL_CASH,
    DEFAULT_RESULT_JSON,
    _load_prices,
    _run_base_backtest,
    _simulate_tdcc_overlay,
)
from evaluate_group_a_tdcc_overlay_variants import _apply_hysteresis, _raw_tdcc_state, Variant
from run_group_a_shareholding_shadow import _ticker_snapshot, assess_shadow_signal


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = PROJECT_ROOT / "group_a_tdcc_improved_config.json"
DEFAULT_SOURCE_BACKTEST = PROJECT_ROOT / "results" / "group_a_tdcc_latest_backtest_20240101_20260605.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_tdcc_improvement_sweep_20240102_20260604.json"
TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]
_TDCC_STATE_CACHE: dict[tuple[str, str], dict[str, Any]] = {}
_TDCC_FEATURE_CACHE: dict[tuple[str, tuple[str, ...]], dict[str, pd.DataFrame]] = {}


def _config_cache_key(config: dict[str, Any]) -> str:
    relevant = {
        "tickers": config.get("tickers"),
        "lookback_weeks": config.get("lookback_weeks"),
        "availability_lag_days": config.get("availability_lag_days"),
        "caution": config.get("caution"),
        "risk_off": config.get("risk_off"),
        "primary_ticker": config.get("primary_ticker"),
        "leverage_ticker": config.get("leverage_ticker"),
        "inverse_ticker": config.get("inverse_ticker"),
    }
    return json.dumps(relevant, sort_keys=True, ensure_ascii=True)


def _cached_raw_tdcc_state(config: dict[str, Any], db_path: Path, as_of: pd.Timestamp) -> dict[str, Any]:
    key = (_config_cache_key(config), str(pd.Timestamp(as_of).date()))
    if key not in _TDCC_STATE_CACHE:
        lag_days = int(config["availability_lag_days"])
        cutoff = pd.Timestamp(as_of).date() - pd.Timedelta(days=lag_days)
        features_by_ticker = _preload_tdcc_features(db_path, [str(ticker) for ticker in config["tickers"]])
        snapshots = {}
        for ticker in config["tickers"]:
            features = features_by_ticker.get(str(ticker), pd.DataFrame())
            if not features.empty:
                features = features.loc[pd.to_datetime(features["dt"]).dt.date <= cutoff]
            snapshots[str(ticker)] = _ticker_snapshot(features, int(config["lookback_weeks"]))
        assessment = assess_shadow_signal(config, snapshots)
        _TDCC_STATE_CACHE[key] = {
            **assessment,
            "availability_cutoff_date": str(cutoff),
            "snapshots": snapshots,
        }
    return _TDCC_STATE_CACHE[key]


def _preload_tdcc_features(db_path: Path, tickers: list[str]) -> dict[str, pd.DataFrame]:
    cache_key = (str(db_path.resolve()), tuple(sorted(tickers)))
    if cache_key in _TDCC_FEATURE_CACHE:
        return _TDCC_FEATURE_CACHE[cache_key]
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tiers = con.execute(
            """
            SELECT stock_id, dt, holding_level, people, percent
            FROM shareholding_distribution
            WHERE stock_id IN (SELECT * FROM UNNEST(?))
            ORDER BY stock_id, dt, holding_level
            """,
            [tickers],
        ).fetchdf()
    finally:
        con.close()
    if tiers.empty:
        _TDCC_FEATURE_CACHE[cache_key] = {}
        return {}
    tiers["minority_percent"] = tiers["percent"].where(tiers["holding_level"].between(1, 5), 0.0)
    tiers["major_percent"] = tiers["percent"].where(tiers["holding_level"].between(12, 15), 0.0)
    grouped = (
        tiers.groupby(["stock_id", "dt"], as_index=False)[["minority_percent", "major_percent"]]
        .sum()
    )
    total_people = (
        tiers.loc[tiers["holding_level"] == 17, ["stock_id", "dt", "people"]]
        .drop_duplicates(subset=["stock_id", "dt"], keep="last")
        .rename(columns={"people": "total_people"})
    )
    features = (
        grouped.merge(total_people, on=["stock_id", "dt"], how="left")
        .sort_values(["stock_id", "dt"])
        .reset_index(drop=True)
    )
    result = {ticker: frame.drop(columns=["stock_id"]).reset_index(drop=True) for ticker, frame in features.groupby("stock_id")}
    _TDCC_FEATURE_CACHE[cache_key] = result
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json", default=str(DEFAULT_RESULT_JSON))
    parser.add_argument("--source-backtest", default=str(DEFAULT_SOURCE_BACKTEST))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-06-05")
    parser.add_argument("--download-end", default="2026-06-05")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--fee-rate", type=float, default=0.001425)
    return parser.parse_args()


def _load_base_from_source(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[pd.Timestamp], float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    base = payload["base_exact_backtest"]
    events = list(base["rebalance_events"])
    curve_rows = payload["latest_tdcc_overlay_replay"]["equity_curve"]
    dates = [pd.Timestamp(row["date"]).normalize() for row in curve_rows]
    initial_cash = float(base.get("total_invested_capital", 1_145_000.0) - base.get("dca_total_contributions", 145_000.0))
    return base, events, dates, initial_cash


def _resolve(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _metric_row(name: str, result: dict[str, Any]) -> dict[str, Any]:
    metrics = result["metrics"]
    return {
        "variant": name,
        "final_value": float(metrics["final_value"]),
        "annual_return": float(metrics["annual_return"]),
        "sharpe_ratio": float(metrics["sharpe_ratio"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "volatility": float(metrics["volatility"]),
        "num_rebalances": int(metrics["num_rebalances"]),
        "fees_paid_estimate": float(metrics["fees_paid_estimate"]),
        "state_counts": result.get("state_counts", {}),
    }


def _set_variant_config(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    cfg = copy.deepcopy(base)
    for key, value in overrides.items():
        if key == "caution_minority":
            cfg["caution"]["leverage_minority_percent_change"] = float(value)
        elif key == "caution_people":
            cfg["caution"]["leverage_total_people_change_ratio"] = float(value)
        elif key == "caution_cap":
            cfg["caution"]["leverage_weight_cap"] = float(value)
        elif key == "risk_minority":
            cfg["risk_off"]["leverage_minority_percent_change"] = float(value)
        elif key == "risk_people":
            cfg["risk_off"]["leverage_total_people_change_ratio"] = float(value)
        elif key == "risk_cap":
            cfg["risk_off"]["leverage_weight_cap"] = float(value)
        elif key == "destination":
            cfg["released_leverage_budget_destination"] = str(value)
        elif key == "primary_fraction":
            cfg["released_to_primary_fraction"] = float(value)
        elif key == "lookback_weeks":
            cfg["lookback_weeks"] = int(value)
        else:
            raise ValueError(f"Unsupported override key: {key}")
    return cfg


def _variant_specs() -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    specs: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
        ("latest_default", {}, {}),
        ("threshold_lenient", {"caution_minority": 3.5, "caution_people": 0.30, "risk_minority": 5.0, "risk_people": 0.42}, {}),
        ("threshold_strict", {"caution_minority": 5.0, "caution_people": 0.45, "risk_minority": 7.0, "risk_people": 0.60}, {}),
        ("lookback_6w", {"lookback_weeks": 6}, {}),
        ("lookback_10w", {"lookback_weeks": 10}, {}),
        ("riskcap_003", {"risk_cap": 0.03}, {}),
        ("riskcap_005", {"risk_cap": 0.05}, {}),
        ("cautioncap_005", {"caution_cap": 0.05}, {}),
        ("cautioncap_015", {"caution_cap": 0.15}, {}),
        ("destination_primary", {"destination": "primary"}, {}),
        ("destination_split25", {"destination": "split_primary_cash", "primary_fraction": 0.25}, {}),
        ("destination_split75", {"destination": "split_primary_cash", "primary_fraction": 0.75}, {}),
        ("strict_split25", {"caution_minority": 5.0, "caution_people": 0.45, "risk_minority": 7.0, "risk_people": 0.60, "destination": "split_primary_cash", "primary_fraction": 0.25}, {}),
        ("lenient_cash_riskcap003", {"caution_minority": 3.5, "caution_people": 0.30, "risk_minority": 5.0, "risk_people": 0.42, "risk_cap": 0.03}, {}),
    ]
    throttle_modes = [
        ("throttle_caution_cash", "caution", "cash"),
        ("throttle_risk_cash", "risk_off", "cash"),
        ("throttle_caution_primary", "caution", "primary"),
        ("throttle_risk_primary", "risk_off", "primary"),
    ]
    for name, min_state, release_to in throttle_modes:
        specs.append((name, {}, {"enabled": True, "min_state": min_state, "release_to": release_to}))
    specs.extend(
        [
            ("strict_throttle_caution_cash", {"caution_minority": 5.0, "caution_people": 0.45, "risk_minority": 7.0, "risk_people": 0.60}, {"enabled": True, "min_state": "caution", "release_to": "cash"}),
            ("split25_throttle_risk_cash", {"destination": "split_primary_cash", "primary_fraction": 0.25}, {"enabled": True, "min_state": "risk_off", "release_to": "cash"}),
        ]
    )
    return specs


def _state_at_least(state: str, min_state: str) -> bool:
    order = {"normal": 0, "caution": 1, "risk_off": 2}
    return order.get(state, -1) >= order.get(min_state, 99)


def _apply_leverage_buy_throttle(
    events: list[dict[str, Any]],
    prices: pd.DataFrame,
    config: dict[str, Any],
    db_path: Path,
    throttle: dict[str, Any],
) -> list[dict[str, Any]]:
    if not throttle.get("enabled"):
        return copy.deepcopy(events)

    raw_states = [str(_cached_raw_tdcc_state(config, db_path, dt)["state"]) for dt in prices.index]
    effective_states = _apply_hysteresis(
        raw_states,
        Variant("throttle_state", risk_off_cap=float(config["risk_off"]["leverage_weight_cap"]), caution_cap=float(config["caution"]["leverage_weight_cap"])),
    )
    state_by_date = dict(zip(prices.index.normalize(), effective_states))
    min_state = str(throttle.get("min_state", "caution"))
    release_to = str(throttle.get("release_to", "cash"))
    adjusted: list[dict[str, Any]] = []
    previous_leverage = 0.0
    for event in events:
        item = copy.deepcopy(event)
        weights = {str(k): float(v) for k, v in item["target_weights"].items()}
        date = pd.Timestamp(item["date"]).normalize()
        state = state_by_date.get(date, "normal")
        leverage = float(weights.get("00631L.TW", 0.0))
        if _state_at_least(state, min_state) and leverage > previous_leverage:
            released = leverage - previous_leverage
            weights["00631L.TW"] = previous_leverage
            if release_to == "primary":
                weights["0050.TW"] = float(weights.get("0050.TW", 0.0)) + released
            else:
                item["target_cash_weight_adjustment"] = float(item.get("target_cash_weight_adjustment", 0.0)) + released
        previous_leverage = float(weights.get("00631L.TW", 0.0))
        item["target_weights"] = weights
        adjusted.append(item)
    return adjusted


def _inject_cash_adjustment(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold throttle cash adjustment into weights via a synthetic tiny cash gap.

    _simulate_tdcc_overlay derives base_cash as 1 - sum(target_weights). Keeping
    the released weight out of ticker weights is enough.
    """
    adjusted = []
    for event in events:
        item = copy.deepcopy(event)
        cash_adjustment = float(item.pop("target_cash_weight_adjustment", 0.0))
        if cash_adjustment > 0:
            weights = {str(k): float(v) for k, v in item["target_weights"].items()}
            total = sum(weights.values())
            if total + cash_adjustment > 1.0:
                scale = max((1.0 - cash_adjustment) / max(total, 1e-12), 0.0)
                weights = {k: v * scale for k, v in weights.items()}
            item["target_weights"] = weights
        adjusted.append(item)
    return adjusted


def main() -> None:
    args = _parse_args()
    result_json = _resolve(args.result_json)
    source_backtest = _resolve(args.source_backtest)
    config_path = _resolve(args.config)
    db_path = _resolve(args.db)
    output = _resolve(args.output)
    base_config = json.loads(config_path.read_text(encoding="utf-8"))
    latest_module._raw_tdcc_state = _cached_raw_tdcc_state

    if source_backtest.exists():
        base, base_events, dates, initial_cash = _load_base_from_source(source_backtest)
    else:
        payload = json.loads(result_json.read_text(encoding="utf-8"))
        base, panel, base_events, _ = _run_base_backtest(
            payload,
            result_json,
            start=str(args.start),
            end=str(args.end),
            download_end=str(args.download_end),
        )
        dates = [pd.Timestamp(value).normalize() for value in panel["date"].tolist()]
        initial_cash = float(payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH))
    prices = _load_prices(db_path, dates)

    rows: list[dict[str, Any]] = []
    results: dict[str, Any] = {}
    curves = pd.DataFrame(index=prices.index)
    curves["base_exact"] = pd.Series(base["equity_curve"], index=prices.index, dtype=float)

    for name, overrides, throttle in _variant_specs():
        config = _set_variant_config(base_config, overrides)
        events = _apply_leverage_buy_throttle(base_events, prices, config, db_path, throttle)
        events = _inject_cash_adjustment(events)
        result = _simulate_tdcc_overlay(
            prices,
            events,
            config,
            db_path,
            initial_cash=initial_cash,
            fee_rate=float(args.fee_rate),
            dca_history=base["dca_purchase_history"],
        )
        row = _metric_row(name, result)
        row["overrides"] = overrides
        row["throttle"] = throttle
        rows.append(row)
        results[name] = {"settings": {"overrides": overrides, "throttle": throttle}, **result}
        curves[name] = pd.Series([item["value"] for item in result["equity_curve"]], index=pd.to_datetime([item["date"] for item in result["equity_curve"]]))
        print(
            f"{name}: final={row['final_value']:.2f}, sharpe={row['sharpe_ratio']:.4f}, "
            f"mdd={row['max_drawdown']:.4%}, rebalances={row['num_rebalances']}, fees={row['fees_paid_estimate']:.2f}"
        )

    baseline = next(row for row in rows if row["variant"] == "latest_default")
    for row in rows:
        row["delta_final_value"] = row["final_value"] - baseline["final_value"]
        row["delta_sharpe_ratio"] = row["sharpe_ratio"] - baseline["sharpe_ratio"]
        row["delta_max_drawdown"] = row["max_drawdown"] - baseline["max_drawdown"]
        row["delta_fees_paid_estimate"] = row["fees_paid_estimate"] - baseline["fees_paid_estimate"]

    best_final = max(rows, key=lambda row: row["final_value"])
    best_sharpe = max(rows, key=lambda row: row["sharpe_ratio"])
    best_mdd_with_final_floor = max(
        [row for row in rows if row["final_value"] >= baseline["final_value"] * 0.98],
        key=lambda row: row["max_drawdown"],
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    curve_path = output.with_name(output.stem + "_curve.csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    curves.index.name = "date"
    curves.to_csv(curve_path, encoding="utf-8-sig")
    report = {
        "experiment": "group_a_tdcc_improvement_sweep",
        "method_note": "No PPO retraining. Reuses one full Group A base replay and sweeps TDCC thresholds, risk-off destination, and 00631L buy throttles.",
        "requested_window": {"start": args.start, "end": args.end, "download_end": args.download_end},
        "source_backtest": str(source_backtest.resolve()) if source_backtest.exists() else None,
        "actual_window": {"start": base["actual_start"], "end": base["actual_end"], "rows": base["rows"]},
        "base_exact_metrics": {k: v for k, v in base.items() if isinstance(v, (int, float, str))},
        "baseline_latest_default": baseline,
        "best": {
            "best_final": best_final,
            "best_sharpe": best_sharpe,
            "best_mdd_with_98pct_final_floor": best_mdd_with_final_floor,
        },
        "results": rows,
        "detailed_results": results,
        "outputs": {"json": str(output), "csv": str(csv_path), "curve_csv": str(curve_path)},
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Curve CSV: {curve_path}")
    print(f"Best final: {best_final['variant']} {best_final['final_value']:.2f}")
    print(f"Best sharpe: {best_sharpe['variant']} {best_sharpe['sharpe_ratio']:.4f}")
    print(f"Best MDD with 98% final floor: {best_mdd_with_final_floor['variant']} {best_mdd_with_final_floor['max_drawdown']:.4%}")


if __name__ == "__main__":
    main()
