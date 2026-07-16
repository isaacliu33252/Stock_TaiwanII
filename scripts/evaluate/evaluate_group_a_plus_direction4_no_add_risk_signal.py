#!/usr/bin/env python3
"""Evaluate Direction 4: risk signal blocks 00631L adds, without de-risking.

This is stricter than the live pre-trade guard audit because it tests several
observable risk masks at every A21.18 regime rebalance. If the requested target
would increase 00631L while the mask is active, only the excess add is moved to
0050. Existing 00631L is not sold and model target weights are not promoted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _metrics
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import (
    _build_volatility_gate_frame,
    _current_weights,
    _metric_delta,
)

PANEL_2025_2026 = "results/ncf_00631l_panel_latest_20260707.csv"
PANEL_2017_2019 = "results/ncf_00631l_panel_backfill_2017_2019_20260710.csv"

WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31", PANEL_2025_2026, "tuning_window"),
    ("inflation_2022", "2022-01-03", "2022-12-30", PANEL_2025_2026, "tuning_window"),
    ("live_2024_2026", "2024-01-02", "2026-07-09", PANEL_2025_2026, "tuning_window"),
    ("active_2025_2026", "2025-01-02", "2026-07-09", PANEL_2025_2026, "tuning_window"),
    ("2017_bull", "2017-01-03", "2017-12-29", PANEL_2017_2019, "out_of_sample"),
    ("2018_correction", "2018-01-02", "2018-12-31", PANEL_2017_2019, "out_of_sample"),
    ("2019_recovery", "2019-01-02", "2019-12-31", PANEL_2017_2019, "out_of_sample"),
]


def _throttle_00631l_add(
    target: dict[str, float],
    current: dict[str, float],
    allowed_add_fraction: float,
    destination: str = "0050.TW",
) -> tuple[dict[str, float], bool, float]:
    target_w = _normalize(dict(target))
    current_631l = float(current.get("00631L.TW", 0.0) or 0.0)
    target_631l = float(target_w.get("00631L.TW", 0.0) or 0.0)
    excess_add = max(target_631l - current_631l, 0.0)
    if excess_add <= 1e-12:
        return target_w, False, 0.0
    allowed_add_fraction = min(max(float(allowed_add_fraction), 0.0), 1.0)
    blocked_add = excess_add * (1.0 - allowed_add_fraction)
    target_w["00631L.TW"] = target_631l - blocked_add
    target_w[destination] = float(target_w.get(destination, 0.0) or 0.0) + blocked_add
    return _normalize(target_w), blocked_add > 1e-12, float(blocked_add)


def _simulate_no_add_on_mask(
    prices: pd.DataFrame,
    regimes: pd.Series,
    risk_mask: pd.Series,
    weights_by_regime: dict[str, dict[str, float]],
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    block_initial_entry: bool = False,
    allowed_add_fraction: float = 0.0,
) -> tuple[pd.Series, dict[str, Any]]:
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    current_regime: str | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0
    no_add_days = 0
    capped_weight_sum = 0.0
    events: list[dict[str, Any]] = []

    risk_mask = risk_mask.reindex(regimes.index).fillna(False).astype(bool)
    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        next_regime = str(regimes.loc[dt])
        if next_regime != current_regime:
            current_w = _current_weights(gross_value, price_row, shares, cash)
            weights = _normalize(weights_by_regime[next_regime])
            should_block = bool(risk_mask.loc[dt]) and (block_initial_entry or current_regime is not None)
            if should_block:
                weights, capped, capped_weight = _throttle_00631l_add(weights, current_w, allowed_add_fraction)
                if capped:
                    no_add_days += 1
                    capped_weight_sum += capped_weight
                    events.append(
                        {
                            "date": str(pd.Timestamp(dt).date()),
                            "regime": next_regime,
                            "current_00631l_weight": round(float(current_w.get("00631L.TW", 0.0)), 6),
                            "requested_00631l_weight": round(float(weights_by_regime[next_regime].get("00631L.TW", 0.0)), 6),
                            "guarded_00631l_weight": round(float(weights.get("00631L.TW", 0.0)), 6),
                            "blocked_00631l_weight": round(float(capped_weight), 6),
                        }
                    )

            current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
            net_value = gross_value
            cost = 0.0
            turnover = 0.0
            for _ in range(3):
                target_values = {ticker: net_value * weights.get(ticker, 0.0) for ticker in TICKERS}
                cost, turnover = _trade_cost(
                    current_values,
                    target_values,
                    commission_rate,
                    slippage_rate,
                    equity_etf_sell_tax,
                )
                net_value = max(gross_value - cost, 0.0)
            shares = {
                ticker: net_value * weights.get(ticker, 0.0) / max(float(price_row[ticker]), 1e-12)
                for ticker in TICKERS
            }
            cash = net_value * weights.get("cash", 0.0)
            gross_value = net_value
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            current_regime = next_regime
        values.append(gross_value)
    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
        "no_add_days": int(no_add_days),
        "capped_00631l_weight_sum": round(float(capped_weight_sum), 6),
        "events": events,
        "policy": "risk_signal_no_00631l_add_no_derisk",
        "allowed_add_fraction": float(allowed_add_fraction),
    }


def _risk_masks(frame: pd.DataFrame, gate_frame: pd.DataFrame) -> dict[str, pd.Series]:
    total = frame.get("total_risk_score", pd.Series(0, index=frame.index)).fillna(0)
    tail = frame.get("tail_risk_score", pd.Series(0, index=frame.index)).fillna(0)
    high_vol = gate_frame["volatility_gate"].reindex(frame.index).fillna("neutral_vol") == "high_vol_defensive"
    masks = {
        "total_risk_ge_1": total >= 1,
        "total_risk_ge_2": total >= 2,
        "total_risk_ge_3": total >= 3,
        "tail_risk_ge_1": tail >= 1,
        "high_vol_gate": high_vol,
    }
    for base_name in ("total_risk_ge_2", "total_risk_ge_3", "high_vol_gate"):
        base = masks[base_name].astype(bool)
        for lookback in (5, 10, 20):
            masks[f"{base_name}_recent_{lookback}d"] = (
                base.rolling(lookback, min_periods=1).max().astype(bool)
            )
    return masks


def evaluate_window(label: str, start: str, end: str, panel: str, kind: str) -> dict[str, Any]:
    db_path = Path(DB_PATH)
    report, frame = run_a2118(
        start=start,
        end=end,
        initial_value=1_000_000.0,
        db=db_path,
        ncf_panel_631l_path=panel,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    )
    prices = _load_prices(db_path, list(TICKERS), start, end)
    chip = _load_chip_features(db_path, prices.index, start, end)
    total_return_prices, _ = _load_total_return_prices(db_path, frame.index)
    gate_frame = _build_volatility_gate_frame(prices, chip).reindex(frame.index)
    regimes = frame["execution_regime"].astype(str)
    baseline_metrics = dict(report["metrics"])
    baseline_execution = dict(report["execution"])
    variants: dict[str, Any] = {}
    policy_specs: list[tuple[str, pd.Series, float]] = []
    for name, mask in _risk_masks(frame, gate_frame).items():
        policy_specs.append((name, mask, 0.0))
    for name in ("total_risk_ge_2_recent_5d", "total_risk_ge_3_recent_5d", "high_vol_gate_recent_20d"):
        for allowed_fraction in (0.25, 0.50, 0.75):
            policy_specs.append((f"{name}_allow_{int(allowed_fraction * 100)}pct_add", _risk_masks(frame, gate_frame)[name], allowed_fraction))

    for name, mask, allowed_fraction in policy_specs:
        curve, sim = _simulate_no_add_on_mask(
            total_return_prices.reindex(regimes.index),
            regimes,
            mask,
            dict(report["base_weights"]),
            1_000_000.0,
            0.001425,
            0.0005,
            0.001,
            allowed_add_fraction=allowed_fraction,
        )
        metrics = _metrics(curve, 1_000_000.0)
        variants[name] = {
            "metrics": metrics,
            "execution": sim,
            "delta_vs_baseline": _metric_delta(metrics, baseline_metrics),
            "extra_rebalances": int(sim["rebalance_count"] - baseline_execution.get("rebalance_count", 0)),
            "extra_transaction_cost": float(sim["transaction_cost"] - baseline_execution.get("transaction_cost", 0.0)),
            "risk_active_days": int(mask.reindex(regimes.index).fillna(False).sum()),
        }
    return {
        "label": label,
        "kind": kind,
        "window": {"start": start, "end": end, "rows": int(len(frame))},
        "baseline": baseline_metrics,
        "variants": variants,
    }


def main() -> None:
    windows = [evaluate_window(*window) for window in WINDOWS]
    summary: dict[str, dict[str, float]] = {}
    variant_names = sorted(windows[0]["variants"])
    for variant in variant_names:
        tuning = [w for w in windows if w["kind"] == "tuning_window"]
        oos = [w for w in windows if w["kind"] == "out_of_sample"]
        summary[variant] = {
            "tuning_sum_delta_final_value": sum(w["variants"][variant]["delta_vs_baseline"]["delta_final_value"] for w in tuning),
            "tuning_sum_delta_sharpe_ratio": sum(w["variants"][variant]["delta_vs_baseline"]["delta_sharpe_ratio"] for w in tuning),
            "oos_sum_delta_final_value": sum(w["variants"][variant]["delta_vs_baseline"]["delta_final_value"] for w in oos),
            "oos_sum_delta_sharpe_ratio": sum(w["variants"][variant]["delta_vs_baseline"]["delta_sharpe_ratio"] for w in oos),
            "total_no_add_days": sum(w["variants"][variant]["execution"]["no_add_days"] for w in windows),
        }
        print(variant, summary[variant])

    payload = {
        "strategy": "group_a_plus_direction4_risk_signal_no_add",
        "research_only": True,
        "summary": summary,
        "windows": windows,
        "promotion_review": {
            "decision": "do_not_promote_keep_shadow",
            "reason": "No-add only must show positive OOS evidence before becoming more than an execution guard.",
        },
    }
    output = PROJECT_ROOT / "results" / "group_a_plus_direction4_no_add_risk_signal_20260710.json"
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
