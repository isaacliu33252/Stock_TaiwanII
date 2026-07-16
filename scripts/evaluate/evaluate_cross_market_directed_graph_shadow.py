#!/usr/bin/env python3
"""Research-only directed cross-market graph shadow for GroupA+.

The timing convention is deliberately strict: for each Taiwan trading date d,
source-market features use the latest source close with source_dt < d. The
resulting graph is a sparse feature-selection layer for REENTER/NO_ADD
classification, not a live allocation rule.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "cross_market_directed_graph_shadow_latest.json"
DEFAULT_SOURCE_TICKERS = ("TSM", "SOXX", "QQQ", "TWD=X", "NVDA", "AMD", "AVGO", "ASML", "^TNX")
DEFAULT_TARGET_TICKERS = ("2330.TW", "0050.TW", "00631L.TW", "2454.TW", "2317.TW", "2308.TW", "2382.TW")
RETURN_WINDOWS = (1, 3, 5)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _table_columns(con: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    try:
        rows = con.execute(f"DESCRIBE {table}").fetchall()
    except Exception:
        return set()
    return {str(row[0]) for row in rows}


def _load_close_table(
    db_path: Path,
    *,
    table: str,
    tickers: tuple[str, ...],
    start: str,
    end: str,
) -> pd.DataFrame:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        columns = _table_columns(con, table)
        if not columns:
            return pd.DataFrame()
        where = f"ticker IN ({placeholders}) AND dt BETWEEN ? AND ?"
        params: list[Any] = [*tickers, start, end]
        if table == "external_market_ohlcv" and "provider" in columns:
            where = f"provider = 'yfinance' AND {where}"
        rows = con.execute(
            f"""
            SELECT ticker, dt, close
            FROM {table}
            WHERE {where}
              AND close IS NOT NULL
            ORDER BY dt, ticker
            """,
            params,
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.DataFrame()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.pivot_table(index="dt", columns="ticker", values="close", aggfunc="last").sort_index()


def load_source_closes(db_path: Path, tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    return _load_close_table(db_path, table="external_market_ohlcv", tickers=tickers, start=start, end=end)


def load_target_closes(db_path: Path, tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    local_tickers = tuple(ticker for ticker in tickers if ticker != "2330.TW")
    external_tickers = tuple(ticker for ticker in tickers if ticker == "2330.TW")
    frames = []
    if local_tickers:
        frames.append(_load_close_table(db_path, table="ohlcv", tickers=local_tickers, start=start, end=end))
    if external_tickers:
        frames.append(_load_close_table(db_path, table="external_market_ohlcv", tickers=external_tickers, start=start, end=end))
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1).sort_index()


def align_source_returns_to_taiwan_dates(
    source_close: pd.DataFrame,
    target_index: pd.DatetimeIndex,
    windows: tuple[int, ...] = RETURN_WINDOWS,
) -> pd.DataFrame:
    features = pd.DataFrame(index=target_index)
    for ticker in source_close.columns:
        close = source_close[ticker].astype(float).dropna()
        for window in windows:
            ret = close.pct_change(window)
            values = []
            for dt in target_index:
                known = ret.loc[ret.index < dt].dropna()
                values.append(float(known.iloc[-1]) if len(known) else np.nan)
            features[f"src_{ticker}_ret{window}d"] = values
    return features


def add_composite_source_features(features: pd.DataFrame) -> pd.DataFrame:
    """Add economically grouped source features after strict date alignment."""

    out = features.copy()
    for window in RETURN_WINDOWS:
        semi_cols = [
            f"src_{ticker}_ret{window}d"
            for ticker in ("TSM", "SOXX", "NVDA", "AMD", "ASML")
            if f"src_{ticker}_ret{window}d" in out
        ]
        if semi_cols:
            out[f"src_US_SEMI_BASKET_ret{window}d"] = out[semi_cols].mean(axis=1)
        if f"src_SOXX_ret{window}d" in out and f"src_QQQ_ret{window}d" in out:
            out[f"src_SOXX_minus_QQQ_ret{window}d"] = out[f"src_SOXX_ret{window}d"] - out[f"src_QQQ_ret{window}d"]
        if f"src_TSM_ret{window}d" in out and f"src_SOXX_ret{window}d" in out:
            out[f"src_TSM_minus_SOXX_ret{window}d"] = out[f"src_TSM_ret{window}d"] - out[f"src_SOXX_ret{window}d"]
        if f"src_NVDA_ret{window}d" in out and f"src_SOXX_ret{window}d" in out:
            out[f"src_NVDA_minus_SOXX_ret{window}d"] = out[f"src_NVDA_ret{window}d"] - out[f"src_SOXX_ret{window}d"]
    return out


def build_target_outcomes(target_close: pd.DataFrame, horizon: int = 5) -> pd.DataFrame:
    out = pd.DataFrame(index=target_close.index)
    if "00631L.TW" in target_close and "0050.TW" in target_close:
        ret_631l = target_close["00631L.TW"].shift(-horizon) / target_close["00631L.TW"] - 1.0
        ret_0050 = target_close["0050.TW"].shift(-horizon) / target_close["0050.TW"] - 1.0
        future_min_631l = pd.concat(
            [target_close["00631L.TW"].shift(-step) for step in range(1, horizon + 1)],
            axis=1,
        ).min(axis=1)
        fwd_mdd_631l = future_min_631l / target_close["00631L.TW"] - 1.0
        valid = ret_631l.notna() & ret_0050.notna() & fwd_mdd_631l.notna()
        out["label_REENTER"] = np.where(
            valid,
            ((ret_631l - ret_0050 >= 0.01) & (fwd_mdd_631l > -0.05)).astype(float),
            np.nan,
        )
        out["label_NO_ADD"] = np.where(
            valid,
            ((ret_631l - ret_0050 <= -0.01) | (fwd_mdd_631l <= -0.05)).astype(float),
            np.nan,
        )
        out["forward_ret_00631l_h5"] = ret_631l
        out["forward_ret_0050_h5"] = ret_0050
        out["forward_mdd_00631l_h5"] = fwd_mdd_631l
    if "0050.TW" in target_close:
        ret_0050_5d_now = target_close["0050.TW"] / target_close["0050.TW"].shift(5) - 1.0
        ret_0050_10d_now = target_close["0050.TW"] / target_close["0050.TW"].shift(10) - 1.0
        dd_0050_60d_now = target_close["0050.TW"] / target_close["0050.TW"].rolling(60, min_periods=20).max() - 1.0
        out["condition_0050_5d_le_minus2pct"] = (ret_0050_5d_now <= -0.02).fillna(False).astype(int)
        out["condition_0050_10d_le_minus3pct"] = (ret_0050_10d_now <= -0.03).fillna(False).astype(int)
        out["condition_0050_60d_drawdown_le_minus5pct"] = (dd_0050_60d_now <= -0.05).fillna(False).astype(int)
        out["condition_0050_5d_abs_ge_2pct"] = (ret_0050_5d_now.abs() >= 0.02).fillna(False).astype(int)
    if "00631L.TW" in target_close:
        ret_631l_5d_now = target_close["00631L.TW"] / target_close["00631L.TW"].shift(5) - 1.0
        out["condition_00631l_5d_le_minus4pct"] = (ret_631l_5d_now <= -0.04).fillna(False).astype(int)
    for ticker in target_close.columns:
        out[f"target_{ticker}_ret1d_fwd"] = target_close[ticker].shift(-1) / target_close[ticker] - 1.0
    return out


def _ols_tstat(x: pd.Series, y: pd.Series) -> tuple[float | None, float | None]:
    frame = pd.concat([x, y], axis=1).dropna()
    if len(frame) < 20:
        return None, None
    xv = frame.iloc[:, 0].astype(float)
    yv = frame.iloc[:, 1].astype(float)
    x_centered = xv - xv.mean()
    ssx = float((x_centered**2).sum())
    if ssx <= 0.0:
        return None, None
    beta = float(((xv - xv.mean()) * (yv - yv.mean())).sum() / ssx)
    alpha = float(yv.mean() - beta * xv.mean())
    resid = yv - (alpha + beta * xv)
    sse = float((resid**2).sum())
    if len(frame) <= 2:
        return beta, None
    se = math.sqrt(max(sse / (len(frame) - 2), 0.0) / ssx)
    if se <= 0.0:
        return beta, None
    return beta, float(beta / se)


def select_directed_edges(
    features: pd.DataFrame,
    outcomes: pd.DataFrame,
    *,
    window: int = 250,
    step: int = 20,
    tstat_threshold: float = 2.0,
    min_windows: int = 3,
    stability_threshold: float = 0.20,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    target_cols = [col for col in outcomes.columns if col.startswith("target_") and col.endswith("_ret1d_fwd")]
    joined = features.join(outcomes[target_cols], how="inner")
    for source_col in features.columns:
        for target_col in target_cols:
            stats = []
            for end in range(window, len(joined) + 1, step):
                sample = joined.iloc[end - window : end]
                beta, tstat = _ols_tstat(sample[source_col], sample[target_col])
                if beta is None or tstat is None:
                    continue
                stats.append({"beta": beta, "tstat": tstat, "selected": abs(tstat) >= tstat_threshold})
            selected = [item for item in stats if item["selected"]]
            sign_values = [math.copysign(1.0, item["beta"]) for item in selected if item["beta"] != 0.0]
            dominant_sign_share = 0.0
            dominant_sign = None
            if sign_values:
                pos = sum(1 for value in sign_values if value > 0)
                neg = len(sign_values) - pos
                dominant_sign_share = max(pos, neg) / len(sign_values)
                dominant_sign = 1 if pos >= neg else -1
            rows.append(
                {
                    "source_feature": source_col,
                    "target_feature": target_col,
                    "tested_windows": len(stats),
                    "selected_windows": len(selected),
                    "selection_rate": len(selected) / len(stats) if stats else 0.0,
                    "dominant_sign": dominant_sign,
                    "dominant_sign_share": dominant_sign_share,
                    "mean_abs_tstat_selected": (
                        float(np.mean([abs(item["tstat"]) for item in selected])) if selected else 0.0
                    ),
                    "stable": bool(
                        len(selected) >= min_windows
                        and (len(selected) / len(stats) if stats else 0.0) >= stability_threshold
                        and dominant_sign_share >= 0.70
                    ),
                }
            )
    edges = pd.DataFrame(rows).sort_values(
        ["stable", "selection_rate", "mean_abs_tstat_selected"],
        ascending=[False, False, False],
    )
    selected_features = sorted(set(edges.loc[edges["stable"], "source_feature"]))
    return edges, [{"feature": feature} for feature in selected_features]


def _auc_or_none(y_true: pd.Series, proba: np.ndarray) -> float | None:
    if len(set(y_true.astype(int).tolist())) < 2:
        return None
    return float(roc_auc_score(y_true.astype(int), proba))


def _threshold_metrics(y_true: pd.Series, proba: np.ndarray, thresholds: tuple[float, ...] = (0.55, 0.60, 0.65)) -> list[dict[str, Any]]:
    y = y_true.astype(int).to_numpy()
    out: list[dict[str, Any]] = []
    positives = int(y.sum())
    for threshold in thresholds:
        pred = (proba >= threshold).astype(int)
        tp = int(((pred == 1) & (y == 1)).sum())
        fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum())
        alerts = int(pred.sum())
        precision = tp / alerts if alerts else None
        recall = tp / positives if positives else None
        false_positive_rate = fp / int((y == 0).sum()) if int((y == 0).sum()) else None
        out.append(
            {
                "threshold": float(threshold),
                "alerts": alerts,
                "true_positives": tp,
                "false_positives": fp,
                "false_negatives": fn,
                "precision": float(precision) if precision is not None else None,
                "recall": float(recall) if recall is not None else None,
                "false_positive_rate": float(false_positive_rate) if false_positive_rate is not None else None,
            }
        )
    return out


def _metrics_by_year(
    dates: list[str],
    truth: dict[str, list[int]],
    predictions: dict[str, list[float]],
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not dates:
        return out
    years = sorted({str(pd.Timestamp(date).year) for date in dates})
    date_years = [str(pd.Timestamp(date).year) for date in dates]
    for year in years:
        idx = [i for i, value in enumerate(date_years) if value == year]
        if not idx:
            continue
        out[year] = {}
        for action in ("REENTER", "NO_ADD"):
            y = pd.Series([truth[action][i] for i in idx], dtype=int)
            p = np.asarray([predictions[action][i] for i in idx], dtype=float)
            pred = (p >= 0.5).astype(int)
            out[year][action] = {
                "rows": int(len(idx)),
                "auc": _auc_or_none(y, p),
                "balanced_accuracy": float(balanced_accuracy_score(y, pred)) if len(y) else None,
                "positive_rate": float(y.mean()) if len(y) else None,
                "mean_probability": float(p.mean()) if len(p) else None,
                "threshold_metrics": _threshold_metrics(y, p) if len(y) else [],
            }
    return out


def _metrics_for_indices(
    idx: list[int],
    truth: dict[str, list[int]],
    predictions: dict[str, list[float]],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for action in ("REENTER", "NO_ADD"):
        y = pd.Series([truth[action][i] for i in idx], dtype=int)
        p = np.asarray([predictions[action][i] for i in idx], dtype=float)
        pred = (p >= 0.5).astype(int)
        out[action] = {
            "rows": int(len(idx)),
            "auc": _auc_or_none(y, p),
            "balanced_accuracy": float(balanced_accuracy_score(y, pred)) if len(y) else None,
            "positive_rate": float(y.mean()) if len(y) else None,
            "mean_probability": float(p.mean()) if len(p) else None,
            "threshold_metrics": _threshold_metrics(y, p) if len(y) else [],
        }
    return out


def _metrics_by_condition(
    dates: list[str],
    condition_values: dict[str, list[int]],
    truth: dict[str, list[int]],
    predictions: dict[str, list[float]],
) -> dict[str, Any]:
    del dates
    out: dict[str, Any] = {}
    for condition, values in condition_values.items():
        idx = [i for i, value in enumerate(values) if int(value or 0) == 1]
        if not idx:
            continue
        out[condition] = _metrics_for_indices(idx, truth, predictions)
        out[condition]["condition_rows"] = len(idx)
        out[condition]["condition_frequency"] = len(idx) / len(values) if values else None
    return out


def walk_forward_action_models(
    features: pd.DataFrame,
    outcomes: pd.DataFrame,
    selected_features: list[str],
    *,
    min_train_days: int = 252,
) -> dict[str, Any]:
    if not selected_features:
        return {"status": "skipped", "reason": "no_stable_edges"}
    condition_cols = [col for col in outcomes.columns if col.startswith("condition_")]
    labels = outcomes[["label_REENTER", "label_NO_ADD", *condition_cols]]
    data = features[selected_features].join(labels, how="inner").replace([np.inf, -np.inf], np.nan).dropna()
    if len(data) <= min_train_days + 20:
        return {"status": "skipped", "reason": "insufficient_rows", "rows": int(len(data))}
    predictions: dict[str, list[float]] = {"REENTER": [], "NO_ADD": []}
    truth: dict[str, list[int]] = {"REENTER": [], "NO_ADD": []}
    condition_values: dict[str, list[int]] = {col: [] for col in condition_cols}
    dates: list[str] = []
    for pos in range(min_train_days, len(data)):
        train = data.iloc[:pos]
        test = data.iloc[[pos]]
        dates.append(str(test.index[0].date()))
        for col in condition_cols:
            condition_values[col].append(int(test[col].iloc[0]))
        x_train = train[selected_features]
        x_test = test[selected_features]
        for action, label_col in (("REENTER", "label_REENTER"), ("NO_ADD", "label_NO_ADD")):
            y_train = train[label_col].astype(int)
            y_test = int(test[label_col].iloc[0])
            truth[action].append(y_test)
            if len(set(y_train.tolist())) < 2:
                predictions[action].append(float(y_train.mean()))
                continue
            model = make_pipeline(
                StandardScaler(),
                LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42),
            )
            model.fit(x_train, y_train)
            predictions[action].append(float(model.predict_proba(x_test)[:, 1][0]))
    metrics = {}
    for action in ("REENTER", "NO_ADD"):
        y = pd.Series(truth[action], dtype=int)
        p = np.asarray(predictions[action], dtype=float)
        pred = (p >= 0.5).astype(int)
        metrics[action] = {
            "auc": _auc_or_none(y, p),
            "balanced_accuracy": float(balanced_accuracy_score(y, pred)) if len(y) else None,
            "positive_rate": float(y.mean()) if len(y) else None,
            "mean_probability": float(p.mean()) if len(p) else None,
            "threshold_metrics": _threshold_metrics(y, p) if len(y) else [],
        }
    latest = {
        action: float(predictions[action][-1]) if predictions[action] else None
        for action in ("REENTER", "NO_ADD")
    }
    decision = "NO_ADD" if (latest["NO_ADD"] or 0.0) >= 0.55 and (latest["NO_ADD"] or 0.0) > (latest["REENTER"] or 0.0) else "REENTER" if (latest["REENTER"] or 0.0) >= 0.55 else "KEEP"
    return {
        "status": "ok",
        "rows": int(len(data)),
        "oos_rows": int(len(dates)),
        "selected_features": selected_features,
        "metrics": metrics,
        "metrics_by_year": _metrics_by_year(dates, truth, predictions),
        "metrics_by_condition": _metrics_by_condition(dates, condition_values, truth, predictions),
        "latest_probabilities": latest,
        "latest_shadow_action": decision,
        "policy": "shadow_only_no_weight_change",
    }


def walk_forward_graph_action_models(
    features: pd.DataFrame,
    outcomes: pd.DataFrame,
    *,
    edge_window: int,
    tstat_threshold: float,
    min_windows: int,
    stability_threshold: float,
    min_train_days: int = 504,
    retrain_step: int = 20,
) -> dict[str, Any]:
    """Leakage-safer action model with past-only edge selection."""

    labels = outcomes[["label_REENTER", "label_NO_ADD"]]
    data = features.join(outcomes, how="inner").replace([np.inf, -np.inf], np.nan).dropna(
        subset=["label_REENTER", "label_NO_ADD"]
    )
    feature_cols = list(features.columns)
    if len(data) <= min_train_days + retrain_step:
        return {"status": "skipped", "reason": "insufficient_rows", "rows": int(len(data))}

    predictions: dict[str, list[float]] = {"REENTER": [], "NO_ADD": []}
    truth: dict[str, list[int]] = {"REENTER": [], "NO_ADD": []}
    condition_cols = [col for col in outcomes.columns if col.startswith("condition_")]
    condition_values: dict[str, list[int]] = {col: [] for col in condition_cols}
    selected_history: list[dict[str, Any]] = []
    dates: list[str] = []
    latest_selected_features: list[str] = []
    latest_probabilities: dict[str, float | None] = {"REENTER": None, "NO_ADD": None}

    for block_start in range(min_train_days, len(data), retrain_step):
        block_end = min(block_start + retrain_step, len(data))
        train = data.iloc[:block_start]
        test = data.iloc[block_start:block_end]
        train_features = train[feature_cols].fillna(0.0)
        train_outcomes = train[outcomes.columns]
        edges, selected = select_directed_edges(
            train_features,
            train_outcomes,
            window=min(edge_window, max(40, len(train_features) - 1)),
            tstat_threshold=tstat_threshold,
            min_windows=min_windows,
            stability_threshold=stability_threshold,
        )
        selected_features = [item["feature"] for item in selected]
        latest_selected_features = selected_features
        selected_history.append(
            {
                "train_end": str(train.index[-1].date()),
                "test_start": str(test.index[0].date()),
                "test_end": str(test.index[-1].date()),
                "selected_features": selected_features,
                "stable_edge_count": int(edges["stable"].sum()) if not edges.empty else 0,
            }
        )

        for _dt, test_row in test.iterrows():
            dates.append(str(pd.Timestamp(_dt).date()))
            for col in condition_cols:
                condition_values[col].append(int(test_row.get(col, 0) or 0))
        if not selected_features:
            for action, label_col in (("REENTER", "label_REENTER"), ("NO_ADD", "label_NO_ADD")):
                mean_prob = float(train[label_col].astype(float).mean())
                values = [mean_prob] * len(test)
                predictions[action].extend(values)
                truth[action].extend(test[label_col].astype(int).tolist())
                latest_probabilities[action] = values[-1] if values else latest_probabilities[action]
            continue

        x_train = train[selected_features].fillna(0.0)
        x_test = test[selected_features].fillna(0.0)
        for action, label_col in (("REENTER", "label_REENTER"), ("NO_ADD", "label_NO_ADD")):
            y_train = train[label_col].astype(int)
            y_test = test[label_col].astype(int)
            truth[action].extend(y_test.tolist())
            if len(set(y_train.tolist())) < 2:
                values = [float(y_train.mean())] * len(test)
            else:
                model = make_pipeline(
                    StandardScaler(),
                    LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42),
                )
                model.fit(x_train, y_train)
                values = model.predict_proba(x_test)[:, 1].astype(float).tolist()
            predictions[action].extend(values)
            latest_probabilities[action] = values[-1] if values else latest_probabilities[action]

    metrics = {}
    for action in ("REENTER", "NO_ADD"):
        y = pd.Series(truth[action], dtype=int)
        p = np.asarray(predictions[action], dtype=float)
        pred = (p >= 0.5).astype(int)
        metrics[action] = {
            "auc": _auc_or_none(y, p),
            "balanced_accuracy": float(balanced_accuracy_score(y, pred)) if len(y) else None,
            "positive_rate": float(y.mean()) if len(y) else None,
            "mean_probability": float(p.mean()) if len(p) else None,
            "threshold_metrics": _threshold_metrics(y, p) if len(y) else [],
        }
    decision = (
        "NO_ADD"
        if (latest_probabilities["NO_ADD"] or 0.0) >= 0.55
        and (latest_probabilities["NO_ADD"] or 0.0) > (latest_probabilities["REENTER"] or 0.0)
        else "REENTER" if (latest_probabilities["REENTER"] or 0.0) >= 0.55 else "KEEP"
    )
    feature_counts: dict[str, int] = {}
    for item in selected_history:
        for feature in item["selected_features"]:
            feature_counts[feature] = feature_counts.get(feature, 0) + 1
    return {
        "status": "ok",
        "mode": "walk_forward_edge_selection",
        "rows": int(len(data)),
        "oos_rows": int(len(dates)),
        "retrain_step": int(retrain_step),
        "min_train_days": int(min_train_days),
        "latest_selected_features": latest_selected_features,
        "most_frequent_selected_features": [
            {"feature": feature, "count": count}
            for feature, count in sorted(feature_counts.items(), key=lambda item: (-item[1], item[0]))[:20]
        ],
        "selection_history_tail": selected_history[-10:],
        "metrics": metrics,
        "metrics_by_year": _metrics_by_year(dates, truth, predictions),
        "metrics_by_condition": _metrics_by_condition(dates, condition_values, truth, predictions),
        "latest_probabilities": latest_probabilities,
        "latest_shadow_action": decision,
        "policy": "shadow_only_no_weight_change",
    }


def build_report(
    *,
    db_path: Path,
    start: str,
    end: str,
    source_tickers: tuple[str, ...],
    target_tickers: tuple[str, ...],
    edge_window: int,
    tstat_threshold: float = 2.0,
    min_windows: int = 3,
    stability_threshold: float = 0.55,
    use_composite_features: bool = True,
    walk_forward_edge_selection: bool = False,
    min_train_days: int = 504,
    retrain_step: int = 20,
) -> dict[str, Any]:
    source_close = load_source_closes(db_path, source_tickers, start, end)
    target_close = load_target_closes(db_path, target_tickers, start, end)
    if source_close.empty or target_close.empty:
        raise ValueError("Missing source or target close data")
    target_close = target_close.dropna(how="all")
    features = align_source_returns_to_taiwan_dates(source_close, target_close.index)
    if use_composite_features:
        features = add_composite_source_features(features)
    outcomes = build_target_outcomes(target_close)
    valid_features = features.dropna(axis=1, thresh=max(edge_window, 40))
    valid = valid_features.join(outcomes, how="inner").dropna(subset=["label_REENTER", "label_NO_ADD"])
    features = valid[valid_features.columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    outcomes = valid[outcomes.columns]
    edges, selected = select_directed_edges(
        features,
        outcomes,
        window=edge_window,
        tstat_threshold=tstat_threshold,
        min_windows=min_windows,
        stability_threshold=stability_threshold,
    )
    selected_features = [item["feature"] for item in selected]
    if walk_forward_edge_selection:
        action_model = walk_forward_graph_action_models(
            features,
            outcomes,
            edge_window=edge_window,
            tstat_threshold=tstat_threshold,
            min_windows=min_windows,
            stability_threshold=stability_threshold,
            min_train_days=min_train_days,
            retrain_step=retrain_step,
        )
    else:
        action_model = walk_forward_action_models(features, outcomes, selected_features)
    latest_edges = edges.head(25).to_dict(orient="records")
    no_add_auc = ((action_model.get("metrics") or {}).get("NO_ADD") or {}).get("auc")
    reenter_auc = ((action_model.get("metrics") or {}).get("REENTER") or {}).get("auc")
    return {
        "schema_version": 1,
        "report_type": "cross_market_directed_graph_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "db_path": str(db_path),
            "start": start,
            "end": end,
            "source_tickers_requested": list(source_tickers),
            "source_tickers_available": list(source_close.columns),
            "target_tickers_requested": list(target_tickers),
            "target_tickers_available": list(target_close.columns),
            "timing": "source close date must be strictly earlier than Taiwan target date",
            "feature_rows": int(len(features)),
            "feature_count": int(features.shape[1]),
            "use_composite_features": bool(use_composite_features),
            "walk_forward_edge_selection": bool(walk_forward_edge_selection),
            "min_train_days": int(min_train_days),
            "retrain_step": int(retrain_step),
            "edge_window": int(edge_window),
            "tstat_threshold": float(tstat_threshold),
            "min_windows": int(min_windows),
            "stability_threshold": float(stability_threshold),
        },
        "edge_selection": {
            "stable_edge_count": int(edges["stable"].sum()) if not edges.empty else 0,
            "selected_source_features": selected_features,
            "top_edges": latest_edges,
        },
        "action_model": action_model,
        "promotion_assessment": {
            "recommended_use": "NO_ADD_ONLY_SHADOW_FILTER",
            "promote_to_execution_guard": False,
            "promote_to_reentry_signal": False,
            "rationale": (
                "NO_ADD has weak but repeatable signal in selected stress years; "
                "REENTER is unstable and should not drive re-entry."
            ),
            "minimum_live_alert_policy": {
                "no_add_probability_min": 0.65,
                "require_no_add_gt_reenter": True,
                "auto_weight_change": False,
            },
            "summary_metrics": {
                "NO_ADD_auc": no_add_auc,
                "REENTER_auc": reenter_auc,
            },
        },
        "method_note": (
            "Directed bipartite graph is used as a sparse feature-selection layer. "
            "The downstream classifier predicts REENTER/NO_ADD and remains shadow-only."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2019-01-02")
    parser.add_argument("--end", default="2026-07-14")
    parser.add_argument("--source-tickers", default=",".join(DEFAULT_SOURCE_TICKERS))
    parser.add_argument("--target-tickers", default=",".join(DEFAULT_TARGET_TICKERS))
    parser.add_argument("--edge-window", type=int, default=250)
    parser.add_argument("--tstat-threshold", type=float, default=2.0)
    parser.add_argument("--min-windows", type=int, default=3)
    parser.add_argument("--stability-threshold", type=float, default=0.20)
    parser.add_argument("--no-composite-features", action="store_true")
    parser.add_argument("--walk-forward-edge-selection", action="store_true")
    parser.add_argument("--min-train-days", type=int, default=504)
    parser.add_argument("--retrain-step", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = build_report(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        source_tickers=tuple(item.strip() for item in args.source_tickers.split(",") if item.strip()),
        target_tickers=tuple(item.strip() for item in args.target_tickers.split(",") if item.strip()),
        edge_window=args.edge_window,
        tstat_threshold=float(args.tstat_threshold),
        min_windows=int(args.min_windows),
        stability_threshold=float(args.stability_threshold),
        use_composite_features=not args.no_composite_features,
        walk_forward_edge_selection=bool(args.walk_forward_edge_selection),
        min_train_days=int(args.min_train_days),
        retrain_step=int(args.retrain_step),
    )
    std = OutputStandardizer("evaluate_cross_market_directed_graph_shadow")
    write_standard_output(std.success(report, run_id=datetime.now().strftime("%Y%m%d_%H%M%S")), args.output)
    print(f"Cross-market directed graph shadow report: {_resolve(args.output)}")


if __name__ == "__main__":
    main()
