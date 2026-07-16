#!/usr/bin/env python3
"""Direct ML crash-risk forecast for 00631L.TW de-risking.

Research-only, 2026-07-12. This is deliberately different from ordinary
up/down forecasting and from the earlier race classifier. The target is a
tail event: a future max-drawdown breach on 00631L.TW. The trading rule is
also deliberately sparse: only when predicted crash risk is extreme do we
shift the golden1 00631L.TW weight into 0050.TW.

Default labels:
  A) future 10-trading-day max drawdown < -5%
  B) future 20-trading-day max drawdown < -8%

The script reports both forecast quality (AUC, average precision, event
rate in the top predicted-risk bucket) and the de-risk backtest delta vs
the current a2118 baseline. It does not change live signals or target
weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices
from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _metrics
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_group_a_plus_00631l_downside_oracle_ceiling import _label_max_drawdown
from scripts.evaluate.evaluate_group_a_plus_00631l_downside_race_classifier import (
    CHIP_FEATURE_COLUMNS,
    FEATURE_COLUMNS,
    MIN_TRAIN_ROWS,
    REFIT_EVERY,
    TRAIN_WINDOW,
    _build_features,
    _load_ohlc,
    _rolling_quantile_flag,
    _simulate_scaled_curve,
    _walkforward_predict,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_ml_crash_risk_derisk_latest.json"

CRASH_LABELS = {
    "10d_mdd_lt_5pct": {"horizon": 10, "threshold": -0.05},
    "20d_mdd_lt_8pct": {"horizon": 20, "threshold": -0.08},
}

WINDOWS = [
    ("tuning", "covid_2020", "2020-01-02", "2020-12-31", "results/ncf_00631l_panel_latest_20260707.csv"),
    ("tuning", "inflation_2022", "2022-01-03", "2022-12-30", "results/ncf_00631l_panel_latest_20260707.csv"),
    ("tuning", "live_2024_2026", "2024-01-02", "latest", "results/ncf_00631l_panel_latest_20260707.csv"),
    ("tuning", "active_2025_2026", "2025-01-02", "latest", "results/ncf_00631l_panel_latest_20260707.csv"),
    ("oos", "2017_bull", "2017-01-03", "2017-12-29", "results/ncf_00631l_panel_backfill_2017_2019_20260710.csv"),
    ("oos", "2018_correction", "2018-01-02", "2018-12-28", "results/ncf_00631l_panel_backfill_2017_2019_20260710.csv"),
    ("oos", "2019_recovery", "2019-01-02", "2019-12-31", "results/ncf_00631l_panel_backfill_2017_2019_20260710.csv"),
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


def _forecast_metrics(y_true: pd.Series, proba: pd.Series, *, top_quantile: float) -> dict:
    valid = y_true.notna() & proba.notna()
    y = y_true[valid].astype(int)
    p = proba[valid].astype(float)
    out = {
        "n_valid": int(valid.sum()),
        "event_rate": float(y.mean()) if len(y) else None,
        "auc": None,
        "average_precision": None,
        "top_quantile": float(top_quantile),
        "top_bucket_days": 0,
        "top_bucket_event_rate": None,
        "lift_vs_base_rate": None,
    }
    if len(y) > 20 and y.nunique() > 1:
        out["auc"] = float(roc_auc_score(y, p))
        out["average_precision"] = float(average_precision_score(y, p))
        cutoff = float(p.quantile(top_quantile))
        top = p >= cutoff
        out["top_bucket_days"] = int(top.sum())
        out["top_bucket_event_rate"] = float(y[top].mean()) if top.any() else None
        if out["event_rate"] and out["top_bucket_event_rate"] is not None:
            out["lift_vs_base_rate"] = float(out["top_bucket_event_rate"] / out["event_rate"])
    return out


def evaluate_label(
    *,
    label_name: str,
    horizon: int,
    drawdown_threshold: float,
    db_path: Path,
    feature_start: str,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    use_chip_features: bool,
    trigger_mode: str,
    decision_threshold: float,
    rolling_quantile_window: int,
    rolling_quantile_level: float,
    top_quantile_report: float,
) -> dict:
    overall_end = _resolve_end_date(db_path, "latest")
    ohlc_0050 = _load_ohlc(db_path, "0050.TW", feature_start, overall_end)
    ohlc_631l = _load_ohlc(db_path, "00631L.TW", feature_start, overall_end)
    chip_features = None
    if use_chip_features:
        chip_features = _load_chip_features(db_path, ohlc_0050.index, feature_start, overall_end)

    feature_cols = FEATURE_COLUMNS + (CHIP_FEATURE_COLUMNS if use_chip_features else [])
    features = _build_features(ohlc_0050, ohlc_631l, chip_features)[feature_cols]
    future_mdd = _label_max_drawdown(ohlc_631l["close"].astype(float), horizon)
    label = (future_mdd < drawdown_threshold).astype(float)
    label[future_mdd.isna()] = float("nan")
    pred_proba = _walkforward_predict(
        features,
        label,
        train_window=TRAIN_WINDOW,
        refit_every=REFIT_EVERY,
        min_train_rows=MIN_TRAIN_ROWS,
        horizon=horizon,
    )
    if trigger_mode == "rolling_quantile":
        derisk_fraction = _rolling_quantile_flag(
            pred_proba, rolling_quantile_window, rolling_quantile_level
        ).astype(float)
    else:
        derisk_fraction = (pred_proba >= decision_threshold).fillna(False).astype(float)

    windows = []
    for kind, win_label, start, end, panel in WINDOWS:
        end_resolved = _resolve_end_date(db_path, end)
        report, frame = run_a2118(
            start=start,
            end=end_resolved,
            initial_value=initial_value,
            db=db_path,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
            ncf_panel_631l_path=panel,
            h20_max=0.33,
            conf_min=0.55,
            h5_reentry_min=0.55,
            chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
            risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
            momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
            momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        )
        prices = _load_prices(db_path, list(TICKERS), start, end_resolved)
        total_return_prices, _ = _load_total_return_prices(db_path, prices.index)
        execution_regime = frame["execution_regime"].astype(str)
        baseline_metrics = dict(report["metrics"])
        baseline_execution = dict(report["execution"])

        win_proba = pred_proba.reindex(frame.index)
        win_label_series = label.reindex(frame.index)
        forecast = _forecast_metrics(win_label_series, win_proba, top_quantile=top_quantile_report)

        curve, sim = _simulate_scaled_curve(
            total_return_prices,
            execution_regime,
            derisk_fraction.reindex(frame.index).fillna(0.0),
            dict(report["base_weights"]["golden1"]),
            dict(report["base_weights"]),
            initial_value,
            commission_rate,
            slippage_rate,
            equity_etf_sell_tax,
            buckets=1,
        )
        metrics = _metrics(curve, initial_value)
        golden_mask = execution_regime == "golden1"
        result = {
            "kind": kind,
            "label": win_label,
            "window": {"start": start, "end": end_resolved},
            "forecast": forecast,
            "golden1_days": int(golden_mask.sum()),
            "derisk_days_within_golden1": sim["days_with_derisk_gt0_golden1"],
            "delta_vs_baseline": {
                "final_value": metrics["final_value"] - baseline_metrics["final_value"],
                "sharpe_ratio": metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"],
                "max_drawdown": metrics["max_drawdown"] - baseline_metrics["max_drawdown"],
            },
            "extra_transaction_cost": float(sim["transaction_cost"] - baseline_execution.get("transaction_cost", 0.0)),
        }
        windows.append(result)
        d = result["delta_vs_baseline"]
        print(
            f"[{kind}] {label_name} {win_label}: auc={forecast['auc']} ap={forecast['average_precision']} "
            f"top_event_rate={forecast['top_bucket_event_rate']} derisk={result['derisk_days_within_golden1']}/{result['golden1_days']} "
            f"delta_final={d['final_value']:.1f} delta_sharpe={d['sharpe_ratio']:.4f} delta_mdd={d['max_drawdown']:.4f}"
        )

    return {
        "label": label_name,
        "definition": {"horizon": horizon, "drawdown_threshold": drawdown_threshold},
        "windows": windows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--feature-start", default="2016-01-04")
    parser.add_argument("--label", choices=list(CRASH_LABELS) + ["all"], default="all")
    parser.add_argument("--use-chip-features", action="store_true")
    parser.add_argument("--trigger-mode", choices=["rolling_quantile", "fixed"], default="rolling_quantile")
    parser.add_argument("--decision-threshold", type=float, default=0.7)
    parser.add_argument("--rolling-quantile-window", type=int, default=252)
    parser.add_argument("--rolling-quantile-level", type=float, default=0.95)
    parser.add_argument("--top-quantile-report", type=float, default=0.95)
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    selected = CRASH_LABELS.items() if args.label == "all" else [(args.label, CRASH_LABELS[args.label])]
    results = []
    for name, spec in selected:
        results.append(
            evaluate_label(
                label_name=name,
                horizon=spec["horizon"],
                drawdown_threshold=spec["threshold"],
                db_path=db_path,
                feature_start=args.feature_start,
                initial_value=args.initial_value,
                commission_rate=args.commission_rate,
                slippage_rate=args.slippage_rate,
                equity_etf_sell_tax=args.equity_etf_sell_tax,
                use_chip_features=args.use_chip_features,
                trigger_mode=args.trigger_mode,
                decision_threshold=args.decision_threshold,
                rolling_quantile_window=args.rolling_quantile_window,
                rolling_quantile_level=args.rolling_quantile_level,
                top_quantile_report=args.top_quantile_report,
            )
        )

    payload = {
        "experiment": "00631l_ml_crash_risk_derisk",
        "policy": "research_only_no_live_weight_change",
        "model": {
            "type": "GradientBoostingClassifier",
            "feature_columns": FEATURE_COLUMNS + (CHIP_FEATURE_COLUMNS if args.use_chip_features else []),
            "use_chip_features": args.use_chip_features,
            "train_window": TRAIN_WINDOW,
            "refit_every": REFIT_EVERY,
            "trigger_mode": args.trigger_mode,
            "decision_threshold": args.decision_threshold if args.trigger_mode == "fixed" else None,
            "rolling_quantile_window": args.rolling_quantile_window if args.trigger_mode == "rolling_quantile" else None,
            "rolling_quantile_level": args.rolling_quantile_level if args.trigger_mode == "rolling_quantile" else None,
        },
        "labels": results,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
