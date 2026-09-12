#!/usr/bin/env python3
"""Validate regime-switching volatility shadow quality before guard use.

Research-only.  Compares the coefficient-clustered regime-switching forecast
from group_a_plus.integrations.regime_switching_volatility_shadow against the
existing HAR-RV forecast and naive persistence.  This script does not emit
target weights, execution regimes, or orders.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.regime_switching_volatility_shadow import coefficient_regime_forecast
from group_a_plus.integrations.risk_sensitive_loss import qlike_loss
from group_a_plus.integrations.volatility_forecast import (
    HORIZONS,
    _future_avg_variance,
    garman_klass_variance,
    har_rv_walkforward_forecast,
    naive_persistence_forecast,
)

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_regime_switching_volatility_forecast_quality_latest.json"


def _load_ohlc(db_path: Path, ticker: str, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, open, high, low, close FROM ohlcv
            WHERE ticker = ? AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [ticker, start, end],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")


def _zscore(series: pd.Series, window: int) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    mean = values.rolling(window, min_periods=max(10, window // 3)).mean()
    std = values.rolling(window, min_periods=max(10, window // 3)).std().replace(0.0, np.nan)
    return ((values - mean) / std).replace([np.inf, -np.inf], np.nan)


def _load_external_close(db_path: Path, ticker: str, index: pd.DatetimeIndex) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, close
            FROM external_market_ohlcv
            WHERE provider = 'yfinance' AND ticker = ?
            ORDER BY dt
            """,
            [ticker],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.Series(np.nan, index=index, dtype=float)
    rows["dt"] = pd.to_datetime(rows["dt"])
    return pd.to_numeric(rows.set_index("dt")["close"], errors="coerce").sort_index().shift(1).reindex(index).ffill()


def _load_taifex_augmented_features(db_path: Path, index: pd.DatetimeIndex) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        opt = con.execute(
            """
            SELECT dt, call_put, volume, open_interest, close
            FROM taifex_options_daily
            WHERE contract = 'TXO' AND trading_session = '一般'
            ORDER BY dt
            """
        ).fetchdf()
        fut = con.execute(
            """
            SELECT dt, contract_month, pct_change, volume, open_interest, settlement_price
            FROM taifex_futures_daily
            WHERE contract = 'TX' AND trading_session = '一般'
            ORDER BY dt, contract_month
            """
        ).fetchdf()
    finally:
        con.close()

    out = pd.DataFrame(index=index)
    if not opt.empty:
        opt["dt"] = pd.to_datetime(opt["dt"])
        piv_vol = opt.pivot_table(index="dt", columns="call_put", values="volume", aggfunc="sum")
        piv_oi = opt.pivot_table(index="dt", columns="call_put", values="open_interest", aggfunc="sum")
        piv_close = opt.pivot_table(index="dt", columns="call_put", values="close", aggfunc="mean")
        put_vol = piv_vol.get("Put", piv_vol.get("賣權", pd.Series(0.0, index=piv_vol.index)))
        call_vol = piv_vol.get("Call", piv_vol.get("買權", pd.Series(0.0, index=piv_vol.index)))
        put_oi = piv_oi.get("Put", piv_oi.get("賣權", pd.Series(0.0, index=piv_oi.index)))
        call_oi = piv_oi.get("Call", piv_oi.get("買權", pd.Series(0.0, index=piv_oi.index)))
        put_close = piv_close.get("Put", piv_close.get("賣權", pd.Series(np.nan, index=piv_close.index)))
        call_close = piv_close.get("Call", piv_close.get("買權", pd.Series(np.nan, index=piv_close.index)))
        pcr_vol = put_vol / call_vol.replace(0.0, np.nan)
        pcr_oi = put_oi / call_oi.replace(0.0, np.nan)
        put_call_premium = put_close / call_close.replace(0.0, np.nan)
        out["txo_pcr_volume_z20"] = _zscore(pcr_vol.shift(1), 20).reindex(index)
        out["txo_pcr_oi_z20"] = _zscore(pcr_oi.shift(1), 20).reindex(index)
        out["txo_put_call_premium_z20"] = _zscore(put_call_premium.shift(1), 20).reindex(index)

    if not fut.empty:
        fut["dt"] = pd.to_datetime(fut["dt"])
        # Pick the most liquid ordinary TX contract per day as a front-month proxy.
        front = (
            fut.sort_values(["dt", "volume", "open_interest"], ascending=[True, False, False])
            .drop_duplicates("dt")
            .set_index("dt")
            .sort_index()
        )
        out["tx_front_pct_change_z20"] = _zscore(front["pct_change"].shift(1), 20).reindex(index)
        out["tx_front_volume_z20"] = _zscore(front["volume"].shift(1), 20).reindex(index)
        out["tx_front_oi_chg_z20"] = _zscore(front["open_interest"].diff().shift(1), 20).reindex(index)

    vix = _load_external_close(db_path, "^VIX", index)
    if vix.notna().any():
        out["vix_level_z60"] = _zscore(vix, 60)
        out["vix_chg5_z60"] = _zscore(vix.diff(5), 60)
    return out.ffill()


