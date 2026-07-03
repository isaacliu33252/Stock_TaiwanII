#!/usr/bin/env python3
"""Purged walk-forward stock ranking and top-k backtest.

Builds a cross-sectional panel from OHLCV, optional industry mapping, and
optional LLM sentiment features. The model predicts next-1d or next-3d forward
returns, ranks tickers by predicted return, and evaluates equal-weight top-k
selection on purged walk-forward folds.
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
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_squared_error

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.integrations.llm_sentiment_features import attach_llm_sentiment_features
from group_a_plus.validation.purged_walk_forward import PurgedWalkForwardSplit
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "stock_ranking_walkforward_latest.json"
DEFAULT_SELECTIONS = PROJECT_ROOT / "results" / "stock_ranking_walkforward_selections_latest.csv"
DEFAULT_CURVE = PROJECT_ROOT / "results" / "stock_ranking_walkforward_curve_latest.csv"
LABEL_COLUMNS = {"date", "ticker", "target_return", "forward_return", "next_return"}


def _normalise_ticker(ticker: str) -> str:
    ticker = str(ticker).strip()
    return ticker if "." in ticker else f"{ticker}.TW"


def parse_tickers(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    values = [_normalise_ticker(item) for item in raw.split(",") if item.strip()]
    return values or None


def load_ohlcv(
    db_path: Path,
    *,
    tickers: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    min_rows: int = 120,
    exclude_tickers: set[str] | None = None,
) -> pd.DataFrame:
    clauses = []
    params: list[Any] = []
    if tickers:
        clauses.append("ticker IN ({})".format(",".join(["?"] * len(tickers))))
        params.extend(tickers)
    if start:
        clauses.append("dt >= ?")
        params.append(start)
    if end:
        clauses.append("dt <= ?")
        params.append(end)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        frame = con.execute(
            f"""
            SELECT ticker, dt AS date, open, high, low, close, volume,
                   coalesce(dividends, 0.0) AS dividends
            FROM ohlcv
            {where}
            ORDER BY ticker, dt
            """,
            params,
        ).fetchdf()
    finally:
        con.close()
    if frame.empty:
        raise ValueError("no OHLCV rows loaded")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["date"]).sort_values(["ticker", "date"])
    if exclude_tickers:
        frame = frame[~frame["ticker"].isin(exclude_tickers)]
    counts = frame.groupby("ticker")["date"].count()
    keep = counts[counts >= min_rows].index
    frame = frame[frame["ticker"].isin(keep)].reset_index(drop=True)
    if frame.empty:
        raise ValueError("no tickers left after min_rows filter")
    return frame


def _load_industry_map(path: Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame(columns=["ticker", "industry"])
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if not {"ticker", "industry"}.issubset(frame.columns):
        raise ValueError("industry map must contain ticker and industry columns")
    out = frame[["ticker", "industry"]].copy()
    out["ticker"] = out["ticker"].map(_normalise_ticker)
    out["industry"] = out["industry"].astype(str)
    return out.drop_duplicates("ticker")


def _safe_pct(series: pd.Series, periods: int) -> pd.Series:
    return series.pct_change(periods).replace([np.inf, -np.inf], np.nan)


def build_feature_panel(
    ohlcv: pd.DataFrame,
    *,
    horizon: int = 1,
    market_ticker: str = "0050.TW",
    industry_map: pd.DataFrame | None = None,
    llm_sentiment_path: Path | None = None,
) -> pd.DataFrame:
    if horizon not in {1, 3}:
        raise ValueError("horizon must be 1 or 3")
    frame = ohlcv.copy().sort_values(["ticker", "date"])
    numeric_cols = ["open", "high", "low", "close", "volume", "dividends"]
    frame[numeric_cols] = frame[numeric_cols].apply(pd.to_numeric, errors="coerce")
    grouped = frame.groupby("ticker", group_keys=False)

    frame["ret_1d"] = grouped["close"].pct_change(1)
    for window in (3, 5, 10, 20, 60):
        frame[f"ret_{window}d"] = grouped["close"].pct_change(window)
    for window in (5, 20, 60):
        ma = grouped["close"].transform(lambda s: s.rolling(window, min_periods=max(3, window // 3)).mean())
        frame[f"ma_gap_{window}d"] = frame["close"].div(ma).sub(1.0)
    frame["volatility_20d"] = grouped["ret_1d"].transform(lambda s: s.rolling(20, min_periods=5).std())
    vol_mean = grouped["volume"].transform(lambda s: s.rolling(20, min_periods=5).mean())
    vol_std = grouped["volume"].transform(lambda s: s.rolling(20, min_periods=5).std())
    frame["volume_z_20d"] = (frame["volume"] - vol_mean).div(vol_std.replace(0.0, np.nan))
    frame["volume_chg_5d"] = grouped["volume"].pct_change(5)
    frame["intraday_range"] = frame["high"].sub(frame["low"]).div(frame["close"].replace(0.0, np.nan))
    frame["open_gap"] = frame["open"].div(grouped["close"].shift(1)).sub(1.0)
    frame["dollar_volume"] = frame["close"] * frame["volume"]
    frame["dividend_yield_event"] = frame["dividends"].div(frame["close"].replace(0.0, np.nan)).fillna(0.0)
    frame["next_return"] = grouped["close"].shift(-1).div(frame["close"]).sub(1.0)
    frame["forward_return"] = grouped["close"].shift(-horizon).div(frame["close"]).sub(1.0)
    frame["target_return"] = frame["forward_return"]

    market = frame[frame["ticker"] == market_ticker][["date", "close", "volume"]].copy()
    if not market.empty:
        market = market.sort_values("date")
        market["market_ret_1d"] = market["close"].pct_change(1)
        market["market_ret_5d"] = market["close"].pct_change(5)
        market["market_ret_20d"] = market["close"].pct_change(20)
        market["market_volatility_20d"] = market["market_ret_1d"].rolling(20, min_periods=5).std()
        market["market_volume_z_20d"] = (
            (market["volume"] - market["volume"].rolling(20, min_periods=5).mean())
            / market["volume"].rolling(20, min_periods=5).std().replace(0.0, np.nan)
        )
        frame = frame.merge(
            market[["date", "market_ret_1d", "market_ret_5d", "market_ret_20d", "market_volatility_20d", "market_volume_z_20d"]],
            on="date",
            how="left",
        )

    for col in ("ret_5d", "ret_20d", "volatility_20d", "volume_z_20d", "dollar_volume"):
        frame[f"cs_rank_{col}"] = frame.groupby("date")[col].rank(pct=True)

    if industry_map is not None and not industry_map.empty:
        frame = frame.merge(industry_map, on="ticker", how="left")
        frame["industry"] = frame["industry"].fillna("UNKNOWN")
        industry_ret = (
            frame.groupby(["date", "industry"], as_index=False)["ret_1d"]
            .mean()
            .rename(columns={"ret_1d": "industry_ret_1d"})
        )
        industry_ret["industry_ret_5d"] = (
            industry_ret.sort_values(["industry", "date"])
            .groupby("industry")["industry_ret_1d"]
            .transform(lambda s: (1.0 + s).rolling(5, min_periods=2).apply(np.prod, raw=True) - 1.0)
        )
        frame = frame.merge(industry_ret, on=["date", "industry"], how="left")
        frame["industry_relative_ret_5d"] = frame["ret_5d"] - frame["industry_ret_5d"]

    if llm_sentiment_path is not None:
        frame = attach_llm_sentiment_features(frame, llm_sentiment_path, date_column="date", lag_days=1)

    feature_cols = [col for col in frame.columns if col not in {"industry"} | LABEL_COLUMNS]
    frame[feature_cols] = frame[feature_cols].replace([np.inf, -np.inf], np.nan)
    frame = frame.dropna(subset=["target_return", "next_return"])
    numeric_features = [
        col for col in feature_cols
        if col not in {"ticker"} and pd.api.types.is_numeric_dtype(frame[col])
    ]
    frame[numeric_features] = frame[numeric_features].fillna(0.0)
    return frame.reset_index(drop=True)


def _feature_columns(panel: pd.DataFrame) -> list[str]:
    cols = []
    for col in panel.columns:
        if col in LABEL_COLUMNS or col in {"industry"}:
            continue
        if col == "date":
            continue
        if pd.api.types.is_numeric_dtype(panel[col]):
            cols.append(col)
    if not cols:
        raise ValueError("panel has no numeric feature columns")
    return cols


def _make_model(random_state: int = 42):
    try:
        from lightgbm import LGBMRegressor

        return LGBMRegressor(
            n_estimators=160,
            learning_rate=0.035,
            num_leaves=15,
            min_child_samples=20,
            subsample=0.9,
            colsample_bytree=0.9,
            reg_lambda=0.2,
            random_state=random_state,
            verbosity=-1,
        ), "lightgbm"
    except Exception:
        return HistGradientBoostingRegressor(
            max_iter=160,
            learning_rate=0.035,
            max_leaf_nodes=15,
            l2_regularization=0.1,
            random_state=random_state,
        ), "hist_gradient_boosting_fallback"


def _rank_ic(scores: pd.Series, returns: pd.Series) -> float | None:
    valid = pd.DataFrame({"score": scores, "ret": returns}).dropna()
    if len(valid) < 3 or valid["score"].nunique() < 2 or valid["ret"].nunique() < 2:
        return None
    return float(valid["score"].corr(valid["ret"], method="spearman"))


def _portfolio_metrics(curve: pd.DataFrame, *, rebalance_every: int) -> dict[str, float]:
    if curve.empty:
        return {}
    values = curve["portfolio_value"].astype(float)
    returns = values.pct_change().dropna()
    years = max((pd.to_datetime(curve["date"].iloc[-1]) - pd.to_datetime(curve["date"].iloc[0])).days / 365.25, 1e-9)
    periods_per_year = 252.0 / max(float(rebalance_every), 1.0)
    vol = float(returns.std() * math.sqrt(periods_per_year)) if len(returns) > 1 else 0.0
    sharpe = float(returns.mean() / returns.std() * math.sqrt(periods_per_year)) if len(returns) > 1 and returns.std() > 0 else 0.0
    return {
        "final_value": float(values.iloc[-1]),
        "total_return": float(values.iloc[-1] / values.iloc[0] - 1.0),
        "annual_return": float((values.iloc[-1] / values.iloc[0]) ** (1.0 / years) - 1.0),
        "volatility": vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": float((values / values.cummax() - 1.0).min()),
        "worst_period_return": float(returns.min()) if len(returns) else 0.0,
    }


def _selection_turnover(selected: list[str], previous: list[str], top_k: int) -> float:
    if not previous:
        return 1.0
    current_w = {ticker: 1.0 / top_k for ticker in selected}
    previous_w = {ticker: 1.0 / top_k for ticker in previous}
    tickers = set(current_w) | set(previous_w)
    return float(sum(abs(current_w.get(t, 0.0) - previous_w.get(t, 0.0)) for t in tickers))


def run_walkforward_ranking(
    panel: pd.DataFrame,
    *,
    horizon: int = 1,
    top_k: int = 5,
    n_splits: int = 4,
    test_size: int | None = None,
    train_size: int | None = None,
    purge: int | None = None,
    min_train_dates: int = 120,
    rebalance_every: int | None = None,
    initial_value: float = 1_000_000.0,
    cost_rate: float = 0.0025,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    if top_k < 1:
        raise ValueError("top_k must be >= 1")
    rebalance_every = int(rebalance_every or horizon)
    purge = horizon if purge is None else int(purge)
    feature_cols = _feature_columns(panel)
    dates = pd.Series(sorted(pd.to_datetime(panel["date"]).dropna().unique()))
    splitter = PurgedWalkForwardSplit(
        n_splits=n_splits,
        test_size=test_size,
        train_size=train_size,
        purge=purge,
        min_train_size=min_train_dates,
    )

    fold_rows: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    curve_rows: list[dict[str, Any]] = []
    value = float(initial_value)
    benchmark_value = float(initial_value)
    previous_selected: list[str] = []
    model_kind = "unknown"
    all_ic: list[float] = []

    for fold, (train_date_idx, test_date_idx) in enumerate(splitter.split(dates), start=1):
        train_dates = set(dates.iloc[train_date_idx])
        test_dates = list(dates.iloc[test_date_idx])
        train = panel[panel["date"].isin(train_dates)].copy()
        test = panel[panel["date"].isin(test_dates)].copy()
        model, model_kind = _make_model(random_state=900 + fold)
        model.fit(train[feature_cols], train["target_return"])
        test = test.copy()
        test["score"] = model.predict(test[feature_cols])
        mse = float(mean_squared_error(test["target_return"], test["score"]))

        date_ics: list[float] = []
        rebalance_dates = test_dates[::rebalance_every]
        for dt in test_dates:
            day = test[test["date"] == dt]
            ic = _rank_ic(day["score"], day["target_return"])
            if ic is not None:
                date_ics.append(ic)
                all_ic.append(ic)

        for dt in rebalance_dates:
            day = test[test["date"] == dt].sort_values("score", ascending=False)
            if len(day) < top_k:
                continue
            top = day.head(top_k).copy()
            selected = top["ticker"].astype(str).tolist()
            turnover = _selection_turnover(selected, previous_selected, top_k)
            gross_return = float(top["target_return"].mean())
            net_return = gross_return - turnover * cost_rate
            universe_return = float(day["target_return"].mean())
            value *= 1.0 + net_return
            benchmark_value *= 1.0 + universe_return
            previous_selected = selected
            curve_rows.append(
                {
                    "date": pd.Timestamp(dt),
                    "fold": fold,
                    "portfolio_value": value,
                    "benchmark_value": benchmark_value,
                    "gross_return": gross_return,
                    "net_return": net_return,
                    "universe_return": universe_return,
                    "turnover": turnover,
                }
            )
            for rank, row in enumerate(top.itertuples(index=False), start=1):
                selections.append(
                    {
                        "date": pd.Timestamp(dt),
                        "fold": fold,
                        "rank": rank,
                        "ticker": row.ticker,
                        "score": float(row.score),
                        "realized_return": float(row.target_return),
                    }
                )

        fold_rows.append(
            {
                "fold": fold,
                "train_start": str(pd.Timestamp(dates.iloc[train_date_idx[0]]).date()),
                "train_end": str(pd.Timestamp(dates.iloc[train_date_idx[-1]]).date()),
                "test_start": str(pd.Timestamp(dates.iloc[test_date_idx[0]]).date()),
                "test_end": str(pd.Timestamp(dates.iloc[test_date_idx[-1]]).date()),
                "train_dates": int(len(train_date_idx)),
                "test_dates": int(len(test_date_idx)),
                "train_rows": int(len(train)),
                "test_rows": int(len(test)),
                "mse": mse,
                "mean_rank_ic": float(np.mean(date_ics)) if date_ics else None,
                "rebalance_count": int(len(rebalance_dates)),
            }
        )

    curve = pd.DataFrame(curve_rows)
    selection_frame = pd.DataFrame(selections)
    metrics = _portfolio_metrics(curve, rebalance_every=rebalance_every)
    if not curve.empty:
        benchmark_curve = curve[["date", "benchmark_value"]].rename(columns={"benchmark_value": "portfolio_value"})
        benchmark_metrics = _portfolio_metrics(benchmark_curve, rebalance_every=rebalance_every)
    else:
        benchmark_metrics = {}
    report = {
        "model_kind": model_kind,
        "horizon": int(horizon),
        "top_k": int(top_k),
        "feature_count": int(len(feature_cols)),
        "feature_columns": feature_cols,
        "panel_rows": int(len(panel)),
        "ticker_count": int(panel["ticker"].nunique()),
        "date_count": int(panel["date"].nunique()),
        "validation": {
            "method": "purged_walk_forward_by_date",
            "n_splits": int(n_splits),
            "test_size": test_size,
            "train_size": train_size,
            "purge_dates": int(purge),
            "min_train_dates": int(min_train_dates),
        },
        "folds": fold_rows,
        "aggregate": {
            "mean_rank_ic": float(np.mean(all_ic)) if all_ic else None,
            "median_rank_ic": float(np.median(all_ic)) if all_ic else None,
            "selection_count": int(len(selection_frame)),
            "rebalance_count": int(len(curve)),
            "avg_turnover": float(curve["turnover"].mean()) if not curve.empty else None,
            "topk_metrics": metrics,
            "equal_weight_universe_metrics": benchmark_metrics,
            "delta_final_value_vs_universe": (
                float(metrics["final_value"] - benchmark_metrics["final_value"])
                if metrics and benchmark_metrics
                else None
            ),
        },
        "promotion_decision": "research_only",
    }
    return report, selection_frame, curve


def build_report(
    *,
    db_path: Path,
    tickers: list[str] | None,
    exclude_tickers: set[str] | None,
    start: str | None,
    end: str | None,
    horizon: int,
    top_k: int,
    market_ticker: str,
    industry_map_path: Path | None,
    llm_sentiment_path: Path | None,
    n_splits: int,
    test_size: int | None,
    train_size: int | None,
    purge: int | None,
    min_train_dates: int,
    rebalance_every: int | None,
    min_rows: int,
    initial_value: float,
    cost_rate: float,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    industry_map = _load_industry_map(industry_map_path)
    ohlcv = load_ohlcv(
        db_path,
        tickers=tickers,
        start=start,
        end=end,
        min_rows=min_rows,
        exclude_tickers=exclude_tickers,
    )
    panel = build_feature_panel(
        ohlcv,
        horizon=horizon,
        market_ticker=market_ticker,
        industry_map=industry_map,
        llm_sentiment_path=llm_sentiment_path,
    )
    report, selections, curve = run_walkforward_ranking(
        panel,
        horizon=horizon,
        top_k=top_k,
        n_splits=n_splits,
        test_size=test_size,
        train_size=train_size,
        purge=purge,
        min_train_dates=min_train_dates,
        rebalance_every=rebalance_every,
        initial_value=initial_value,
        cost_rate=cost_rate,
    )
    report.update(
        {
            "schema_version": 1,
            "report_type": "stock_ranking_walkforward",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": {
                "db": str(db_path),
                "tickers": tickers,
                "exclude_tickers": sorted(exclude_tickers or []),
                "start": start,
                "end": end,
                "market_ticker": market_ticker,
                "industry_map": str(industry_map_path) if industry_map_path else None,
                "llm_sentiment": str(llm_sentiment_path) if llm_sentiment_path else None,
                "current_db_warning": (
                    "This DB currently has a small ETF-heavy universe; load a broader stock OHLCV universe "
                    "and optional ticker/industry mapping before treating this as a production stock selector."
                ),
            },
            "active_allocation_impact": "none",
        }
    )
    return report, selections, curve


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--tickers", default=None, help="Comma-separated tickers; omitted means all DB tickers after min_rows filter")
    parser.add_argument("--exclude-tickers", default="wf,0050", help="Comma-separated tickers to remove from the universe")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--horizon", type=int, default=1, choices=(1, 3))
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--market-ticker", default="0050.TW")
    parser.add_argument("--industry-map", default=None, help="CSV with ticker,industry columns")
    parser.add_argument("--llm-sentiment", default=None, help="Daily LLM sentiment CSV")
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--test-size", type=int, default=None)
    parser.add_argument("--train-size", type=int, default=None)
    parser.add_argument("--purge", type=int, default=None)
    parser.add_argument("--min-train-dates", type=int, default=240)
    parser.add_argument("--min-rows", type=int, default=240)
    parser.add_argument("--rebalance-every", type=int, default=None)
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--cost-rate", type=float, default=0.0025)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--selections-output", default=str(DEFAULT_SELECTIONS))
    parser.add_argument("--curve-output", default=str(DEFAULT_CURVE))
    args = parser.parse_args()

    std = OutputStandardizer("evaluate_stock_ranking_walkforward")
    try:
        report, selections, curve = build_report(
            db_path=Path(args.db),
            tickers=parse_tickers(args.tickers),
            exclude_tickers=set(item.strip() for item in args.exclude_tickers.split(",") if item.strip()),
            start=args.start,
            end=args.end,
            horizon=args.horizon,
            top_k=args.top_k,
            market_ticker=args.market_ticker,
            industry_map_path=Path(args.industry_map) if args.industry_map else None,
            llm_sentiment_path=Path(args.llm_sentiment) if args.llm_sentiment else None,
            n_splits=args.n_splits,
            test_size=args.test_size,
            train_size=args.train_size,
            purge=args.purge,
            min_train_dates=args.min_train_dates,
            rebalance_every=args.rebalance_every,
            min_rows=args.min_rows,
            initial_value=args.initial_value,
            cost_rate=args.cost_rate,
        )
        Path(args.selections_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.curve_output).parent.mkdir(parents=True, exist_ok=True)
        selections.to_csv(args.selections_output, index=False, encoding="utf-8-sig")
        curve.to_csv(args.curve_output, index=False, encoding="utf-8-sig")
        payload = std.success(report, selections_output=args.selections_output, curve_output=args.curve_output)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Stock ranking WF report: {Path(args.output).resolve()}")
    print(f"Selections CSV: {Path(args.selections_output).resolve()}")
    print(f"Curve CSV: {Path(args.curve_output).resolve()}")


if __name__ == "__main__":
    main()
