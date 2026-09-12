#!/usr/bin/env python3
"""Build a 2606.09104 HAR horizon-extension review for GroupA+.

The paper uses 1/5/22-day HAR features and lists longer horizons as future
work. This shadow compares fixed HAR horizon sets to see whether longer cycles
improve OOS prior ranking value. It never changes A21.18 weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

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
    _load_close,
    _load_json,
    _ridge_predict,
    _score_predictions,
)
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_har_horizon_extension_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_har_horizon_extension_review/history"
DEFAULT_HORIZON_SETS = {
    "paper_1_5_22": (1, 5, 22),
    "quarterly_1_5_22_63": (1, 5, 22, 63),
    "yearly_1_5_22_63_252": (1, 5, 22, 63, 252),
}


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


def _har_features_for_horizons(returns: pd.DataFrame, horizons: tuple[int, ...]) -> pd.DataFrame:
    frames = []
    for ticker in returns.columns:
        r = returns[ticker].shift(1)
        data = {f"{ticker}__h{horizon}": r if horizon == 1 else r.rolling(horizon).mean() for horizon in horizons}
        frames.append(pd.DataFrame(data, index=returns.index))
    return pd.concat(frames, axis=1)


def _run_horizon_set(
    *,
    returns: pd.DataFrame,
    features: pd.DataFrame,
    tickers: tuple[str, ...],
    train_window: int,
    horizon: int,
    step: int,
    ridge_alphas: tuple[float, ...],
) -> list[dict[str, Any]]:
    valid = pd.concat([features, returns], axis=1).dropna()
    date_to_pos = {date: idx for idx, date in enumerate(returns.index)}
    rows: list[dict[str, Any]] = []
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
        pred_horizon = np.sum(np.asarray(preds) * weights[:, None], axis=0) * horizon
        realized = _future_return(returns[list(tickers)], ret_pos, horizon)
        for ticker, pred_value in zip(tickers, pred_horizon):
            if ticker not in realized:
                continue
            rows.append(
                {
                    "date": str(pd.Timestamp(date).date()),
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
    if len(returns) < train_window + max(max(v) for v in DEFAULT_HORIZON_SETS.values()) + horizon + 30:
        blockers.append("insufficient_history_for_horizon_extension")

    reviews: list[dict[str, Any]] = []
    if not blockers:
        for name, horizons in DEFAULT_HORIZON_SETS.items():
            features = _har_features_for_horizons(returns, horizons).replace([np.inf, -np.inf], np.nan)
            rows = _run_horizon_set(
                returns=returns,
                features=features,
                tickers=tickers,
                train_window=train_window,
                horizon=horizon,
                step=step,
                ridge_alphas=ridge_alphas,
            )
            metrics = _score_predictions(rows)
            if metrics.get("prediction_dates", 0) < min_prediction_dates:
                blockers.append(f"insufficient_prediction_dates:{name}")
            has_value = bool(
                metrics.get("mean_daily_cross_sectional_rank_ic") is not None
                and float(metrics.get("mean_daily_cross_sectional_rank_ic") or 0.0) > 0.05
                and float(metrics.get("mean_top_minus_bottom_realized_return") or 0.0) > 0.0
            )
            reviews.append(
                {
                    "horizon_set": name,
                    "horizons": list(horizons),
                    "oos_prior_quality": metrics,
                    "has_oos_economic_value": has_value,
                }
            )
    best = None
    if reviews:
        best = max(
            reviews,
            key=lambda row: float(row["oos_prior_quality"].get("mean_top_minus_bottom_realized_return") or -999.0),
        )
    horizon_extension_improves = bool(
        best
        and best["horizon_set"] != "paper_1_5_22"
        and float(best["oos_prior_quality"].get("mean_top_minus_bottom_realized_return") or 0.0) > 0.0
    )
    if not horizon_extension_improves and not blockers:
        warnings.append("longer_har_horizons_do_not_create_positive_economic_value")
    forward_monitor = _load_json(_resolve(forward_monitor_path))
    live_signal = forward_monitor.get("live_signal") if isinstance(forward_monitor.get("live_signal"), dict) else {}
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_har_horizon_extension_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_monitoring",
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "HAR_horizon_extension_future_work",
            "not_imported": ["BAVAR_BLED_TD3_optimizer", "short_selling", "unconstrained_weight_generation"],
        },
        "parameters": {
            "start": start,
            "end": str(end_resolved),
            "tickers": list(tickers),
            "train_window": train_window,
            "horizon": horizon,
            "step": step,
            "ridge_alphas": list(ridge_alphas),
        },
        "latest_a2118_context": {
            "strategy_id": live_signal.get("strategy_id"),
            "target_weights": live_signal.get("target_weights"),
            "market_state": live_signal.get("market_state"),
        },
        "horizon_reviews": reviews,
        "best_horizon_set_by_economic_value": best["horizon_set"] if best else None,
        "decision": {
            "har_horizon_extension_improves_economic_value": horizon_extension_improves,
            "promote_extended_har_prior_to_live": False,
            "train_td3_or_bavar_bled_optimizer_now": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "Longer HAR horizons are reviewed as shadow prior features only; they cannot alter weights.",
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
    (history_dir / f"2606_09104_har_horizon_extension_review_{as_of.replace('-', '')}.json").write_text(
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
    report = build_review(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        train_window=args.train_window,
        horizon=args.horizon,
        step=args.step,
        ridge_alphas=tuple(float(item.strip()) for item in args.ridge_alphas.split(",") if item.strip()),
    )
    write_review(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
