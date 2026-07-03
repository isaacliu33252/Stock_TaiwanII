#!/usr/bin/env python3
"""Research-only LightGBM baseline for Group A+ tabular panels."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import duckdb
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.llm_sentiment_features import attach_llm_sentiment_features
from group_a_plus.integrations.cross_asset_relation import (
    build_cross_asset_relation_features,
    cross_asset_relation_feature_columns,
)
from group_a_plus.integrations.fourier_features import add_atfnet_lite_features, atfnet_lite_feature_columns
from group_a_plus.validation.purged_walk_forward import PurgedWalkForwardSplit
from tw_output_standard import OutputStandardizer, write_standard_output
from backtest_group_a_plus_switch_policy import DB_PATH


DEFAULT_PANEL = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260630.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_lightgbm_baseline_latest.json"
LABEL_COLUMNS = {
    "forward_gain_h1", "forward_gain_h5", "forward_gain_h20",
    "forward_mdd_h20", "is_live",
}
DEFAULT_EXCLUDE_PREFIXES = ("forward_",)


def _load_panel(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "date" not in frame.columns:
        raise ValueError("panel is missing date column")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["date"]).sort_values("date")
    if "is_live" in frame.columns:
        frame = frame[~frame["is_live"].astype(bool)]
    return frame.reset_index(drop=True)


def _target_from_panel(panel: pd.DataFrame, target_column: str) -> pd.Series:
    if target_column not in panel.columns:
        raise ValueError(f"panel is missing target column: {target_column}")
    return (pd.to_numeric(panel[target_column], errors="coerce") > 0.0).astype(int)


def _feature_frame(panel: pd.DataFrame, target_column: str) -> pd.DataFrame:
    drop = {"date", target_column, *LABEL_COLUMNS}
    cols: list[str] = []
    for col in panel.columns:
        if col in drop:
            continue
        if any(str(col).startswith(prefix) for prefix in DEFAULT_EXCLUDE_PREFIXES):
            continue
        if pd.api.types.is_numeric_dtype(panel[col]):
            cols.append(col)
    if not cols:
        raise ValueError("panel has no numeric feature columns")
    features = panel[cols].apply(pd.to_numeric, errors="coerce")
    return features.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)


def _load_close_series(db_path: Path, ticker: str, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        frame = con.execute(
            """
            SELECT dt AS date, close
            FROM ohlcv
            WHERE ticker = ? AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [ticker, start, end],
        ).fetchdf()
    finally:
        con.close()
    if frame.empty:
        raise ValueError(f"no OHLCV rows found for {ticker} between {start} and {end}")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    return frame.dropna(subset=["date"]).set_index("date").sort_index()


