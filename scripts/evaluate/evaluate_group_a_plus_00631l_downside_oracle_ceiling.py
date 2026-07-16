#!/usr/bin/env python3
"""Oracle ceiling test: is a downside-specific (not symmetric) 00631L signal
even theoretically worth building a forecast model for?

Research-only, and NOT a real forecast -- this uses actual future prices
(look-ahead) to answer one question only: if we had a PERFECT forward-10-day
00631L downside-risk oracle, would de-risking on it beat a2118 baseline
after costs? If even the oracle can't clear that bar, no realistic model
built on the same label could either, and the modeling effort isn't worth
it. If the oracle does show a clear margin, that margin is the ceiling a
real (imperfect) forecast would have to partially capture.

Three label definitions per the user's request (2026-07-10):
  A) future 10d 00631L max drawdown < -X%
  B) future 10d 00631L hits -Y% before +Z% ("race" / first-touch)
  C) future 10d 00631L downside semivariance in the top 20% (by percentile)

De-risk action when the oracle label fires: 00631L -> 0%, freed weight to
0050.TW (same mechanic as the tiered control script), only on golden1 days.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices, _metrics
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_00631l_downside_oracle_ceiling_latest.json"

HORIZON = 10
MDD_THRESHOLD = -0.10  # label A: future 10d 00631L max drawdown worse than -10%
RACE_DOWN_THRESHOLD = -0.08  # label B: hits -8% before +12%
RACE_UP_THRESHOLD = 0.12
SEMIVOL_PERCENTILE = 0.80  # label C: top 20% downside semivariance

DEFAULT_WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31"),
    ("inflation_2022", "2022-01-03", "2022-12-30"),
    ("live_2024_2026", "2024-01-02", "latest"),
    ("active_2025_2026", "2025-01-02", "latest"),
]


def _resolve_end_date(db_path: Path, requested_end: str, ticker: str = "0050.TW") -> str:
    if str(requested_end).lower() != "latest":
        return requested_end
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        max_dt = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()[0]
    finally:
        con.close()
    return pd.Timestamp(max_dt).strftime("%Y-%m-%d")


def _future_paths(close: pd.Series, horizon: int) -> pd.DataFrame:
    """DataFrame of forward cumulative returns for day 1..horizon, indexed like close."""
    cols = {}
    for i in range(1, horizon + 1):
        cols[i] = close.shift(-i) / close - 1.0
    return pd.DataFrame(cols, index=close.index)


def _label_max_drawdown(close_00631l: pd.Series, horizon: int) -> pd.Series:
    future = _future_paths(close_00631l, horizon)
    return future.min(axis=1, skipna=False)


def _label_race(close_00631l: pd.Series, horizon: int, down_thr: float, up_thr: float) -> pd.Series:
    """True if the down threshold is hit on an earlier day than the up threshold
    (or the up threshold is never hit within horizon while down is)."""
    future = _future_paths(close_00631l, horizon)

    def _race_row(row: pd.Series) -> bool | float:
        if row.isna().any():
            return np.nan
        down_hits = np.where(row.to_numpy() <= down_thr)[0]
        up_hits = np.where(row.to_numpy() >= up_thr)[0]
        down_day = down_hits[0] if len(down_hits) else None
        up_day = up_hits[0] if len(up_hits) else None
        if down_day is None:
            return False
        if up_day is None:
            return True
        return down_day < up_day

    return future.apply(_race_row, axis=1)


def _label_downside_semivol(close_00631l: pd.Series, horizon: int, percentile: float) -> pd.Series:
    daily_ret = close_00631l.pct_change().fillna(0.0)
    future_daily = pd.concat([daily_ret.shift(-i) for i in range(1, horizon + 1)], axis=1)
    downside_sq = future_daily.clip(upper=0.0) ** 2
    semivar = downside_sq.mean(axis=1, skipna=False)
    rank_pct = semivar.rank(pct=True)
    return rank_pct >= percentile


def _weights_de_risked(golden_weights: dict[str, float]) -> dict[str, float]:
    weights = dict(golden_weights)
    shift = float(weights.get("00631L.TW", 0.0) or 0.0)
    weights["00631L.TW"] = 0.0
    weights["0050.TW"] = float(weights.get("0050.TW", 0.0) or 0.0) + shift
    return _normalize(weights)


def _simulate_oracle_curve(
    prices: pd.DataFrame,
    execution_regime: pd.Series,
    de_risk_flag: pd.Series,
    golden_weights: dict[str, float],
    de_risked_weights: dict[str, float],
    weights_by_regime: dict[str, dict[str, float]],
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.Series, dict[str, float]]:
    shares = {t: 0.0 for t in TICKERS}
    cash = float(initial_value)
    applied_key: str | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[t] * float(price_row[t]) for t in TICKERS)
        regime = str(execution_regime.loc[dt])
        if regime == "golden1":
            flagged = bool(de_risk_flag.loc[dt]) if dt in de_risk_flag.index and pd.notna(de_risk_flag.loc[dt]) else False
            key = "golden1_derisked" if flagged else "golden1"
            target_weights = de_risked_weights if flagged else golden_weights
        else:
            key = regime
            target_weights = weights_by_regime.get(regime, golden_weights)

        if key != applied_key:
            weights = _normalize(target_weights)
            current_values = {t: shares[t] * float(price_row[t]) for t in TICKERS}
            net_value = gross_value
            cost = 0.0
            turnover = 0.0
            for _ in range(3):
                target_values = {t: net_value * weights.get(t, 0.0) for t in TICKERS}
                cost, turnover = _trade_cost(
                    current_values, target_values, commission_rate, slippage_rate, equity_etf_sell_tax
                )
                net_value = max(gross_value - cost, 0.0)
            shares = {t: net_value * weights.get(t, 0.0) / max(float(price_row[t]), 1e-12) for t in TICKERS}
            cash = net_value * weights.get("cash", 0.0)
            gross_value = net_value
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            applied_key = key
        values.append(gross_value)

    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
    }


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    db_path: Path,
    initial_value: float,
    ncf_panel_631l: str | None,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> dict[str, Any]:
    end = _resolve_end_date(db_path, end)
    report, frame = run_a2118(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db_path,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
        ncf_panel_631l_path=ncf_panel_631l,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    )
    prices = _load_prices(db_path, list(TICKERS), start, end)
    total_return_prices, dividend_coverage = _load_total_return_prices(db_path, prices.index)
    close_00631l = total_return_prices["00631L.TW"].reindex(frame.index)

    execution_regime = frame["execution_regime"].astype(str)
    baseline_metrics = dict(report["metrics"])
    baseline_execution = dict(report["execution"])
    golden_weights = dict(report["base_weights"]["golden1"])
    weights_by_regime = dict(report["base_weights"])
    de_risked_weights = _weights_de_risked(golden_weights)

    label_a = (_label_max_drawdown(close_00631l, HORIZON) < MDD_THRESHOLD).reindex(frame.index)
    label_b = _label_race(close_00631l, HORIZON, RACE_DOWN_THRESHOLD, RACE_UP_THRESHOLD).reindex(frame.index).astype("boolean").fillna(False)
    label_c = _label_downside_semivol(close_00631l, HORIZON, SEMIVOL_PERCENTILE).reindex(frame.index)

    golden_mask = execution_regime == "golden1"
    label_results = {}
    for name, flag in (("A_max_drawdown", label_a), ("B_race_down_first", label_b), ("C_downside_semivol_top20pct", label_c)):
        flag = flag.fillna(False).astype(bool)
        curve, sim = _simulate_oracle_curve(
            total_return_prices,
            execution_regime,
            flag,
            golden_weights,
            de_risked_weights,
            weights_by_regime,
            initial_value,
            commission_rate,
            slippage_rate,
            equity_etf_sell_tax,
        )
        metrics = _metrics(curve, initial_value)
        label_results[name] = {
            "metrics": metrics,
            "delta_vs_baseline": {
                "final_value": metrics["final_value"] - baseline_metrics["final_value"],
                "sharpe_ratio": metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"],
                "max_drawdown": metrics["max_drawdown"] - baseline_metrics["max_drawdown"],
            },
            "flagged_days_within_golden1": int((flag & golden_mask).sum()),
            "extra_transaction_cost": float(sim["transaction_cost"] - baseline_execution.get("transaction_cost", 0.0)),
            "extra_rebalances": int(sim["rebalance_count"] - baseline_execution.get("rebalance_count", 0)),
        }

    return {
        "label": label,
        "window": {"start": start, "end": end, "rows": int(len(frame))},
        "golden1_days": int(golden_mask.sum()),
        "baseline_metrics": baseline_metrics,
        "oracle_labels": label_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--ncf-panel-631l", default="results/ncf_00631l_panel_latest_20260707.csv")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    results = []
    for label, start, end in DEFAULT_WINDOWS:
        result = evaluate_window(
            label=label,
            start=start,
            end=end,
            db_path=db_path,
            initial_value=args.initial_value,
            ncf_panel_631l=args.ncf_panel_631l,
            commission_rate=args.commission_rate,
            slippage_rate=args.slippage_rate,
            equity_etf_sell_tax=args.equity_etf_sell_tax,
        )
        results.append(result)
        print(f"\n{label} (golden1_days={result['golden1_days']}):")
        for name, res in result["oracle_labels"].items():
            d = res["delta_vs_baseline"]
            print(
                f"  {name}: flagged={res['flagged_days_within_golden1']} "
                f"delta_final={d['final_value']:.1f} delta_sharpe={d['sharpe_ratio']:.4f} "
                f"delta_mdd={d['max_drawdown']:.4f} extra_cost={res['extra_transaction_cost']:.1f}"
            )

    payload = {
        "experiment": "group_a_plus_00631l_downside_oracle_ceiling",
        "policy": "research_only_oracle_uses_future_data_not_a_real_forecast",
        "thresholds": {
            "horizon_days": HORIZON,
            "label_a_mdd_threshold": MDD_THRESHOLD,
            "label_b_race_down": RACE_DOWN_THRESHOLD,
            "label_b_race_up": RACE_UP_THRESHOLD,
            "label_c_semivol_percentile": SEMIVOL_PERCENTILE,
        },
        "windows": results,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
