#!/usr/bin/env python3
"""Walk-forward classifier for the "race" downside label (2026-07-10).

Label (user-specified): within the next 10 trading days, does 00631L.TW
touch -8% before it touches +12%? This is label B from
evaluate_group_a_plus_00631l_downside_oracle_ceiling.py, which showed the
best oracle-ceiling Sharpe improvement of the three downside-specific labels
tested (vs. the symmetric HAR-RV volatility forecast, which showed no
ceiling worth pursuing).

This script trains a REAL (non-lookahead) walk-forward classifier -- not an
oracle -- using only price-derived features available at time t, and
reports out-of-sample AUC/precision/recall plus what fraction of the oracle
ceiling a realistic model captures when wired into the same de-risk rule.

Research-only. Does not touch any live signal or target weight.
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
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _metrics
from group_a_plus.integrations.volatility_forecast import build_multi_horizon_forecast
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_00631l_downside_race_classifier_latest.json"

HORIZON = 10
RACE_DOWN_THRESHOLD = -0.08
RACE_UP_THRESHOLD = 0.12
TRAIN_WINDOW = 504
REFIT_EVERY = 21
MIN_TRAIN_ROWS = 252
DECISION_THRESHOLD = 0.5

DEFAULT_WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31"),
    ("inflation_2022", "2022-01-03", "2022-12-30"),
    ("live_2024_2026", "2024-01-02", "latest"),
    ("active_2025_2026", "2025-01-02", "latest"),
]

FEATURE_COLUMNS = [
    "ma_gap_20",
    "ma_gap_60",
    "drawdown_0050",
    "return_0050_5d",
    "return_0050_10d",
    "return_0050_20d",
    "return_0050_60d",
    "return_00631l_5d",
    "return_00631l_10d",
    "realized_vol_ratio_20_60",
    "downside_semivar_20d",
    "up_day_fraction_14d",
    "forecast_vol_h10",
    "forecast_vol_h10_ratio",
    "forecast_vol_h10_percentile",
]

CHIP_FEATURE_COLUMNS = [
    "inst_0050_5d",
    "foreign_0050_5d",
    "margin_0050_balance_chg_5d",
    "market_margin_balance_chg_5d",
    "tdcc_0050_minority_chg_1w",
    "tdcc_0050_major_chg_1w",
    "foreign_shareholding_0050_ratio_chg_5d",
    "short_0050_margin_balance_chg_5d",
    "short_0050_sbl_balance_chg_5d",
    "securities_lending_0050_volume_5d",
    "day_trade_0050_volume_5d",
    "dealer_tx_volume_5d",
    "dealer_txo_volume_5d",
    "tx_foreign_net_oi",
    "tx_foreign_net_oi_chg_5d",
    "txo_foreign_call_net_oi",
    "txo_foreign_put_net_oi",
    "txo_foreign_put_call_net_oi",
    "txo_foreign_put_call_net_oi_chg_5d",
]


def _load_ohlc(db_path: Path, ticker: str, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt, open, high, low, close FROM ohlcv WHERE ticker = ? AND dt BETWEEN ? AND ? ORDER BY dt",
            [ticker, start, end],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")


def _build_features(
    ohlc_0050: pd.DataFrame, ohlc_631l: pd.DataFrame, chip_features: pd.DataFrame | None = None
) -> pd.DataFrame:
    close = ohlc_0050["close"].astype(float)
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    peak = close.cummax()
    daily_ret = close.pct_change().fillna(0.0)
    realized_vol_20 = daily_ret.rolling(20).std()
    realized_vol_60 = daily_ret.rolling(60).std()
    downside_sq_20 = (daily_ret.clip(upper=0.0) ** 2).rolling(20).mean()
    up_day_frac_14 = (daily_ret > 0).rolling(14).mean()
    close_631l = ohlc_631l["close"].astype(float).reindex(close.index)

    vol_forecast = build_multi_horizon_forecast(ohlc_0050, horizons=(10,))

    feat = pd.DataFrame(index=close.index)
    feat["ma_gap_20"] = close / ma20 - 1.0
    feat["ma_gap_60"] = close / ma60 - 1.0
    feat["drawdown_0050"] = close / peak - 1.0
    feat["return_0050_5d"] = close.pct_change(5)
    feat["return_0050_10d"] = close.pct_change(10)
    feat["return_0050_20d"] = close.pct_change(20)
    feat["return_0050_60d"] = close.pct_change(60)
    feat["return_00631l_5d"] = close_631l.pct_change(5)
    feat["return_00631l_10d"] = close_631l.pct_change(10)
    feat["realized_vol_ratio_20_60"] = (realized_vol_20 / realized_vol_60.replace(0.0, np.nan)).fillna(1.0)
    feat["downside_semivar_20d"] = downside_sq_20
    feat["up_day_fraction_14d"] = up_day_frac_14
    feat["forecast_vol_h10"] = vol_forecast["forecast_vol_h10"]
    feat["forecast_vol_h10_ratio"] = vol_forecast["forecast_vol_h10_ratio"]
    feat["forecast_vol_h10_percentile"] = vol_forecast["forecast_vol_h10_percentile"]
    if chip_features is not None:
        for col in CHIP_FEATURE_COLUMNS:
            feat[col] = chip_features.reindex(feat.index)[col] if col in chip_features.columns else 0.0
    return feat


def _future_paths(close: pd.Series, horizon: int) -> pd.DataFrame:
    return pd.DataFrame({i: close.shift(-i) / close - 1.0 for i in range(1, horizon + 1)}, index=close.index)


def _race_label(close_631l: pd.Series, horizon: int, down_thr: float, up_thr: float) -> pd.Series:
    future = _future_paths(close_631l, horizon)

    def _row(row: pd.Series) -> float:
        if row.isna().any():
            return np.nan
        down_hits = np.where(row.to_numpy() <= down_thr)[0]
        up_hits = np.where(row.to_numpy() >= up_thr)[0]
        down_day = down_hits[0] if len(down_hits) else None
        up_day = up_hits[0] if len(up_hits) else None
        if down_day is None:
            return 0.0
        if up_day is None:
            return 1.0
        return 1.0 if down_day < up_day else 0.0

    return future.apply(_row, axis=1)


def _walkforward_predict(
    features: pd.DataFrame,
    label: pd.Series,
    *,
    train_window: int,
    refit_every: int,
    min_train_rows: int,
    horizon: int,
    n_estimators: int = 100,
    max_depth: int = 2,
    learning_rate: float = 0.05,
) -> pd.Series:
    valid_features = features.notna().all(axis=1)
    pred = pd.Series(np.nan, index=features.index, dtype=float)
    model = None
    last_fit_idx = -1
    feat_arr = features.to_numpy(dtype=float)
    label_arr = label.to_numpy(dtype=float)

    for i in range(len(features)):
        if not valid_features.iloc[i]:
            continue
        train_end = i - horizon  # last row whose label is fully known by day i
        if train_end < min_train_rows:
            continue
        if model is None or (i - last_fit_idx) >= refit_every:
            train_start = max(0, train_end + 1 - train_window)
            train_slice = slice(train_start, train_end + 1)
            valid_slice = valid_features.iloc[train_slice].to_numpy() & ~np.isnan(label_arr[train_slice])
            x = feat_arr[train_slice][valid_slice]
            y = label_arr[train_slice][valid_slice]
            if len(y) < min_train_rows or len(np.unique(y)) < 2:
                continue
            model = GradientBoostingClassifier(
                n_estimators=n_estimators, max_depth=max_depth, learning_rate=learning_rate, random_state=7
            )
            model.fit(x, y)
            last_fit_idx = i
        pred.iloc[i] = float(model.predict_proba(feat_arr[i : i + 1])[0, 1])

    return pred


def _rolling_quantile_flag(pred_proba: pd.Series, window: int, level: float) -> pd.Series:
    """Adaptive, regime-relative trigger: flag day i if its predicted probability is in
    the top (1-level) fraction of the trailing `window`-day distribution of predictions
    up to and including day i. No lookahead -- only uses predictions already known at i.
    """
    threshold = pred_proba.rolling(window, min_periods=max(20, window // 4)).quantile(level)
    return (pred_proba >= threshold).fillna(False)


def _weights_scaled(golden_weights: dict[str, float], fraction: float) -> dict[str, float]:
    """Shift `fraction` of the 00631L.TW weight into 0050.TW. fraction=1.0 is the old
    all-or-nothing de-risk; fraction=0.0 is unchanged golden1 weights; values in between
    give a graduated (partial) de-risk.
    """
    weights = dict(golden_weights)
    base_631l = float(weights.get("00631L.TW", 0.0) or 0.0)
    shift = base_631l * fraction
    weights["00631L.TW"] = base_631l - shift
    weights["0050.TW"] = float(weights.get("0050.TW", 0.0) or 0.0) + shift
    return _normalize(weights)


def _graduated_fraction(pred_proba: pd.Series, low_th: float, high_th: float) -> pd.Series:
    """Map predicted probability linearly to a [0,1] de-risk fraction: <=low_th -> 0,
    >=high_th -> 1, linear in between. No lookahead -- pointwise transform of pred_proba.
    """
    span = max(high_th - low_th, 1e-9)
    frac = (pred_proba - low_th) / span
    return frac.clip(lower=0.0, upper=1.0).fillna(0.0)


def _simulate_scaled_curve(
    prices: pd.DataFrame,
    execution_regime: pd.Series,
    derisk_fraction: pd.Series,
    golden_weights: dict[str, float],
    weights_by_regime: dict[str, dict[str, float]],
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    buckets: int = 1,
) -> tuple[pd.Series, dict[str, float]]:
    shares = {t: 0.0 for t in TICKERS}
    cash = float(initial_value)
    applied_key: str | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0
    frac_sum = 0.0
    frac_days = 0
    frac_gt0_days = 0

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[t] * float(price_row[t]) for t in TICKERS)
        regime = str(execution_regime.loc[dt])
        if regime == "golden1":
            frac = float(derisk_fraction.loc[dt]) if dt in derisk_fraction.index and pd.notna(derisk_fraction.loc[dt]) else 0.0
            frac = min(max(frac, 0.0), 1.0)
            if buckets and buckets > 0:
                frac = round(frac * buckets) / buckets
            frac_sum += frac
            frac_days += 1
            if frac > 0:
                frac_gt0_days += 1
            key = f"golden1_derisk_{frac:.4f}"
            target_weights = _weights_scaled(golden_weights, frac)
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
        "avg_derisk_fraction_golden1": float(frac_sum / frac_days) if frac_days else 0.0,
        "days_with_derisk_gt0_golden1": int(frac_gt0_days),
    }


def _resolve_end_date(db_path: Path, requested_end: str, ticker: str = "0050.TW") -> str:
    if str(requested_end).lower() != "latest":
        return requested_end
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        max_dt = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()[0]
    finally:
        con.close()
    return pd.Timestamp(max_dt).strftime("%Y-%m-%d")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--ncf-panel-631l", default="results/ncf_00631l_panel_latest_20260707.csv")
    parser.add_argument("--feature-start", default="2016-01-04")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--decision-threshold", type=float, default=DECISION_THRESHOLD)
    parser.add_argument("--use-chip-features", action="store_true")
    parser.add_argument("--threshold-mode", choices=["fixed", "rolling_quantile"], default="fixed")
    parser.add_argument("--rolling-quantile-window", type=int, default=252)
    parser.add_argument("--rolling-quantile-level", type=float, default=0.9)
    parser.add_argument("--derisk-mode", choices=["binary", "graduated"], default="binary")
    parser.add_argument("--graduated-low-threshold", type=float, default=0.4)
    parser.add_argument("--graduated-high-threshold", type=float, default=0.8)
    parser.add_argument("--graduated-buckets", type=int, default=4)
    parser.add_argument("--horizon", type=int, default=HORIZON)
    parser.add_argument("--race-down-threshold", type=float, default=RACE_DOWN_THRESHOLD)
    parser.add_argument("--race-up-threshold", type=float, default=RACE_UP_THRESHOLD)
    parser.add_argument("--n-estimators", type=int, default=100)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    overall_end = _resolve_end_date(db_path, "latest")

    ohlc_0050 = _load_ohlc(db_path, "0050.TW", args.feature_start, overall_end)
    ohlc_631l = _load_ohlc(db_path, "00631L.TW", args.feature_start, overall_end)
    chip_features = None
    if args.use_chip_features:
        chip_features = _load_chip_features(db_path, ohlc_0050.index, args.feature_start, overall_end)
    all_feature_columns = FEATURE_COLUMNS + (CHIP_FEATURE_COLUMNS if args.use_chip_features else [])
    features = _build_features(ohlc_0050, ohlc_631l, chip_features)[all_feature_columns]
    label = _race_label(
        ohlc_631l["close"].astype(float), args.horizon, args.race_down_threshold, args.race_up_threshold
    )

    pred_proba = _walkforward_predict(
        features, label,
        train_window=TRAIN_WINDOW, refit_every=REFIT_EVERY, min_train_rows=MIN_TRAIN_ROWS, horizon=args.horizon,
        n_estimators=args.n_estimators, max_depth=args.max_depth, learning_rate=args.learning_rate,
    )
    if args.derisk_mode == "graduated":
        derisk_fraction_series = _graduated_fraction(
            pred_proba, args.graduated_low_threshold, args.graduated_high_threshold
        )
        sim_buckets = args.graduated_buckets
    elif args.threshold_mode == "rolling_quantile":
        derisk_fraction_series = _rolling_quantile_flag(
            pred_proba, args.rolling_quantile_window, args.rolling_quantile_level
        ).astype(float)
        sim_buckets = 1
    else:
        derisk_fraction_series = (pred_proba >= args.decision_threshold).fillna(False).astype(float)
        sim_buckets = 1

    results = []
    for win_label, start, end in DEFAULT_WINDOWS:
        end_resolved = _resolve_end_date(db_path, end)
        report, frame = run_a2118(
            start=start, end=end_resolved, initial_value=args.initial_value, db=db_path,
            commission_rate=args.commission_rate, slippage_rate=args.slippage_rate,
            equity_etf_sell_tax=args.equity_etf_sell_tax, ncf_panel_631l_path=args.ncf_panel_631l,
            h20_max=0.33, conf_min=0.55, h5_reentry_min=0.55,
            chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
            risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
            momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
            momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        )
        prices = _load_prices(db_path, list(TICKERS), start, end_resolved)
        total_return_prices, _ = _load_total_return_prices(db_path, prices.index)
        execution_regime = frame["execution_regime"].astype(str)
        golden_weights = dict(report["base_weights"]["golden1"])
        weights_by_regime = dict(report["base_weights"])
        baseline_metrics = dict(report["metrics"])
        baseline_execution = dict(report["execution"])

        win_pred = pred_proba.reindex(frame.index)
        win_race_label = label.reindex(frame.index)
        valid_oos = win_pred.notna() & win_race_label.notna()
        auc = None
        if valid_oos.sum() > 20 and win_race_label[valid_oos].nunique() > 1:
            auc = float(roc_auc_score(win_race_label[valid_oos], win_pred[valid_oos]))

        win_frac = derisk_fraction_series.reindex(frame.index).fillna(0.0)
        curve, sim = _simulate_scaled_curve(
            total_return_prices, execution_regime, win_frac, golden_weights,
            weights_by_regime, args.initial_value, args.commission_rate, args.slippage_rate, args.equity_etf_sell_tax,
            buckets=sim_buckets,
        )
        metrics = _metrics(curve, args.initial_value)
        golden_mask = execution_regime == "golden1"

        result = {
            "label": win_label,
            "window": {"start": start, "end": end_resolved},
            "auc_oos": auc,
            "derisk_days_within_golden1": sim["days_with_derisk_gt0_golden1"],
            "avg_derisk_fraction_golden1": sim["avg_derisk_fraction_golden1"],
            "golden1_days": int(golden_mask.sum()),
            "delta_vs_baseline": {
                "final_value": metrics["final_value"] - baseline_metrics["final_value"],
                "sharpe_ratio": metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"],
                "max_drawdown": metrics["max_drawdown"] - baseline_metrics["max_drawdown"],
            },
            "extra_transaction_cost": float(sim["transaction_cost"] - baseline_execution.get("transaction_cost", 0.0)),
        }
        results.append(result)
        d = result["delta_vs_baseline"]
        print(
            f"{start}..{end_resolved}: AUC={auc} derisk_days={result['derisk_days_within_golden1']}/{result['golden1_days']} "
            f"avg_frac={result['avg_derisk_fraction_golden1']:.3f} "
            f"delta_final={d['final_value']:.1f} delta_sharpe={d['sharpe_ratio']:.4f} delta_mdd={d['max_drawdown']:.4f}"
        )

    payload = {
        "experiment": "group_a_plus_00631l_downside_race_classifier",
        "policy": "research_only_walkforward_no_lookahead",
        "label_definition": {
            "horizon_days": args.horizon,
            "race_down_threshold": args.race_down_threshold,
            "race_up_threshold": args.race_up_threshold,
        },
        "model": {
            "type": "GradientBoostingClassifier",
            "features": all_feature_columns,
            "use_chip_features": args.use_chip_features,
            "train_window": TRAIN_WINDOW,
            "refit_every": REFIT_EVERY,
            "n_estimators": args.n_estimators,
            "max_depth": args.max_depth,
            "learning_rate": args.learning_rate,
            "threshold_mode": args.threshold_mode,
            "decision_threshold": args.decision_threshold if args.threshold_mode == "fixed" else None,
            "rolling_quantile_window": args.rolling_quantile_window if args.threshold_mode == "rolling_quantile" else None,
            "rolling_quantile_level": args.rolling_quantile_level if args.threshold_mode == "rolling_quantile" else None,
            "derisk_mode": args.derisk_mode,
            "graduated_low_threshold": args.graduated_low_threshold if args.derisk_mode == "graduated" else None,
            "graduated_high_threshold": args.graduated_high_threshold if args.derisk_mode == "graduated" else None,
            "graduated_buckets": args.graduated_buckets if args.derisk_mode == "graduated" else None,
        },
        "windows": results,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
