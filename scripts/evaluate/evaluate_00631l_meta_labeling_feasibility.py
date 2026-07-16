#!/usr/bin/env python3
"""Feasibility test: can a meta-labeling classifier learn when 00631L's
primary H5 directional bet is trustworthy?

Research-only, per user request 2026-07-12 following a discussion of
triple-barrier labeling and meta-labeling (Lopez de Prado, Advances in
Financial Machine Learning). Triple-barrier labeling is already in
production for the H5 horizon (scripts/misc/ncf_00631l.py's
`triple_barrier_label`, cited directly in that function's docstring) --
this script does not test that, it reuses it as ground truth. Meta-labeling
itself (a trained secondary classifier deciding whether to act on the
primary signal, as opposed to hand-tuned rule gates like
direction_magnitude_gate) does not exist anywhere in this codebase; this is
a first feasibility check, not a full implementation.

Design:
  Primary signal: sign(prob_up_h5 - 0.5) from the NCF panel (the same H5
  probability that already drives triple-barrier-labeled training).
  Ground truth ("was the primary bet correct?"): the actual triple-barrier
  outcome computed directly from OHLC price data using the *same*
  `triple_barrier_label` function already in production (t_max=5,
  tp_mult=sl_mult=0.75, matching ncf_00631l.py's default --tbl-mult).
  Label=1 (up barrier hit) correct iff primary side is UP; label=0 (down
  barrier hit) correct iff primary side is DOWN; label=-1 (timeout) is
  excluded (inconclusive, matches how ncf_00631l.py already filters -1 from
  training).

  Meta-features (all available at signal time, no look-ahead):
    prob_edge_h5, confidence, ensemble_weight_h5, cross-horizon agreement
    (do h1/h5/h20 point the same direction), tail_reward_risk_score_h20,
    prob_fwd_mdd_gt5_h20, prob_fwd_gain_gt5_h20, trailing 20d realized vol.

  Model: simple Logistic Regression (few features, small sample -- avoid
  overfitting a bigger model on ~1000 rows), walk-forward with an expanding
  window, minimum 252-day training history before the first prediction, no
  refit-window look-ahead.

  Evaluation: walk-forward AUC of the meta-model at discriminating
  correct-vs-incorrect primary bets, benchmarked against the single existing
  `confidence` field alone (the closest thing already in production to a
  meta-label proxy) to see whether a trained combination beats that single
  heuristic.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.misc.ncf_00631l import triple_barrier_label
from group_a_plus.integrations.volatility_forecast import garman_klass_variance, har_rv_walkforward_forecast

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_meta_labeling_feasibility_latest.json"

PANEL_FILES = [
    PROJECT_ROOT / "results" / "ncf_00631l_panel_backfill_2017_2019_20260710.csv",
    PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260710.csv",
]

HORIZON = 5
TP_MULT = 0.75
SL_MULT = 0.75
MIN_TRAIN_DAYS = 252
REFIT_EVERY = 21

FEATURE_COLS = [
    "prob_edge_h5",
    "confidence",
    "ensemble_weight_h5",
    "cross_horizon_agreement",
    "tail_reward_risk_score_h20",
    "prob_fwd_mdd_gt5_h20",
    "prob_fwd_gain_gt5_h20",
    "realized_vol_20d",
]

# 2026-07-12 follow-up: user asked whether GARCH-style (HAR-RV) forecast vol
# and RSI -- the two features xglamdring.com's meta-labeling explainer names
# but the original feature set above didn't include -- change the result.
# har_rv_forecast_h5_ratio reuses the already-validated (2026-07-10) walk-
# forward HAR-RV forecaster instead of a naive trailing realized-vol window;
# rsi_14 is a standard 14-day RSI, not used anywhere in the original set.
FEATURE_COLS_GARCH_RSI = [
    "prob_edge_h5",
    "confidence",
    "ensemble_weight_h5",
    "cross_horizon_agreement",
    "tail_reward_risk_score_h20",
    "prob_fwd_mdd_gt5_h20",
    "prob_fwd_gain_gt5_h20",
    "har_rv_forecast_h5_ratio",
    "rsi_14",
]


def _rsi_14(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0).rolling(window).mean()
    loss = (-delta.clip(upper=0.0)).rolling(window).mean()
    rs = gain / loss.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


def _load_price(ticker: str = "00631L.TW") -> pd.DataFrame:
    import duckdb

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt, open, high, low, close FROM ohlcv WHERE ticker = ? ORDER BY dt", [ticker]
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt").astype(float)


def _load_panels() -> pd.DataFrame:
    frames = [pd.read_csv(f) for f in PANEL_FILES if f.exists()]
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])
    panel = panel.drop_duplicates(subset="date").sort_values("date").set_index("date")
    return panel


def _build_dataset() -> pd.DataFrame:
    panel = _load_panels()
    price = _load_price()
    tbl = triple_barrier_label(
        price["close"], price["high"], price["low"], t_max=HORIZON, tp_mult=TP_MULT, sl_mult=SL_MULT
    )
    realized_vol = price["close"].pct_change().rolling(20).std()
    gk_var = garman_klass_variance(price)
    har_fc = har_rv_walkforward_forecast(gk_var, horizon=HORIZON)
    har_fc_ratio = (har_fc / har_fc.rolling(252, min_periods=60).median().replace(0.0, np.nan)).fillna(1.0)
    rsi = _rsi_14(price["close"])

    df = (
        panel.join(tbl.rename("tbl_label"), how="inner")
        .join(realized_vol.rename("realized_vol_20d"), how="left")
        .join(har_fc_ratio.rename("har_rv_forecast_h5_ratio"), how="left")
        .join(rsi.rename("rsi_14"), how="left")
    )

    df["primary_side"] = np.where(df["prob_up_h5"] > 0.5, 1, -1)
    df["prob_edge_h5"] = (df["prob_up_h5"] - 0.5).abs()
    h1_side = np.sign(df["prob_up_h1"] - 0.5)
    h20_side = np.sign(df["prob_up_h20"] - 0.5)
    h5_side = np.sign(df["prob_up_h5"] - 0.5)
    df["cross_horizon_agreement"] = ((h1_side == h5_side).astype(int) + (h20_side == h5_side).astype(int)) / 2.0

    valid_tbl = df["tbl_label"].isin([0, 1])
    df = df[valid_tbl].copy()
    df["meta_label"] = (
        ((df["primary_side"] == 1) & (df["tbl_label"] == 1))
        | ((df["primary_side"] == -1) & (df["tbl_label"] == 0))
    ).astype(int)

    all_needed_cols = sorted(set(FEATURE_COLS) | set(FEATURE_COLS_GARCH_RSI) | {"meta_label"})
    df = df.dropna(subset=all_needed_cols)
    return df


def _walk_forward_auc(df: pd.DataFrame, feature_cols: list[str]) -> dict:
    X = df[feature_cols].to_numpy(dtype=float)
    y = df["meta_label"].to_numpy(dtype=int)
    n = len(df)

    preds = np.full(n, np.nan)
    for start in range(MIN_TRAIN_DAYS, n, REFIT_EVERY):
        end = min(start + REFIT_EVERY, n)
        X_train, y_train = X[:start], y[:start]
        if len(np.unique(y_train)) < 2:
            continue
        model = LogisticRegression(max_iter=1000)
        model.fit(X_train, y_train)
        preds[start:end] = model.predict_proba(X[start:end])[:, 1]

    valid = ~np.isnan(preds)
    n_eval = int(valid.sum())
    if n_eval < 60 or len(np.unique(y[valid])) < 2:
        return {"status": "insufficient_data", "n": n_eval}

    auc_meta = float(roc_auc_score(y[valid], preds[valid]))
    auc_confidence_only = float(roc_auc_score(y[valid], df["confidence"].to_numpy()[valid]))
    base_rate = float(y[valid].mean())
    return {
        "status": "ok",
        "n": n_eval,
        "base_rate_primary_correct": base_rate,
        "meta_model_auc": auc_meta,
        "confidence_only_auc": auc_confidence_only,
        "meta_vs_confidence_delta": auc_meta - auc_confidence_only,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    df = _build_dataset()
    result_original = _walk_forward_auc(df, FEATURE_COLS)
    result_garch_rsi = _walk_forward_auc(df, FEATURE_COLS_GARCH_RSI)
    payload = {
        "rows_after_filtering_timeouts": int(len(df)),
        "date_range": {"start": str(df.index.min().date()), "end": str(df.index.max().date())},
        "original_features": result_original,
        "garch_rsi_features": result_garch_rsi,
    }

    print(f"Dataset: {payload['rows_after_filtering_timeouts']} rows, {payload['date_range']['start']}..{payload['date_range']['end']}")
    for label, result in (("original (realized_vol)", result_original), ("garch_rsi (HAR-RV forecast + RSI)", result_garch_rsi)):
        if result["status"] == "insufficient_data":
            print(f"[{label}] insufficient data (n={result['n']})")
            continue
        print(
            f"[{label}] n={result['n']} base_rate={result['base_rate_primary_correct']:.3f} "
            f"meta_auc={result['meta_model_auc']:.4f} confidence_only_auc={result['confidence_only_auc']:.4f} "
            f"delta={result['meta_vs_confidence_delta']:+.4f}"
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
