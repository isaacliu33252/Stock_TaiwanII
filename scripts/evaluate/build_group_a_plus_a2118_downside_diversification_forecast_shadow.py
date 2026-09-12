#!/usr/bin/env python3
"""Build A21.18 downside-diversification forecast shadow.

Stage 2 tests whether simple semi-covariance forecasts have out-of-sample
value before considering DCC or deep models. It never changes live weights.
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
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


BASE = "0050.TW"
DEFENSIVE_ASSET = "00679B.TWO"
DEFAULT_FIFTH_CANDIDATES = ("0056.TW", "00713.TW", "00878.TW", "00646.TW")
DEFAULT_WINDOWS = (20, 60, 120)
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/a2118_downside_diversification_forecast_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/a2118_downside_diversification_forecast_shadow/history"


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


def _downside_stats(frame: pd.DataFrame, left: str, right: str, *, ewma_halflife: int | None = None) -> dict[str, float | None]:
    pair = frame[[left, right]].dropna()
    if len(pair) < 3:
        return {"semi_cov": None, "semi_corr": None}
    down = pair.clip(upper=0.0)
    if ewma_halflife is None:
        cov = (down[left] * down[right]).mean()
        var_l = (down[left] * down[left]).mean()
        var_r = (down[right] * down[right]).mean()
    else:
        age = np.arange(len(down) - 1, -1, -1, dtype=float)
        weights = np.exp(np.log(0.5) * age / float(ewma_halflife))
        weights = weights / weights.sum()
        cov = float(np.sum(weights * down[left].to_numpy() * down[right].to_numpy()))
        var_l = float(np.sum(weights * down[left].to_numpy() * down[left].to_numpy()))
        var_r = float(np.sum(weights * down[right].to_numpy() * down[right].to_numpy()))
    denom = float(np.sqrt(var_l * var_r)) if var_l > 0 and var_r > 0 else np.nan
    corr = cov / denom if np.isfinite(denom) and denom > 0 else np.nan
    return {"semi_cov": _float(cov, 10), "semi_corr": _float(corr)}


def _forecast(
    frame: pd.DataFrame,
    left: str,
    right: str,
    *,
    model: str,
    window: int,
    ewma_halflife: int,
    shrinkage_alpha: float,
) -> dict[str, float | None]:
    if model == "historical":
        return _downside_stats(frame.tail(window), left, right)
    if model == "ewma":
        return _downside_stats(frame.tail(window), left, right, ewma_halflife=ewma_halflife)
    if model == "shrinkage":
        hist = _downside_stats(frame.tail(window), left, right)
        return {
            "semi_cov": None if hist["semi_cov"] is None else _float((1.0 - shrinkage_alpha) * float(hist["semi_cov"]), 10),
            "semi_corr": None if hist["semi_corr"] is None else _float((1.0 - shrinkage_alpha) * float(hist["semi_corr"])),
        }
    raise ValueError(f"unknown model: {model}")


def _future_mdd(series: pd.Series) -> float | None:
    if series.empty:
        return None
    path = (1.0 + series).cumprod()
    path = pd.concat([pd.Series([1.0]), path], ignore_index=True)
    mdd = (path / path.cummax() - 1.0).min()
    return _float(mdd)


def _cum_return(series: pd.Series) -> float | None:
    clean = series.dropna()
    if clean.empty:
        return None
    return _float((1.0 + clean).prod() - 1.0)


def _state(predicted_semicorr: float | None, good_threshold: float, failed_threshold: float) -> str:
    if predicted_semicorr is None:
        return "UNAVAILABLE"
    if predicted_semicorr <= good_threshold:
        return "DIVERSIFICATION_GOOD"
    if predicted_semicorr <= failed_threshold:
        return "DIVERSIFICATION_WEAK"
    return "DIVERSIFICATION_FAILED"


def _spearman(x: pd.Series, y: pd.Series) -> float | None:
    if len(x.dropna()) < 2 or len(y.dropna()) < 2:
        return None
    value = x.corr(y, method="spearman")
    return _float(value)


def _qlike_like(actual: pd.Series, predicted: pd.Series) -> float | None:
    df = pd.DataFrame({"actual": actual, "predicted": predicted}).dropna()
    if df.empty:
        return None
    eps = 1e-10
    ratio = df["actual"].clip(lower=eps) / df["predicted"].clip(lower=eps)
    loss = ratio - np.log(ratio) - 1.0
    return _float(loss.mean())


def _evaluate_predictions(predictions: pd.DataFrame) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    if predictions.empty:
        return summaries
    for (model, window), group in predictions.groupby(["model", "window"]):
        group = group.dropna(subset=["predicted_20d_semicorr", "realized_20d_semicorr"])
        if group.empty:
            continue
        daily_ics = []
        for _, date_group in group.groupby("date"):
            ic = _spearman(date_group["predicted_20d_semicorr"], date_group["realized_20d_semicorr"])
            if ic is not None:
                daily_ics.append(ic)
        sorted_group = group.sort_values("predicted_20d_semicorr")
        bucket_size = max(int(len(sorted_group) * 0.33), 1)
        low_bucket = sorted_group.head(bucket_size)
        high_bucket = sorted_group.tail(bucket_size)
        predicted_failed = group["diversification_state"].eq("DIVERSIFICATION_FAILED")
        realized_failed = group["downside_diversification_failure"].eq(1)
        direction_accuracy = (predicted_failed == realized_failed).mean()
        summaries.append(
            {
                "model": model,
                "window": int(window),
                "observations": int(len(group)),
                "rank_ic_mean": _float(np.mean(daily_ics)) if daily_ics else None,
                "rank_ic_observations": int(len(daily_ics)),
                "mae_semicorr": _float((group["predicted_20d_semicorr"] - group["realized_20d_semicorr"]).abs().mean()),
                "mae_semicov": _float((group["predicted_20d_semicov"] - group["realized_20d_semicov"]).abs().mean(), 10),
                "qlike_like_semicov": _qlike_like(group["realized_20d_semicov"], group["predicted_20d_semicov"]),
                "direction_accuracy_failure_event": _float(direction_accuracy),
                "low_risk_bucket_realized_semicorr": _float(low_bucket["realized_20d_semicorr"].mean()),
                "high_risk_bucket_realized_semicorr": _float(high_bucket["realized_20d_semicorr"].mean()),
                "bucket_ordering_pass": bool(high_bucket["realized_20d_semicorr"].mean() > low_bucket["realized_20d_semicorr"].mean()),
            }
        )
    return summaries


def _economic_filter(predictions: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if predictions.empty:
        return rows
    for (model, window, pair), group in predictions.groupby(["model", "window", "pair"]):
        failed = group[group["diversification_state"].eq("DIVERSIFICATION_FAILED")].dropna(subset=["asset_future_20d_return"])
        if failed.empty:
            rows.append(
                {
                    "model": model,
                    "window": int(window),
                    "pair": pair,
                    "failed_signal_count": 0,
                    "net_filter_value": None,
                    "avoided_downside_if_filter_obeyed": None,
                    "opportunity_cost_if_filter_obeyed": None,
                }
            )
            continue
        cash_return = 0.0
        diff = cash_return - failed["asset_future_20d_return"]
        rows.append(
            {
                "model": model,
                "window": int(window),
                "pair": pair,
                "failed_signal_count": int(len(failed)),
                "net_filter_value": _float(diff.mean()),
                "avoided_downside_if_filter_obeyed": _float(diff.clip(lower=0.0).mean()),
                "opportunity_cost_if_filter_obeyed": _float((-diff).clip(lower=0.0).mean()),
                "asset_future_20d_return_mean_when_failed": _float(failed["asset_future_20d_return"].mean()),
            }
        )
    return rows


def _latest_signals(predictions: pd.DataFrame) -> list[dict[str, Any]]:
    if predictions.empty:
        return []
    latest_date = predictions["date"].max()
    latest = predictions[predictions["date"].eq(latest_date)]
    rows = []
    for _, row in latest.sort_values(["pair", "model", "window"]).iterrows():
        rows.append(
            {
                "date": str(row["date"].date()),
                "pair": row["pair"],
                "predicted_20d_semicorr": _float(row["predicted_20d_semicorr"]),
                "predicted_20d_semicov": _float(row["predicted_20d_semicov"], 10),
                "diversification_state": row["diversification_state"],
                "model": row["model"],
                "window": int(row["window"]),
                "production_effect": "none",
            }
        )
    return rows


def build_shadow(
    *,
    db_path: Path = DB_PATH,
    start: str = "2018-01-02",
    end: str = "latest",
    fifth_candidates: tuple[str, ...] = DEFAULT_FIFTH_CANDIDATES,
    windows: tuple[int, ...] = DEFAULT_WINDOWS,
    forecast_horizon: int = 20,
    oos_lookback_days: int = 252,
    min_history: int = 160,
    ewma_halflife: int = 20,
    shrinkage_alpha: float = 0.25,
    good_threshold: float = 0.25,
    failed_threshold: float = 0.55,
    failure_base_mdd: float = -0.05,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    tickers = tuple(dict.fromkeys([BASE, DEFENSIVE_ASSET, *fifth_candidates]))
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end

    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
    else:
        close = _load_close(db_path, tickers, start, str(end_resolved))
    if close.empty or BASE not in close.columns:
        blockers.append("price_panel_missing_or_base_unavailable")
        returns = pd.DataFrame()
    else:
        close = close.ffill(limit=3)
        returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)

    available = tuple(ticker for ticker in tickers if ticker in returns.columns and int(returns[ticker].notna().sum()) >= min_history)
    if BASE not in available:
        blockers.append("base_has_insufficient_history")
    pairs = [(BASE, asset) for asset in available if asset != BASE]
    if not pairs:
        blockers.append("no_pairs_with_sufficient_history")

    prediction_rows: list[dict[str, Any]] = []
    max_window = max(windows)
    if not blockers:
        model_names = ("historical", "ewma", "shrinkage")
        first_oos_idx = max(max_window, len(returns) - forecast_horizon - oos_lookback_days)
        for idx in range(first_oos_idx, len(returns) - forecast_horizon):
            date = returns.index[idx]
            for window in windows:
                history = returns.iloc[idx - window : idx]
                future = returns.iloc[idx + 1 : idx + 1 + forecast_horizon]
                for left, right in pairs:
                    realized = _downside_stats(future, left, right)
                    base_mdd = _future_mdd(future[left].dropna())
                    asset_return = _cum_return(future[right].dropna())
                    failure = (
                        base_mdd is not None
                        and base_mdd <= failure_base_mdd
                        and asset_return is not None
                        and asset_return < 0.0
                    )
                    for model in model_names:
                        pred = _forecast(
                            history,
                            left,
                            right,
                            model=model,
                            window=window,
                            ewma_halflife=ewma_halflife,
                            shrinkage_alpha=shrinkage_alpha,
                        )
                        prediction_rows.append(
                            {
                                "date": date,
                                "pair": f"{left}_{right}",
                                "asset": right,
                                "model": model,
                                "window": window,
                                "predicted_20d_semicorr": pred["semi_corr"],
                                "predicted_20d_semicov": pred["semi_cov"],
                                "realized_20d_semicorr": realized["semi_corr"],
                                "realized_20d_semicov": realized["semi_cov"],
                                "downside_diversification_failure": int(failure),
                                "base_future_20d_mdd": base_mdd,
                                "asset_future_20d_return": asset_return,
                                "diversification_state": _state(pred["semi_corr"], good_threshold, failed_threshold),
                            }
                        )
    predictions = pd.DataFrame(prediction_rows)
    model_summaries = _evaluate_predictions(predictions)
    economic = _economic_filter(predictions)
    latest = _latest_signals(predictions)

    bucket_passes = [row["bucket_ordering_pass"] for row in model_summaries]
    any_oos_value = bool(bucket_passes and any(bucket_passes))
    if not any_oos_value and not blockers:
        warnings.append("simple_semicovariance_models_show_no_bucket_ordering_value")

    return {
        "schema_version": 1,
        "report_type": "a2118_downside_diversification_forecast_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_monitoring",
        "as_of": str(end_resolved),
        "method_scope": {
            "stage": "stage_2_oos_downside_diversification_forecast_shadow",
            "models": ["historical", "ewma", "shrinkage"],
            "deep_models_allowed": False,
            "downside_dcc_allowed": False,
            "parameter_sweep_allowed": False,
            "target_weight_change_allowed": False,
        },
        "parameters": {
            "base": BASE,
            "defensive_asset": DEFENSIVE_ASSET,
            "fifth_candidates": list(fifth_candidates),
            "windows": list(windows),
            "forecast_horizon": forecast_horizon,
            "oos_lookback_days": oos_lookback_days,
            "min_history": min_history,
            "ewma_halflife": ewma_halflife,
            "shrinkage_alpha": shrinkage_alpha,
            "good_threshold": good_threshold,
            "failed_threshold": failed_threshold,
            "failure_base_mdd": failure_base_mdd,
            "failure_asset_return_threshold": 0.0,
        },
        "coverage": {
            "available_tickers": list(available),
            "pairs": [f"{left}_{right}" for left, right in pairs],
            "prediction_rows": int(len(predictions)),
            "actual_data_start": str(returns.index.min().date()) if not returns.empty else None,
            "actual_data_end": str(returns.index.max().date()) if not returns.empty else None,
        },
        "latest_daily_signals": latest,
        "model_comparison": model_summaries,
        "economic_filter_review": economic,
        "decision": {
            "simple_models_have_oos_bucket_value": any_oos_value,
            "promote_to_live_weights": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "advance_to_downside_dcc_research": any_oos_value,
            "advance_to_transformer_research": False,
            "summary": (
                "Use this only as a shadow gate. DCC is only justified if simple models show OOS bucket ordering; "
                "Transformer/Autoformer remains blocked until simple and DCC forecasts produce economic filter value."
            ),
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_shadow(shadow: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(shadow, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(shadow.get("as_of") or datetime.now().date())
    history_name = f"a2118_downside_diversification_forecast_shadow_{as_of.replace('-', '')}.json"
    (history_dir / history_name).write_text(text + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--fifth-candidates", nargs="*", default=list(DEFAULT_FIFTH_CANDIDATES))
    parser.add_argument("--windows", nargs="*", type=int, default=list(DEFAULT_WINDOWS))
    parser.add_argument("--forecast-horizon", type=int, default=20)
    parser.add_argument("--oos-lookback-days", type=int, default=252)
    parser.add_argument("--min-history", type=int, default=160)
    parser.add_argument("--ewma-halflife", type=int, default=20)
    parser.add_argument("--shrinkage-alpha", type=float, default=0.25)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    shadow = build_shadow(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        fifth_candidates=tuple(args.fifth_candidates),
        windows=tuple(args.windows),
        forecast_horizon=args.forecast_horizon,
        oos_lookback_days=args.oos_lookback_days,
        min_history=args.min_history,
        ewma_halflife=args.ewma_halflife,
        shrinkage_alpha=args.shrinkage_alpha,
    )
    write_shadow(shadow, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(shadow["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
