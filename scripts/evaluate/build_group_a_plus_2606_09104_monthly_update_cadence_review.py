#!/usr/bin/env python3
"""Build a 2606.09104 update cadence review for GroupA+.

The paper reports asynchronous BAVAR updates around every 21 trading days. This
shadow checks whether weekly or monthly hold-last-prior cadences materially
change HAR-BAVAR prior OOS ranking quality versus frequent updates. It never
changes live weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from scripts.evaluate.build_group_a_plus_2606_09104_har_bavar_prior_shadow import (  # noqa: E402
    CORE_TICKERS,
    DEFAULT_FORWARD_MONITOR,
    _future_return,
    _har_features,
    _load_close,
    _load_json,
    _ridge_predict,
    _score_predictions,
)
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_monthly_update_cadence_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_monthly_update_cadence_review/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _prediction_rows(
    *,
    returns: pd.DataFrame,
    features: pd.DataFrame,
    tickers: tuple[str, ...],
    train_window: int,
    horizon: int,
    eval_step: int,
    update_interval: int,
    ridge_alphas: tuple[float, ...],
) -> list[dict[str, Any]]:
    valid = pd.concat([features, returns], axis=1).dropna()
    date_to_pos = {date: idx for idx, date in enumerate(returns.index)}
    rows: list[dict[str, Any]] = []
    cached_pred: np.ndarray | None = None
    cached_update_date: pd.Timestamp | None = None
    last_update_row = -10**9
    for row_idx in range(train_window, len(valid) - horizon, eval_step):
        date = valid.index[row_idx]
        ret_pos = date_to_pos.get(date)
        if ret_pos is None or ret_pos + horizon >= len(returns):
            continue
        if cached_pred is None or row_idx - last_update_row >= update_interval:
            train_dates = valid.index[row_idx - train_window : row_idx]
            x_train = features.loc[train_dates].to_numpy(dtype=float)
            y_train = returns.loc[train_dates, list(tickers)].to_numpy(dtype=float)
            x_now = features.loc[date].to_numpy(dtype=float)
            preds = []
            mses = []
            for alpha in ridge_alphas:
                pred, mse = _ridge_predict(x_train, y_train, x_now, alpha)
                preds.append(pred)
                mses.append(max(mse, 1e-12))
            weights = np.asarray([1.0 / mse for mse in mses], dtype=float)
            weights = weights / weights.sum()
            cached_pred = np.sum(np.asarray(preds) * weights[:, None], axis=0) * horizon
            cached_update_date = pd.Timestamp(date)
            last_update_row = row_idx
        realized = _future_return(returns[list(tickers)], ret_pos, horizon)
        for ticker, pred_value in zip(tickers, cached_pred):
            if ticker not in realized:
                continue
            rows.append(
                {
                    "date": str(pd.Timestamp(date).date()),
                    "prior_update_date": str(cached_update_date.date()) if cached_update_date is not None else None,
                    "ticker": ticker,
                    "predicted_horizon_return": float(pred_value),
                    "realized_horizon_return": float(realized[ticker]),
                }
            )
    return rows


def build_review(
    *,
    db_path: Path = DB_PATH,
    start: str = "2018-01-02",
    end: str = "latest",
    tickers: tuple[str, ...] = CORE_TICKERS,
    train_window: int = 252,
    horizon: int = 20,
    eval_step: int = 5,
    daily_update_interval: int = 1,
    weekly_update_interval: int = 5,
    monthly_update_interval: int = 21,
    ridge_alphas: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0),
    min_prediction_dates: int = 80,
    forward_monitor_path: Path = DEFAULT_FORWARD_MONITOR,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
    else:
        close = _load_close(db_path, tickers, start, str(end_resolved)).ffill(limit=3)
    if close.empty:
        blockers.append("price_panel_missing")
        returns = pd.DataFrame()
    else:
        returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna(how="all")
    if len(returns) < train_window + horizon + 30:
        blockers.append("insufficient_history_for_cadence_review")
    features = _har_features(returns).replace([np.inf, -np.inf], np.nan) if not returns.empty else pd.DataFrame()
    daily_rows: list[dict[str, Any]] = []
    weekly_rows: list[dict[str, Any]] = []
    monthly_rows: list[dict[str, Any]] = []
    if not blockers:
        daily_rows = _prediction_rows(
            returns=returns,
            features=features,
            tickers=tickers,
            train_window=train_window,
            horizon=horizon,
            eval_step=eval_step,
            update_interval=daily_update_interval,
            ridge_alphas=ridge_alphas,
        )
        weekly_rows = _prediction_rows(
            returns=returns,
            features=features,
            tickers=tickers,
            train_window=train_window,
            horizon=horizon,
            eval_step=eval_step,
            update_interval=weekly_update_interval,
            ridge_alphas=ridge_alphas,
        )
        monthly_rows = _prediction_rows(
            returns=returns,
            features=features,
            tickers=tickers,
            train_window=train_window,
            horizon=horizon,
            eval_step=eval_step,
            update_interval=monthly_update_interval,
            ridge_alphas=ridge_alphas,
        )
    daily_metrics = _score_predictions(daily_rows) if daily_rows else {}
    weekly_metrics = _score_predictions(weekly_rows) if weekly_rows else {}
    monthly_metrics = _score_predictions(monthly_rows) if monthly_rows else {}
    if daily_metrics.get("prediction_dates", 0) < min_prediction_dates and not blockers:
        blockers.append("insufficient_daily_prediction_dates")
    if weekly_metrics.get("prediction_dates", 0) < min_prediction_dates and not blockers:
        blockers.append("insufficient_weekly_prediction_dates")
    if monthly_metrics.get("prediction_dates", 0) < min_prediction_dates and not blockers:
        blockers.append("insufficient_monthly_prediction_dates")
    daily_ic = daily_metrics.get("mean_daily_cross_sectional_rank_ic")
    weekly_ic = weekly_metrics.get("mean_daily_cross_sectional_rank_ic")
    monthly_ic = monthly_metrics.get("mean_daily_cross_sectional_rank_ic")
    daily_econ = daily_metrics.get("mean_top_minus_bottom_realized_return")
    weekly_econ = weekly_metrics.get("mean_top_minus_bottom_realized_return")
    monthly_econ = monthly_metrics.get("mean_top_minus_bottom_realized_return")
    weekly_rank_ic_delta = None if daily_ic is None or weekly_ic is None else float(weekly_ic) - float(daily_ic)
    weekly_econ_delta = None if daily_econ is None or weekly_econ is None else float(weekly_econ) - float(daily_econ)
    rank_ic_delta = None if daily_ic is None or monthly_ic is None else float(monthly_ic) - float(daily_ic)
    econ_delta = None if daily_econ is None or monthly_econ is None else float(monthly_econ) - float(daily_econ)
    weekly_acceptable = bool(
        not blockers
        and weekly_rank_ic_delta is not None
        and weekly_rank_ic_delta >= -0.02
        and weekly_econ_delta is not None
        and weekly_econ_delta >= -0.005
    )
    monthly_acceptable = bool(
        not blockers
        and rank_ic_delta is not None
        and rank_ic_delta >= -0.03
        and econ_delta is not None
        and econ_delta >= -0.01
    )
    if weekly_acceptable:
        warnings.append("weekly_cadence_not_materially_worse_than_daily_refresh")
    elif not blockers:
        warnings.append("weekly_cadence_materially_worse_or_unstable")
    if monthly_acceptable:
        warnings.append("monthly_cadence_not_materially_worse_than_daily_refresh")
    elif not blockers:
        warnings.append("monthly_cadence_materially_worse_or_unstable")
    forward_monitor = _load_json(_resolve(forward_monitor_path))
    live_signal = forward_monitor.get("live_signal") if isinstance(forward_monitor.get("live_signal"), dict) else {}
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_monthly_update_cadence_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_monitoring",
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "asynchronous_bavar_update_cadence",
            "not_imported": ["full_BAVAR_600_model_threaded_runtime", "TD3_training_loop", "live_optimizer_update_schedule"],
        },
        "parameters": {
            "tickers": list(tickers),
            "start": start,
            "end": str(end_resolved),
            "train_window": train_window,
            "horizon": horizon,
            "eval_step": eval_step,
            "daily_update_interval": daily_update_interval,
            "weekly_update_interval": weekly_update_interval,
            "monthly_update_interval": monthly_update_interval,
            "ridge_alphas": list(ridge_alphas),
        },
        "latest_a2118_context": {
            "strategy_id": live_signal.get("strategy_id"),
            "target_weights": live_signal.get("target_weights"),
            "market_state": live_signal.get("market_state"),
        },
        "cadence_comparison": {
            "daily_refresh": daily_metrics,
            "weekly_hold_last_prior": weekly_metrics,
            "monthly_hold_last_prior": monthly_metrics,
            "weekly_minus_daily_rank_ic": _float(weekly_rank_ic_delta),
            "weekly_minus_daily_top_minus_bottom_realized_return": _float(weekly_econ_delta),
            "monthly_minus_daily_rank_ic": _float(rank_ic_delta),
            "monthly_minus_daily_top_minus_bottom_realized_return": _float(econ_delta),
        },
        "decision": {
            "weekly_update_cadence_acceptable_for_shadow": weekly_acceptable,
            "monthly_update_cadence_acceptable_for_shadow": monthly_acceptable,
            "use_daily_refresh_for_live_trading": False,
            "use_weekly_refresh_for_live_trading": False,
            "use_monthly_refresh_for_live_trading": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "Cadence review only compares shadow refresh frequency; it does not authorize a live optimizer or live schedule.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_review(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_monthly_update_cadence_review_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--train-window", type=int, default=252)
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--eval-step", type=int, default=5)
    parser.add_argument("--weekly-update-interval", type=int, default=5)
    parser.add_argument("--monthly-update-interval", type=int, default=21)
    parser.add_argument("--ridge-alphas", default="0.1,1,10,100")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_review(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        train_window=args.train_window,
        horizon=args.horizon,
        eval_step=args.eval_step,
        weekly_update_interval=args.weekly_update_interval,
        monthly_update_interval=args.monthly_update_interval,
        ridge_alphas=tuple(float(item.strip()) for item in args.ridge_alphas.split(",") if item.strip()),
    )
    write_review(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
