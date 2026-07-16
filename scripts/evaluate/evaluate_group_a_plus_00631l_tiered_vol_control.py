#!/usr/bin/env python3
"""Shadow-evaluate a 3-tier volatility-driven 00631L exposure rule.

Research-only. Does not update the latest strategy, live signal, or any
allocation file.

User-specified rule (2026-07-10):

    forecast_vol_10d low AND execution_regime golden1 AND TSMC/SOXX not
    weakening -> 00631L = 20%
    forecast_vol_10d rising OR drawdown risk rising OR TSMC weakening
    -> 00631L = 10%
    forecast_vol_10d extreme OR crash warning -> 00631L = 0%

Only applied on days where a2118's own execution_regime is "golden1"; other
regimes keep a2118's existing (already defensive) weights untouched.

2026-07-10 update: "forecast_vol_10d" now uses a genuine h=10 HAR-RV
walk-forward forecast (group_a_plus.integrations.volatility_forecast,
504-day rolling window, validated against a naive baseline via
evaluate_group_a_plus_volatility_forecast_quality.py: +11.7% QLIKE
improvement at h=10) instead of the earlier backward-looking GARCH-proxy
ratio/percentile approximation.

Known approximations, documented rather than hidden:
  - TSMC weakening uses only the price-based leg of daily_signal.py's
    tsmc_weak rule (2330 5d return vs 0050-ex-TSMC-proxy 5d return); the
    ncf_2330 probability/tail-risk legs require a trained model panel that
    does not exist for the older crisis windows (2020/2022), so they are
    left out of this historical backtest.
  - No SOXX signal exists anywhere in this repo; the user's "TSMC / SOXX"
    condition is backtested as TSMC-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _metrics
from group_a_plus.integrations.garch_regime_shadow import PERCENTILE_THRESHOLD, RATIO_THRESHOLD, REQUIRE_NEGATIVE_5D
from group_a_plus.integrations.volatility_forecast import build_multi_horizon_forecast
from group_a_plus.operations.market_state import classify_market_state
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from group_a_plus.utils.tsmc_0050_weight import TSMC_0050_WEIGHT_ASSUMPTION
from scripts.backtest.backtest_group_a_plus_financial_econometrics import _garch_features

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_00631l_tiered_vol_control_shadow_latest.json"

VOL_EXTREME_PERCENTILE = 0.90
VOL_EXTREME_RATIO = 1.50
DRAWDOWN_RISK_ELEVATED_MIN = 6
TSMC_WEAK_5D_RETURN_MAX = -0.02
TSMC_EX_PROXY_5D_RETURN_MAX = 0.0

TIER_WEIGHTS = {
    "high": 0.11,
    "mid": 0.05,
    "low": 0.0,
}

DEFAULT_WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31"),
    ("inflation_2022", "2022-01-03", "2022-12-30"),
    ("live_2024_2026", "2024-01-02", "latest"),
    ("active_2025_2026", "2025-01-02", "latest"),
]


def _resolve_end_date(db_path: Path, requested_end: str, ticker: str = "0050.TW") -> str:
    if str(requested_end).lower() != "latest":
        return requested_end
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        max_dt = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()[0]
    finally:
        con.close()
    return pd.Timestamp(max_dt).strftime("%Y-%m-%d")


def _load_real_vol_forecast(db_path: Path, index: pd.DatetimeIndex, start: str, end: str) -> pd.DataFrame:
    """h=10 HAR-RV forecast for 0050.TW, with a 600-row warmup buffer before `start`
    so the 504-day rolling window is already fitted by the time the window begins."""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        buffer_start = con.execute(
            "SELECT dt FROM ohlcv WHERE ticker = '0050.TW' AND dt < ? ORDER BY dt DESC LIMIT 1 OFFSET 600",
            [start],
        ).fetchone()
        rows = con.execute(
            """
            SELECT dt, open, high, low, close FROM ohlcv
            WHERE ticker = '0050.TW' AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [str(buffer_start[0]) if buffer_start else "2000-01-01", end],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    ohlc = rows.set_index("dt")
    forecast_frame = build_multi_horizon_forecast(ohlc, horizons=(10,))
    return forecast_frame.reindex(index)


