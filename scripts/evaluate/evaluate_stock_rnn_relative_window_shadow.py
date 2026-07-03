#!/usr/bin/env python3
"""Research-only stock-rnn relative-window shadow benchmark for Group A+.

This imports the useful idea from stock-rnn-master: normalize each lookback
window relative to its own starting price, then test whether that sequence
representation improves H20 direction ranking.  It does not change live
allocation logic.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.paths import PROJECT_ROOT
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_PANEL = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260630.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "stock_rnn_relative_window_shadow_latest_20260630.json"


def load_panel(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "date" not in frame.columns:
        raise ValueError("NCF panel is missing date column")
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date").set_index("date")
    if "is_live" in frame.columns:
        frame = frame[~frame["is_live"].astype(bool)]
    for required in ("forward_gain_h20", "prob_up_h20"):
        if required not in frame.columns:
            raise ValueError(f"NCF panel is missing {required}")
    return frame


def load_close_prices(db_path: Path, tickers: list[str], start: str, end: str) -> pd.DataFrame:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {tickers} between {start} and {end}")
    prices = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    prices.index = pd.to_datetime(prices.index)
    return prices.astype(float)


def load_ohlcv_panel(db_path: Path, tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, open, high, low, close, volume
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {tickers} between {start} and {end}")
    rows["dt"] = pd.to_datetime(rows["dt"])
    return {
        field: rows.pivot(index="dt", columns="ticker", values=field).sort_index().astype(float)
        for field in ("open", "high", "low", "close", "volume")
    }


def build_relative_window_features(
    panel: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    lookback: int = 30,
    tickers: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.Series]:
    if lookback < 2:
        raise ValueError("lookback must be at least 2")
    tickers = tickers or list(TICKERS)
    target = (panel["forward_gain_h20"].astype(float) > 0.0).astype(int)

    joined = panel[["prob_up_h20"]].join(prices[tickers], how="inner")
    feature_rows: list[dict[str, float]] = []
    feature_index: list[pd.Timestamp] = []

    for dt in joined.index:
        loc = prices.index.searchsorted(dt)
        if loc >= len(prices.index) or prices.index[loc] != dt:
            continue
        window = prices.iloc[loc - lookback + 1 : loc + 1][tickers]
        if len(window) != lookback or window.isna().any().any():
            continue
        row: dict[str, float] = {"prob_up_h20": float(panel.loc[dt, "prob_up_h20"])}
        for ticker in tickers:
            series = window[ticker].astype(float)
            base = float(series.iloc[0])
            if base <= 0.0:
                continue
            normalized = series / base - 1.0
            returns = series.pct_change().dropna()
            for offset, value in enumerate(normalized.to_numpy(dtype=float)):
                row[f"{ticker}_rel_{offset:02d}"] = float(value)
            row[f"{ticker}_window_return"] = float(series.iloc[-1] / base - 1.0)
            row[f"{ticker}_return_mean"] = float(returns.mean())
            row[f"{ticker}_return_vol"] = float(returns.std(ddof=1))
            row[f"{ticker}_return_min"] = float(returns.min())
            row[f"{ticker}_return_max"] = float(returns.max())
        if len(row) == 1 + len(tickers) * (lookback + 5):
            feature_rows.append(row)
            feature_index.append(pd.Timestamp(dt))

    features = pd.DataFrame(feature_rows, index=pd.DatetimeIndex(feature_index))
    valid_index = features.index.intersection(target.index)
    features = features.loc[valid_index].replace([np.inf, -np.inf], np.nan).dropna()
    target = target.loc[features.index]
    return features.astype(float), target.astype(int)


def build_ohlcv_relative_window_features(
    panel: pd.DataFrame,
    ohlcv: dict[str, pd.DataFrame],
    *,
    lookback: int = 30,
    tickers: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.Series]:
    if lookback < 2:
        raise ValueError("lookback must be at least 2")
    tickers = tickers or list(TICKERS)
    for field in ("open", "high", "low", "close", "volume"):
        if field not in ohlcv:
            raise ValueError(f"OHLCV panel is missing {field}")

    close = ohlcv["close"][tickers]
    target = (panel["forward_gain_h20"].astype(float) > 0.0).astype(int)
    joined = panel[["prob_up_h20"]].join(close, how="inner")
    feature_rows: list[dict[str, float]] = []
    feature_index: list[pd.Timestamp] = []

    for dt in joined.index:
        loc = close.index.searchsorted(dt)
        if loc >= len(close.index) or close.index[loc] != dt:
            continue
        close_window = close.iloc[loc - lookback + 1 : loc + 1][tickers]
        if len(close_window) != lookback or close_window.isna().any().any():
            continue
        row: dict[str, float] = {"prob_up_h20": float(panel.loc[dt, "prob_up_h20"])}

        for ticker in tickers:
            c = close_window[ticker].astype(float)
            base = float(c.iloc[0])
            if base <= 0.0:
                continue
            ret = c.pct_change().dropna()
            rel_close = c / base - 1.0
            for offset, value in enumerate(rel_close.to_numpy(dtype=float)):
                row[f"{ticker}_close_rel_{offset:02d}"] = float(value)

            high = ohlcv["high"].iloc[loc - lookback + 1 : loc + 1][ticker].astype(float)
            low = ohlcv["low"].iloc[loc - lookback + 1 : loc + 1][ticker].astype(float)
            open_ = ohlcv["open"].iloc[loc - lookback + 1 : loc + 1][ticker].astype(float)
            volume = ohlcv["volume"].iloc[loc - lookback + 1 : loc + 1][ticker].astype(float)
            if high.isna().any() or low.isna().any() or open_.isna().any() or volume.isna().any():
                continue

            rel_range = (high - low) / c.replace(0.0, np.nan)
            rel_gap = open_ / c.shift(1) - 1.0
            volume_base = float(volume.iloc[0])
            rel_volume = volume / volume_base - 1.0 if volume_base > 0.0 else pd.Series(np.nan, index=volume.index)

            for offset, value in enumerate(rel_range.fillna(0.0).to_numpy(dtype=float)):
                row[f"{ticker}_range_rel_{offset:02d}"] = float(value)
            for offset, value in enumerate(rel_volume.fillna(0.0).to_numpy(dtype=float)):
                row[f"{ticker}_volume_rel_{offset:02d}"] = float(value)

            row[f"{ticker}_window_return"] = float(c.iloc[-1] / base - 1.0)
            row[f"{ticker}_return_mean"] = float(ret.mean())
            row[f"{ticker}_return_vol"] = float(ret.std(ddof=1))
            row[f"{ticker}_return_min"] = float(ret.min())
            row[f"{ticker}_return_max"] = float(ret.max())
            row[f"{ticker}_range_mean"] = float(rel_range.mean())
            row[f"{ticker}_range_max"] = float(rel_range.max())
            row[f"{ticker}_gap_mean"] = float(rel_gap.dropna().mean())
            row[f"{ticker}_gap_abs_max"] = float(rel_gap.dropna().abs().max())
            row[f"{ticker}_volume_rel_last"] = float(rel_volume.iloc[-1]) if pd.notna(rel_volume.iloc[-1]) else 0.0

        expected_per_ticker = lookback * 3 + 10
        if len(row) == 1 + len(tickers) * expected_per_ticker:
            feature_rows.append(row)
            feature_index.append(pd.Timestamp(dt))

    features = pd.DataFrame(feature_rows, index=pd.DatetimeIndex(feature_index))
    valid_index = features.index.intersection(target.index)
    features = features.loc[valid_index].replace([np.inf, -np.inf], np.nan).dropna()
    target = target.loc[features.index]
    return features.astype(float), target.astype(int)


def _auc_or_none(y_true: pd.Series | np.ndarray, proba: np.ndarray) -> float | None:
    values = np.asarray(y_true)
    if len(np.unique(values)) < 2:
        return None
    return float(roc_auc_score(values, proba))


def _brier_or_none(y_true: pd.Series | np.ndarray, proba: np.ndarray) -> float | None:
    values = np.asarray(y_true)
    if len(values) == 0:
        return None
    return float(brier_score_loss(values, proba))


def _delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return float(value - baseline)


def evaluate_models(
    features: pd.DataFrame,
    target: pd.Series,
    *,
    n_splits: int,
    gap: int,
    include_baseline_feature: bool = False,
) -> dict[str, Any]:
    if len(features) < n_splits + 10:
        raise ValueError("Not enough rows for requested TimeSeriesSplit")

    models = {
        "relative_window_logistic": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=3000, class_weight="balanced", random_state=42),
        ),
        "relative_window_hgb": HistGradientBoostingClassifier(
            max_iter=160,
            learning_rate=0.035,
            max_leaf_nodes=15,
            l2_regularization=0.08,
            random_state=42,
        ),
    }
    split = TimeSeriesSplit(n_splits=n_splits, gap=gap)
    baseline_probs: list[float] = []
    baseline_truth: list[int] = []
    model_probs = {name: [] for name in models}
    model_truth = {name: [] for name in models}
    folds: list[dict[str, Any]] = []

    for fold, (train_idx, test_idx) in enumerate(split.split(features), start=1):
        x_train = features.iloc[train_idx]
        y_train = target.iloc[train_idx]
        x_test = features.iloc[test_idx]
        y_test = target.iloc[test_idx]
        baseline = x_test["prob_up_h20"].clip(0.0, 1.0).to_numpy(dtype=float)
        baseline_probs.extend(baseline.tolist())
        baseline_truth.extend(y_test.tolist())

        row: dict[str, Any] = {
            "fold": fold,
            "train_start": str(x_train.index[0].date()),
            "train_end": str(x_train.index[-1].date()),
            "test_start": str(x_test.index[0].date()),
            "test_end": str(x_test.index[-1].date()),
            "train_rows": int(len(x_train)),
            "test_rows": int(len(x_test)),
            "positive_rate_test": float(y_test.mean()),
            "baseline_auc": _auc_or_none(y_test, baseline),
            "baseline_brier": _brier_or_none(y_test, baseline),
        }
        train_cols = list(features.columns) if include_baseline_feature else [col for col in features.columns if col != "prob_up_h20"]
        for name, model in models.items():
            model.fit(x_train[train_cols], y_train)
            proba = model.predict_proba(x_test[train_cols])[:, 1]
            model_probs[name].extend(proba.tolist())
            model_truth[name].extend(y_test.tolist())
            row[f"{name}_auc"] = _auc_or_none(y_test, proba)
            row[f"{name}_brier"] = _brier_or_none(y_test, proba)
        folds.append(row)

    baseline_auc = _auc_or_none(baseline_truth, np.asarray(baseline_probs))
    baseline_brier = _brier_or_none(baseline_truth, np.asarray(baseline_probs))
    aggregate: dict[str, Any] = {
        "baseline": {
            "feature": "prob_up_h20",
            "auc": baseline_auc,
            "brier": baseline_brier,
            "included_in_shadow_models": bool(include_baseline_feature),
        }
    }
    for name in models:
        proba = np.asarray(model_probs[name], dtype=float)
        truth = np.asarray(model_truth[name], dtype=int)
        auc = _auc_or_none(truth, proba)
        brier = _brier_or_none(truth, proba)
        aggregate[name] = {
            "auc": auc,
            "brier": brier,
            "auc_delta_vs_baseline": _delta(auc, baseline_auc),
            "brier_delta_vs_baseline": _delta(brier, baseline_brier),
        }
    best_name = max(models, key=lambda name: aggregate[name]["auc"] or float("-inf"))
    aggregate["best_shadow_model"] = best_name
    aggregate["promotion_decision"] = (
        "candidate_for_deeper_ablation"
        if (aggregate[best_name]["auc_delta_vs_baseline"] is not None and aggregate[best_name]["auc_delta_vs_baseline"] >= 0.02)
        else "research_only"
    )
    return {"folds": folds, "aggregate": aggregate}


def build_report(
    *,
    panel_path: Path,
    db_path: Path,
    start: str,
    end: str,
    lookback: int,
    n_splits: int,
    gap: int,
    feature_set: str,
    include_baseline_feature: bool,
) -> dict[str, Any]:
    panel = load_panel(panel_path)
    if feature_set == "close":
        prices = load_close_prices(db_path, list(TICKERS), start, end)
        features, target = build_relative_window_features(panel, prices, lookback=lookback, tickers=list(TICKERS))
        actual_start = str(prices.index[0].date())
        actual_end = str(prices.index[-1].date())
        price_rows = int(len(prices))
    elif feature_set == "ohlcv":
        ohlcv = load_ohlcv_panel(db_path, list(TICKERS), start, end)
        features, target = build_ohlcv_relative_window_features(panel, ohlcv, lookback=lookback, tickers=list(TICKERS))
        actual_start = str(ohlcv["close"].index[0].date())
        actual_end = str(ohlcv["close"].index[-1].date())
        price_rows = int(len(ohlcv["close"]))
    else:
        raise ValueError(f"Unsupported feature_set: {feature_set}")
    evaluation = evaluate_models(
        features,
        target,
        n_splits=n_splits,
        gap=gap,
        include_baseline_feature=include_baseline_feature,
    )
    return {
        "schema_version": 1,
        "report_type": "stock_rnn_relative_window_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "stock_rnn_source": "C:\\Users\\isaac\\Downloads\\stock-rnn-master\\stock-rnn-master",
            "panel": str(panel_path),
            "db_path": str(db_path),
            "price_window": {
                "requested_start": start,
                "requested_end": end,
                "actual_start": actual_start,
                "actual_end": actual_end,
                "price_rows": price_rows,
            },
            "feature_set": feature_set,
            "include_baseline_feature": bool(include_baseline_feature),
            "lookback_days": int(lookback),
            "feature_rows": int(len(features)),
            "feature_count": int(features.shape[1]),
            "target": "forward_gain_h20 > 0",
            "tickers": list(TICKERS),
        },
        "evaluation": evaluation,
        "method_note": (
            "Research-only import of stock-rnn's relative lookback-window normalization. "
            "Each ETF sequence is normalized to its own window start; models are "
            "evaluated with TimeSeriesSplit and do not affect live allocation."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-30")
    parser.add_argument("--lookback", type=int, default=30)
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--gap", type=int, default=5)
    parser.add_argument("--feature-set", choices=["close", "ohlcv"], default="close")
    parser.add_argument("--include-baseline-feature", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    std = OutputStandardizer("evaluate_stock_rnn_relative_window_shadow")
    try:
        report = build_report(
            panel_path=Path(args.panel),
            db_path=Path(args.db),
            start=args.start,
            end=args.end,
            lookback=args.lookback,
            n_splits=args.n_splits,
            gap=args.gap,
            feature_set=args.feature_set,
            include_baseline_feature=args.include_baseline_feature,
        )
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"stock-rnn relative-window shadow: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