def _log_r2(actual: pd.Series, forecast: pd.Series) -> float:
    y = np.log(actual.clip(lower=1e-12))
    yhat = np.log(forecast.clip(lower=1e-12))
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def _metrics(actual: pd.Series, forecast: pd.Series, benchmark: pd.Series) -> dict[str, Any]:
    valid = actual.notna() & forecast.notna() & benchmark.notna()
    n = int(valid.sum())
    if n < 30:
        return {"status": "insufficient_data", "n": n}
    forecast_loss = qlike_loss(actual[valid], forecast[valid])
    benchmark_loss = qlike_loss(actual[valid], benchmark[valid])
    forecast_mean = float(forecast_loss.mean())
    benchmark_mean = float(benchmark_loss.mean())
    mse = float(((actual[valid] - forecast[valid]) ** 2).mean())
    benchmark_mse = float(((actual[valid] - benchmark[valid]) ** 2).mean())
    return {
        "status": "available",
        "n": n,
        "qlike_mean": forecast_mean,
        "benchmark_qlike_mean": benchmark_mean,
        "qlike_improvement_pct": (benchmark_mean - forecast_mean) / benchmark_mean * 100.0
        if benchmark_mean
        else None,
        "mse": mse,
        "benchmark_mse": benchmark_mse,
        "mse_improvement_pct": (benchmark_mse - mse) / benchmark_mse * 100.0 if benchmark_mse else None,
        "win_rate_vs_benchmark": float((forecast_loss.to_numpy() < benchmark_loss.to_numpy()).mean()),
        "r2_log_variance": _log_r2(actual[valid], forecast[valid]),
        "benchmark_r2_log_variance": _log_r2(actual[valid], benchmark[valid]),
    }


def evaluate(
    ticker: str,
    start: str,
    end: str,
    *,
    rolling_window: int | None,
    n_regimes: int,
    use_augmented_features: bool = False,
) -> dict[str, Any]:
    ohlc = _load_ohlc(DB_PATH, ticker, start, end)
    gk_variance = garman_klass_variance(ohlc)
    extra_features = _load_taifex_augmented_features(DB_PATH, ohlc.index) if use_augmented_features else None
    results: dict[str, Any] = {}
    for h in HORIZONS:
        regime_frame = coefficient_regime_forecast(
            ohlc,
            horizon=h,
            rolling_window=rolling_window,
            n_regimes=n_regimes,
            extra_features=extra_features,
        )
        regime_forecast = regime_frame[f"regime_switch_forecast_vol_h{h}"]
        har_forecast = har_rv_walkforward_forecast(gk_variance, horizon=h, rolling_window=rolling_window)
        naive_forecast = naive_persistence_forecast(gk_variance, horizon=h)
        actual = _future_avg_variance(gk_variance, h)
        results[str(h)] = {
            "regime_vs_naive": _metrics(actual, regime_forecast, naive_forecast),
            "regime_vs_har_rv": _metrics(actual, regime_forecast, har_forecast),
            "har_rv_vs_naive": _metrics(actual, har_forecast, naive_forecast),
        }
    return {
        "ticker": ticker,
        "window": {"start": start, "end": end, "rows": int(len(ohlc))},
        "policy": "research_only_no_weight_change",
        "outputs_target_weights": False,
        "outputs_execution_regime": False,
        "rolling_window": rolling_window,
        "n_regimes": n_regimes,
        "use_augmented_features": bool(use_augmented_features),
        "augmented_feature_columns": list(extra_features.columns) if extra_features is not None else [],
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="0050.TW")
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="2026-08-07")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--rolling-window", type=int, default=504)
    parser.add_argument("--n-regimes", type=int, default=2)
    parser.add_argument("--use-augmented-features", action="store_true")
    args = parser.parse_args()

    payload = evaluate(
        args.ticker,
        args.start,
        args.end,
        rolling_window=args.rolling_window,
        n_regimes=args.n_regimes,
        use_augmented_features=args.use_augmented_features,
    )
    for h, result in payload["results"].items():
        naive = result["regime_vs_naive"]
        har = result["regime_vs_har_rv"]
        if naive.get("status") != "available" or har.get("status") != "available":
            print(f"h={h}: insufficient data")
            continue
        print(
            f"h={h}: n={naive['n']} regime_vs_naive_QLIKE={naive['qlike_improvement_pct']:.2f}% "
            f"regime_vs_HAR_QLIKE={har['qlike_improvement_pct']:.2f}% "
            f"win_vs_HAR={har['win_rate_vs_benchmark']:.3f}"
        )

    output = Path(args.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