def _load_close_matrix(db_path: Path, tickers: list[str], start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        frame = con.execute(
            """
            SELECT ticker, dt AS date, close
            FROM ohlcv
            WHERE ticker IN ({}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """.format(",".join(["?"] * len(tickers))),
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if frame.empty:
        raise ValueError(f"no OHLCV rows found for tickers {tickers} between {start} and {end}")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    matrix = frame.pivot(index="date", columns="ticker", values="close").sort_index()
    missing = [ticker for ticker in tickers if ticker not in matrix.columns]
    if missing:
        raise ValueError(f"missing OHLCV tickers: {missing}")
    return matrix[tickers].ffill()


def attach_fourier_price_features(
    panel: pd.DataFrame,
    *,
    db_path: Path,
    ticker: str,
    windows: tuple[int, ...] = (16, 32, 64),
) -> pd.DataFrame:
    """Attach ATFNet-lite spectral features from a ticker close series."""
    out = panel.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    start = str(out["date"].min().date())
    end = str(out["date"].max().date())
    prices = _load_close_series(db_path, ticker, start, end)
    prefix = "fft_" + ticker.replace(".", "_").replace("-", "_")
    features = add_atfnet_lite_features(prices, windows=windows, prefix=prefix)
    cols = atfnet_lite_feature_columns(windows=windows, prefix=prefix)
    joined = out.set_index("date").join(features[cols], how="left")
    joined[cols] = joined[cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return joined.reset_index()


def attach_cross_asset_relation_features(
    panel: pd.DataFrame,
    *,
    db_path: Path,
    tickers: list[str] | None = None,
    windows: tuple[int, ...] = (5, 20, 60),
) -> pd.DataFrame:
    tickers = tickers or ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"]
    out = panel.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    start = str(out["date"].min().date())
    end = str(out["date"].max().date())
    prices = _load_close_matrix(db_path, tickers, start, end)
    features = build_cross_asset_relation_features(prices, windows=windows)
    cols = cross_asset_relation_feature_columns(windows=windows)
    joined = out.set_index("date").join(features[cols], how="left")
    joined[cols] = joined[cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return joined.reset_index()


def _make_model(random_state: int = 42):
    try:
        from lightgbm import LGBMClassifier

        return LGBMClassifier(
            n_estimators=120,
            learning_rate=0.04,
            num_leaves=15,
            max_depth=-1,
            min_child_samples=12,
            subsample=0.9,
            colsample_bytree=0.9,
            reg_lambda=0.1,
            random_state=random_state,
            verbosity=-1,
        ), "lightgbm"
    except Exception:
        return HistGradientBoostingClassifier(
            max_iter=120,
            learning_rate=0.04,
            max_leaf_nodes=15,
            l2_regularization=0.05,
            random_state=random_state,
        ), "hist_gradient_boosting_fallback"


def _auc(y_true, proba) -> float | None:
    values = np.asarray(y_true)
    if len(np.unique(values)) < 2:
        return None
    return float(roc_auc_score(values, proba))


def _brier(y_true, proba) -> float:
    return float(brier_score_loss(np.asarray(y_true), np.asarray(proba)))


def evaluate_lightgbm_baseline(
    panel: pd.DataFrame,
    *,
    target_column: str = "forward_gain_h20",
    baseline_column: str = "prob_up_h20",
    n_splits: int = 4,
    test_size: int | None = None,
    train_size: int | None = None,
    purge: int = 20,
    min_train_size: int = 80,
) -> dict[str, Any]:
    y = _target_from_panel(panel, target_column)
    x = _feature_frame(panel, target_column)
    valid = y.notna()
    x = x.loc[valid].reset_index(drop=True)
    y = y.loc[valid].reset_index(drop=True)
    dates = pd.to_datetime(panel.loc[valid, "date"]).reset_index(drop=True)
    baseline = (
        pd.to_numeric(panel.loc[valid, baseline_column], errors="coerce").fillna(0.5).clip(0.0, 1.0).reset_index(drop=True)
        if baseline_column in panel.columns
        else pd.Series(0.5, index=x.index)
    )

    splitter = PurgedWalkForwardSplit(
        n_splits=n_splits,
        test_size=test_size,
        train_size=train_size,
        purge=purge,
        min_train_size=min_train_size,
    )
    folds: list[dict[str, Any]] = []
    model_probs: list[float] = []
    baseline_probs: list[float] = []
    truth: list[int] = []
    model_kind = "unknown"

    for fold, (train_idx, test_idx) in enumerate(splitter.split(x), start=1):
        model, model_kind = _make_model(random_state=42 + fold)
        model.fit(x.iloc[train_idx], y.iloc[train_idx])
        proba = model.predict_proba(x.iloc[test_idx])[:, 1]
        base = baseline.iloc[test_idx].to_numpy(dtype=float)
        yy = y.iloc[test_idx].to_numpy(dtype=int)
        model_probs.extend(proba.tolist())
        baseline_probs.extend(base.tolist())
        truth.extend(yy.tolist())
        folds.append(
            {
                "fold": fold,
                "train_start": str(dates.iloc[train_idx[0]].date()),
                "train_end": str(dates.iloc[train_idx[-1]].date()),
                "test_start": str(dates.iloc[test_idx[0]].date()),
                "test_end": str(dates.iloc[test_idx[-1]].date()),
                "train_rows": int(len(train_idx)),
                "test_rows": int(len(test_idx)),
                "purge_rows": int(purge),
                "positive_rate_test": float(np.mean(yy)),
                "model_auc": _auc(yy, proba),
                "model_brier": _brier(yy, proba),
                "baseline_auc": _auc(yy, base),
                "baseline_brier": _brier(yy, base),
            }
        )

    model_auc = _auc(truth, np.asarray(model_probs))
    baseline_auc = _auc(truth, np.asarray(baseline_probs))
    model_brier = _brier(truth, model_probs)
    baseline_brier = _brier(truth, baseline_probs)
    return {
        "model_kind": model_kind,
        "target_column": target_column,
        "baseline_column": baseline_column,
        "feature_count": int(x.shape[1]),
        "feature_columns": list(x.columns),
        "rows": int(len(x)),
        "folds": folds,
        "aggregate": {
            "model_auc": model_auc,
            "baseline_auc": baseline_auc,
            "auc_delta_vs_baseline": None if model_auc is None or baseline_auc is None else float(model_auc - baseline_auc),
            "model_brier": model_brier,
            "baseline_brier": baseline_brier,
            "brier_delta_vs_baseline": float(model_brier - baseline_brier),
        },
        "promotion_decision": (
            "candidate_for_deeper_ablation"
            if model_auc is not None and baseline_auc is not None and model_auc - baseline_auc >= 0.02
            else "research_only"
        ),
    }


def build_report(
    panel_path: Path,
    *,
    llm_sentiment_path: Path | None = None,
    fourier_ticker: str | None = None,
    cross_asset_relations: bool = False,
    db_path: Path = DB_PATH,
    target_column: str = "forward_gain_h20",
    n_splits: int = 4,
    test_size: int | None = None,
    train_size: int | None = None,
    purge: int = 20,
    min_train_size: int = 80,
) -> dict[str, Any]:
    panel = _load_panel(panel_path)
    sentiment_info: dict[str, Any] = {"enabled": False}
    if llm_sentiment_path is not None:
        panel = attach_llm_sentiment_features(panel, llm_sentiment_path, date_column="date", lag_days=1)
        sentiment_info = {"enabled": True, "path": str(llm_sentiment_path)}
    fourier_info: dict[str, Any] = {"enabled": False}
    if fourier_ticker:
        panel = attach_fourier_price_features(panel, db_path=db_path, ticker=fourier_ticker)
        fourier_info = {"enabled": True, "ticker": fourier_ticker, "db": str(db_path)}
    relation_info: dict[str, Any] = {"enabled": False}
    if cross_asset_relations:
        panel = attach_cross_asset_relation_features(panel, db_path=db_path)
        relation_info = {"enabled": True, "db": str(db_path)}
    evaluation = evaluate_lightgbm_baseline(
        panel,
        target_column=target_column,
        n_splits=n_splits,
        test_size=test_size,
        train_size=train_size,
        purge=purge,
        min_train_size=min_train_size,
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_lightgbm_baseline",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "panel": str(panel_path),
            "llm_sentiment": sentiment_info,
            "fourier": fourier_info,
            "cross_asset_relations": relation_info,
        },
        "validation": {
            "method": "purged_walk_forward",
            "n_splits": n_splits,
            "test_size": test_size,
            "train_size": train_size,
            "purge": purge,
            "min_train_size": min_train_size,
        },
        "evaluation": evaluation,
        "active_allocation_impact": "none",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--llm-sentiment", default=None)
    parser.add_argument("--fourier-ticker", default=None, help="Attach ATFNet-lite Fourier features from this OHLCV ticker")
    parser.add_argument("--cross-asset-relations", action="store_true", help="Attach NoGraphMixer-lite cross-asset relation features")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--target-column", default="forward_gain_h20")
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--test-size", type=int, default=None)
    parser.add_argument("--train-size", type=int, default=None)
    parser.add_argument("--purge", type=int, default=20)
    parser.add_argument("--min-train-size", type=int, default=80)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    std = OutputStandardizer("evaluate_lightgbm_baseline")
    try:
        report = build_report(
            Path(args.panel),
            llm_sentiment_path=Path(args.llm_sentiment) if args.llm_sentiment else None,
            fourier_ticker=args.fourier_ticker,
            cross_asset_relations=args.cross_asset_relations,
            db_path=Path(args.db),
            target_column=args.target_column,
            n_splits=args.n_splits,
            test_size=args.test_size,
            train_size=args.train_size,
            purge=args.purge,
            min_train_size=args.min_train_size,
        )
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"LightGBM baseline report: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
