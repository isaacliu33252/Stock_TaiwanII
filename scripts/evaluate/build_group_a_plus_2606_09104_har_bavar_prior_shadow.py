#!/usr/bin/env python3
"""Build a 2606.09104 HAR-BAVAR prior shadow for GroupA+.

This imports the paper's regime-aware BAVAR prior idea without importing the
full short-enabled BAVAR-BLED/TD3 optimizer. It evaluates whether a fixed HAR
ridge/likelihood ensemble has OOS ranking information for core GroupA+ assets.
It never changes A21.18 weights.
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
from scripts.evaluate.build_group_a_plus_2411_19649_semicovariance_review import _load_json  # noqa: E402
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


CORE_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_har_bavar_prior_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_har_bavar_prior_shadow/history"
DEFAULT_FORWARD_MONITOR = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_forward_shadow_monitor.json"


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


def _load_close(db_path: Path, tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
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
        return pd.DataFrame()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.pivot_table(index="dt", columns="ticker", values="close", aggfunc="last").sort_index()


def _har_features(returns: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for ticker in returns.columns:
        r = returns[ticker]
        frames.append(
            pd.DataFrame(
                {
                    f"{ticker}__d1": r.shift(1),
                    f"{ticker}__w5": r.shift(1).rolling(5).mean(),
                    f"{ticker}__m22": r.shift(1).rolling(22).mean(),
                },
                index=returns.index,
            )
        )
    return pd.concat(frames, axis=1)


def _ridge_predict(x_train: np.ndarray, y_train: np.ndarray, x_now: np.ndarray, alpha: float) -> tuple[np.ndarray, float]:
    x = np.column_stack([np.ones(len(x_train)), x_train])
    now = np.r_[1.0, x_now]
    penalty = np.eye(x.shape[1]) * alpha
    penalty[0, 0] = 0.0
    beta = np.linalg.pinv(x.T @ x + penalty) @ x.T @ y_train
    pred = now @ beta
    resid = y_train - x @ beta
    mse = float(np.nanmean(resid * resid))
    return np.asarray(pred, dtype=float), mse


def _future_return(returns: pd.DataFrame, start_idx: int, horizon: int) -> pd.Series:
    future = returns.iloc[start_idx + 1 : start_idx + 1 + horizon]
    if len(future) < horizon:
        return pd.Series(dtype=float)
    return (1.0 + future).prod() - 1.0


def _rank_ic(pred: pd.Series, realized: pd.Series) -> float | None:
    joined = pd.concat([pred, realized], axis=1).dropna()
    if len(joined) < 3:
        return None
    return _float(joined.iloc[:, 0].rank().corr(joined.iloc[:, 1].rank()))


def _direction_accuracy(pred: pd.Series, realized: pd.Series) -> float | None:
    joined = pd.concat([pred, realized], axis=1).dropna()
    if joined.empty:
        return None
    return _float(float((np.sign(joined.iloc[:, 0]) == np.sign(joined.iloc[:, 1])).mean()))


def _score_predictions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    rank_ics = []
    dir_acc = []
    top_minus_bottom = []
    for _, group in df.groupby("date"):
        pred = group.set_index("ticker")["predicted_horizon_return"]
        realized = group.set_index("ticker")["realized_horizon_return"]
        ic = _rank_ic(pred, realized)
        if ic is not None:
            rank_ics.append(ic)
        acc = _direction_accuracy(pred, realized)
        if acc is not None:
            dir_acc.append(acc)
        if len(group) >= 2:
            ordered = group.sort_values("predicted_horizon_return")
            top_minus_bottom.append(float(ordered.iloc[-1]["realized_horizon_return"] - ordered.iloc[0]["realized_horizon_return"]))
    return {
        "prediction_rows": int(len(df)),
        "prediction_dates": int(df["date"].nunique()),
        "mean_daily_cross_sectional_rank_ic": _float(np.nanmean(rank_ics)) if rank_ics else None,
        "median_daily_cross_sectional_rank_ic": _float(np.nanmedian(rank_ics)) if rank_ics else None,
        "mean_direction_accuracy": _float(np.nanmean(dir_acc)) if dir_acc else None,
        "mean_top_minus_bottom_realized_return": _float(np.nanmean(top_minus_bottom)) if top_minus_bottom else None,
    }


def _infer_current_target(forward_monitor: dict[str, Any]) -> dict[str, Any]:
    live_signal = forward_monitor.get("live_signal") if isinstance(forward_monitor.get("live_signal"), dict) else {}
    return {
        "strategy_id": live_signal.get("strategy_id"),
        "target_weights": live_signal.get("target_weights") if isinstance(live_signal.get("target_weights"), dict) else {},
        "market_state": live_signal.get("market_state") if isinstance(live_signal.get("market_state"), dict) else {},
        "execution_regime": live_signal.get("execution_regime"),
    }


def build_shadow(
    *,
    db_path: Path = DB_PATH,
    start: str = "2018-01-02",
    end: str = "latest",
    tickers: tuple[str, ...] = CORE_TICKERS,
    train_window: int = 252,
    horizon: int = 20,
    step: int = 5,
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
        blockers.append("insufficient_history_for_har_bavar_shadow")
    features = _har_features(returns).replace([np.inf, -np.inf], np.nan) if not returns.empty else pd.DataFrame()
    prediction_rows: list[dict[str, Any]] = []
    latest_prior: dict[str, Any] = {}
    if not blockers:
        valid = pd.concat([features, returns], axis=1).dropna()
        date_to_pos = {date: idx for idx, date in enumerate(returns.index)}
        for row_idx in range(train_window, len(valid) - horizon, step):
            date = valid.index[row_idx]
            ret_pos = date_to_pos.get(date)
            if ret_pos is None or ret_pos + horizon >= len(returns):
                continue
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
            pred_daily = np.sum(np.asarray(preds) * weights[:, None], axis=0)
            pred_horizon = pred_daily * horizon
            realized = _future_return(returns[list(tickers)], ret_pos, horizon)
            for ticker, pred_value in zip(tickers, pred_horizon):
                if ticker not in realized:
                    continue
                prediction_rows.append(
                    {
                        "date": str(pd.Timestamp(date).date()),
                        "ticker": ticker,
                        "predicted_horizon_return": float(pred_value),
                        "realized_horizon_return": float(realized[ticker]),
                    }
                )
        if len(prediction_rows) == 0:
            blockers.append("no_oos_predictions_created")
        if prediction_rows:
            latest_date = max(row["date"] for row in prediction_rows)
            latest_sample = [row for row in prediction_rows if row["date"] == latest_date]
            latest_prior = {
                "date": latest_date,
                "asset_priors": sorted(
                    [
                        {
                            "ticker": row["ticker"],
                            "predicted_20d_return": _float(row["predicted_horizon_return"]),
                            "realized_20d_return": _float(row["realized_horizon_return"]),
                        }
                        for row in latest_sample
                    ],
                    key=lambda x: float(x["predicted_20d_return"] or 0.0),
                    reverse=True,
                ),
            }
    metrics = _score_predictions(prediction_rows) if prediction_rows else {}
    if metrics.get("prediction_dates", 0) < min_prediction_dates and not blockers:
        blockers.append("insufficient_oos_prediction_dates")
    rank_ic = metrics.get("mean_daily_cross_sectional_rank_ic")
    has_oos_value = bool(rank_ic is not None and rank_ic > 0.05 and metrics.get("mean_top_minus_bottom_realized_return", 0.0) > 0)
    if not has_oos_value and not blockers:
        warnings.append("har_bavar_prior_oos_value_weak_or_absent")
    forward_monitor = _load_json(_resolve(forward_monitor_path))
    current_context = _infer_current_target(forward_monitor)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_har_bavar_prior_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_optimizer_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_monitoring",
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "HAR_BAVAR_regime_aware_prior",
            "not_imported": ["short_selling", "fractional_share_optimizer", "BAVAR_BLED_TD3_live_optimizer", "zero_slippage_assumption"],
        },
        "guardrails": {
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "short_selling_allowed": False,
            "unconstrained_black_litterman_optimizer_allowed": False,
            "forbid_simultaneous_00631l_00632r_offset": True,
        },
        "parameters": {
            "tickers": list(tickers),
            "start": start,
            "end": str(end_resolved),
            "train_window": train_window,
            "horizon": horizon,
            "step": step,
            "ridge_alphas": list(ridge_alphas),
            "min_prediction_dates": min_prediction_dates,
        },
        "coverage": {
            "return_observations": int(len(returns)),
            "prediction_rows": int(len(prediction_rows)),
            "prediction_dates": int(metrics.get("prediction_dates", 0) or 0),
        },
        "latest_a2118_context": current_context,
        "oos_prior_quality": metrics,
        "latest_prior_snapshot": latest_prior,
        "decision": {
            "har_bavar_prior_has_oos_ranking_value": has_oos_value,
            "use_as_regime_prior_shadow": bool(not blockers),
            "advance_to_bavar_model_weight_drift_monitor": has_oos_value,
            "advance_to_bled_tail_adjustment_review": True,
            "train_td3_or_bavar_bled_optimizer_now": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "HAR-BAVAR prior is evaluated only as a shadow information source; it cannot override A21.18 targets.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_shadow(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_har_bavar_prior_shadow_{as_of.replace('-', '')}.json").write_text(
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
    parser.add_argument("--step", type=int, default=5)
    parser.add_argument("--ridge-alphas", default="0.1,1,10,100")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_shadow(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        train_window=args.train_window,
        horizon=args.horizon,
        step=args.step,
        ridge_alphas=tuple(float(item.strip()) for item in args.ridge_alphas.split(",") if item.strip()),
    )
    write_shadow(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