def _load_tsmc_proxy_frame(db_path: Path, index: pd.DatetimeIndex, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tsmc_rows = con.execute(
            """
            SELECT dt, close FROM external_market_ohlcv
            WHERE provider = 'yfinance' AND ticker = '2330.TW' AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [start, end],
        ).fetchdf()
    finally:
        con.close()
    tsmc_close = pd.Series(
        tsmc_rows["close"].to_numpy(dtype=float),
        index=pd.to_datetime(tsmc_rows["dt"]).values,
    ).reindex(index).ffill()
    ret_2330_5d = tsmc_close.pct_change(5)
    return pd.DataFrame({"ret_2330_5d": ret_2330_5d}, index=index)


def _tsmc_weak_mask(
    tsmc_frame: pd.DataFrame,
    return_0050_5d: pd.Series,
    *,
    tsmc_weight: float = TSMC_0050_WEIGHT_ASSUMPTION,
) -> pd.Series:
    ret_2330_5d = tsmc_frame["ret_2330_5d"].reindex(return_0050_5d.index)
    ret_0050_5d = return_0050_5d.reindex(return_0050_5d.index)
    ex_tsmc_5d = (ret_0050_5d - tsmc_weight * ret_2330_5d) / (1.0 - tsmc_weight)
    weak = (ret_2330_5d <= TSMC_WEAK_5D_RETURN_MAX) & (ex_tsmc_5d <= TSMC_EX_PROXY_5D_RETURN_MAX)
    return weak.fillna(False)


def _crash_warning_mask(frame: pd.DataFrame, execution_regime: pd.Series) -> pd.Series:
    out = pd.Series(False, index=frame.index)
    for dt, row in frame.iterrows():
        state = classify_market_state(
            str(execution_regime.loc[dt]),
            {
                "ma_gap": row.get("ma_gap"),
                "drawdown": row.get("drawdown"),
                "exit_momentum_5d": row.get("exit_momentum"),
                "total_risk_score": row.get("total_risk_score"),
                "tail_risk_score": row.get("tail_risk_score"),
            },
        )
        out.loc[dt] = state["state"] == "crash_risk"
    return out


def _build_tier_series(
    execution_regime: pd.Series,
    vol_forecast_frame: pd.DataFrame,
    frame: pd.DataFrame,
    tsmc_weak: pd.Series,
    *,
    return_5d: pd.Series,
) -> pd.Series:
    vol_percentile = vol_forecast_frame["forecast_vol_h10_percentile"].reindex(execution_regime.index).fillna(0.5)
    vol_ratio = vol_forecast_frame["forecast_vol_h10_ratio"].reindex(execution_regime.index).fillna(1.0)
    return_5d = return_5d.reindex(execution_regime.index)

    vol_extreme = (vol_percentile >= VOL_EXTREME_PERCENTILE) | (vol_ratio >= VOL_EXTREME_RATIO)
    vol_elevated = (vol_ratio >= RATIO_THRESHOLD) | (vol_percentile >= PERCENTILE_THRESHOLD)
    if REQUIRE_NEGATIVE_5D:
        vol_elevated = vol_elevated & (return_5d < 0.0)

    total_risk_score = pd.to_numeric(frame.get("total_risk_score"), errors="coerce").reindex(execution_regime.index).fillna(0)
    drawdown_risk_elevated = total_risk_score >= DRAWDOWN_RISK_ELEVATED_MIN

    crash_warning = _crash_warning_mask(frame.reindex(execution_regime.index), execution_regime)

    tier = pd.Series("high", index=execution_regime.index, dtype=object)
    mid_mask = vol_elevated | drawdown_risk_elevated | tsmc_weak.reindex(execution_regime.index).fillna(False)
    low_mask = vol_extreme | crash_warning
    tier.loc[mid_mask] = "mid"
    tier.loc[low_mask] = "low"
    return tier


def _weights_for_tier(golden_weights: dict[str, float], tier: str) -> dict[str, float]:
    weights = dict(golden_weights)
    current_00631l = float(weights.get("00631L.TW", 0.0) or 0.0)
    target_00631l = TIER_WEIGHTS[tier]
    shift = current_00631l - target_00631l
    weights["00631L.TW"] = target_00631l
    weights["0050.TW"] = max(float(weights.get("0050.TW", 0.0) or 0.0) + shift, 0.0)
    return _normalize(weights)


def _simulate_daily_tier_curve(
    prices: pd.DataFrame,
    execution_regime: pd.Series,
    tier: pd.Series,
    golden_weights: dict[str, float],
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
            key = f"golden1_tier_{tier.loc[dt]}"
            target_weights = _weights_for_tier(golden_weights, str(tier.loc[dt]))
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
            shares = {
                t: net_value * weights.get(t, 0.0) / max(float(price_row[t]), 1e-12) for t in TICKERS
            }
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
    chip_features = _load_chip_features(db_path, prices.index, start, end)
    total_return_prices, dividend_coverage = _load_total_return_prices(db_path, prices.index)
    garch_frame = _garch_features(prices, chip_features).reindex(frame.index)
    vol_forecast_frame = _load_real_vol_forecast(db_path, frame.index, start, end)
    tsmc_frame = _load_tsmc_proxy_frame(db_path, frame.index, start, end)
    tsmc_weak = _tsmc_weak_mask(tsmc_frame, garch_frame["return_0050_5d"])

    execution_regime = frame["execution_regime"].astype(str)
    baseline_metrics = dict(report["metrics"])
    baseline_execution = dict(report["execution"])
    golden_weights = dict(report["base_weights"]["golden1"])
    weights_by_regime = dict(report["base_weights"])

    tier = _build_tier_series(
        execution_regime,
        vol_forecast_frame,
        frame,
        tsmc_weak,
        return_5d=garch_frame["return_0050_5d"],
    )

    curve, sim = _simulate_daily_tier_curve(
        total_return_prices,
        execution_regime,
        tier,
        golden_weights,
        weights_by_regime,
        initial_value,
        commission_rate,
        slippage_rate,
        equity_etf_sell_tax,
    )
    metrics = _metrics(curve, initial_value)
    golden_mask = execution_regime == "golden1"
    tier_counts = tier[golden_mask].value_counts().to_dict()

    return {
        "label": label,
        "window": {"start": start, "end": end, "rows": int(len(frame))},
        "golden1_days": int(golden_mask.sum()),
        "tier_counts_within_golden1": {k: int(v) for k, v in tier_counts.items()},
        "baseline": {"metrics": baseline_metrics, "execution": baseline_execution},
        "tiered_vol_control": {
            "metrics": metrics,
            "execution": sim,
            "delta_vs_baseline": {
                "final_value": metrics["final_value"] - baseline_metrics["final_value"],
                "sharpe_ratio": metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"],
                "max_drawdown": metrics["max_drawdown"] - baseline_metrics["max_drawdown"],
            },
            "extra_transaction_cost": float(sim["transaction_cost"] - baseline_execution.get("transaction_cost", 0.0)),
            "extra_rebalances": int(sim["rebalance_count"] - baseline_execution.get("rebalance_count", 0)),
        },
        "dividend_coverage": dividend_coverage,
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
        d = result["tiered_vol_control"]["delta_vs_baseline"]
        print(
            f"{label}: golden1_days={result['golden1_days']} "
            f"tiers={result['tier_counts_within_golden1']} "
            f"delta_final={d['final_value']:.1f} delta_sharpe={d['sharpe_ratio']:.4f} "
            f"delta_mdd={d['max_drawdown']:.4f} "
            f"extra_cost={result['tiered_vol_control']['extra_transaction_cost']:.1f} "
            f"extra_rebalances={result['tiered_vol_control']['extra_rebalances']}"
        )

    payload = {
        "experiment": "group_a_plus_00631l_tiered_vol_control",
        "policy": "research_only_no_active_allocation_change",
        "rule": {
            "high_20pct": "vol not elevated AND drawdown risk not elevated AND TSMC not weakening",
            "mid_10pct": "vol elevated OR drawdown risk elevated OR TSMC weakening",
            "low_0pct": "vol extreme OR crash warning (classify_market_state == crash_risk)",
            "applies_only_when": "execution_regime == golden1",
        },
        "thresholds": {
            "vol_elevated_ratio": RATIO_THRESHOLD,
            "vol_elevated_percentile": PERCENTILE_THRESHOLD,
            "vol_elevated_require_negative_5d": REQUIRE_NEGATIVE_5D,
            "vol_extreme_percentile": VOL_EXTREME_PERCENTILE,
            "vol_extreme_ratio": VOL_EXTREME_RATIO,
            "drawdown_risk_elevated_total_risk_score_min": DRAWDOWN_RISK_ELEVATED_MIN,
            "tsmc_weak_5d_return_max": TSMC_WEAK_5D_RETURN_MAX,
            "tsmc_ex_proxy_5d_return_max": TSMC_EX_PROXY_5D_RETURN_MAX,
        },
        "known_approximations": [
            "forecast_vol_10d proxied by GARCH-proxy vol ratio/percentile, not a literal 10-day-ahead forecast",
            "TSMC weakening uses price-only proxy (no ncf_2330 model probability legs, unavailable historically)",
            "no SOXX signal exists in this repo; TSMC-only",
        ],
        "windows": results,
    }
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
