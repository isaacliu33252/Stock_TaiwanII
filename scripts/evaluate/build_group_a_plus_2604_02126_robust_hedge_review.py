#!/usr/bin/env python3
"""Build a GroupA+ 2604.02126 robust hedge shadow review.

The paper's useful import is a robust minimum-variance hedge ratio that shrinks
the hedge when hedge-instrument variance forecasts are uncertain. This script
keeps it diagnostic-only: it compares standard and robust 0050/00632R hedge
ratios, but never changes GroupA+ target weights or opens 00632R.
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


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2604_02126_robust_hedge_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2604_02126_robust_hedge/history"
DEFAULT_LETF_READINESS = PROJECT_ROOT / "report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json"
DEFAULT_LATEST_STRATEGY = PROJECT_ROOT / "results/group_a_plus_latest_strategy_predict_20260831_from_20260828_total1000000.json"
SOURCE_PAPER = "C:/Users/isaac/Downloads/2604.02126.pdf"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_optional(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def _series_summary(series: pd.Series) -> dict[str, Any]:
    clean = series.dropna()
    if clean.empty:
        return {
            "count": 0,
            "mean": None,
            "std": None,
            "p05": None,
            "p50": None,
            "p95": None,
            "latest": None,
        }
    return {
        "count": int(clean.shape[0]),
        "mean": _finite(clean.mean()),
        "std": _finite(clean.std(ddof=0)),
        "p05": _finite(clean.quantile(0.05)),
        "p50": _finite(clean.quantile(0.50)),
        "p95": _finite(clean.quantile(0.95)),
        "latest": _finite(clean.iloc[-1]),
    }


def _load_close_panel(
    db_path: Path,
    *,
    tickers: list[str],
    start: str,
    as_of: str | None,
) -> pd.DataFrame:
    end_clause = "AND dt <= ?" if as_of else ""
    params: list[Any] = [tickers, start]
    if as_of:
        params.append(as_of)
    query = f"""
        SELECT ticker, dt, close
        FROM ohlcv
        WHERE ticker IN ?
          AND dt >= ?
          {end_clause}
        ORDER BY dt, ticker
    """
    with duckdb.connect(str(db_path), read_only=True) as conn:
        df = conn.execute(query, params).fetchdf()
    if df.empty:
        return pd.DataFrame()
    df["dt"] = pd.to_datetime(df["dt"]).dt.strftime("%Y-%m-%d")
    return df.pivot(index="dt", columns="ticker", values="close").sort_index()


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    clean_denominator = denominator.where(denominator.abs() > 1e-12)
    return numerator / clean_denominator


def _hedge_effectiveness(asset_ret: pd.Series, hedge_ret: pd.Series, *, tail_quantile: float) -> dict[str, Any]:
    frame = pd.DataFrame({"asset": asset_ret, "hedge": hedge_ret}).dropna()
    if frame.shape[0] < 5:
        return {
            "count": int(frame.shape[0]),
            "hedge_effectiveness": None,
            "conditional_hedge_effectiveness": None,
            "hedging_error_return_ratio": None,
        }
    asset_var = frame["asset"].var(ddof=0)
    hedge_var = frame["hedge"].var(ddof=0)
    threshold = frame["asset"].quantile(tail_quantile)
    tail = frame[frame["asset"] < threshold]
    tail_asset_var = tail["asset"].var(ddof=0) if tail.shape[0] > 1 else np.nan
    tail_hedge_var = tail["hedge"].var(ddof=0) if tail.shape[0] > 1 else np.nan
    tail_asset_mean = tail["asset"].mean() if not tail.empty else np.nan
    tail_hedge_mean = tail["hedge"].mean() if not tail.empty else np.nan
    return {
        "count": int(frame.shape[0]),
        "tail_quantile": tail_quantile,
        "tail_threshold_asset_return": _finite(threshold),
        "hedge_effectiveness": _finite(1.0 - hedge_var / asset_var) if asset_var else None,
        "conditional_hedge_effectiveness": _finite(1.0 - tail_hedge_var / tail_asset_var) if tail_asset_var else None,
        "hedging_error_return_ratio": _finite(tail_hedge_mean / tail_asset_mean) if tail_asset_mean else None,
    }


def _strategy_weight(payload: dict[str, Any], ticker: str) -> float | None:
    data = payload.get("data")
    if isinstance(data, dict):
        weights = data.get("target_weights")
        if isinstance(weights, dict) and ticker in weights:
            return _finite(weights.get(ticker))
    weights = payload.get("target_weights")
    if isinstance(weights, dict) and ticker in weights:
        return _finite(weights.get(ticker))
    return None


def _compute_hedges(
    returns: pd.DataFrame,
    *,
    asset_ticker: str,
    hedge_ticker: str,
    window: int,
    uncertainty_window: int,
    max_hedge_weight: float,
    tail_quantile: float,
    evaluation_start: str | None = None,
) -> dict[str, Any]:
    asset = returns[asset_ticker]
    hedge = returns[hedge_ticker]
    realized_var_hedge = hedge.pow(2)
    realized_cov = asset * hedge

    var_forecast = realized_var_hedge.rolling(window).mean().shift(1)
    cov_forecast = realized_cov.rolling(window).mean().shift(1)
    var_residual = realized_var_hedge - var_forecast
    cov_residual = realized_cov - cov_forecast
    theta_var = var_residual.rolling(uncertainty_window).std(ddof=0).shift(1).clip(lower=0.0)
    theta_cov = cov_residual.rolling(uncertainty_window).std(ddof=0).shift(1).clip(lower=0.0)

    standard_ratio = _safe_div(cov_forecast, var_forecast)
    robust_var_ratio = _safe_div(cov_forecast, var_forecast + theta_var)
    robust_full_ratio = np.sign(cov_forecast) * (cov_forecast.abs() - theta_cov).clip(lower=0.0)
    robust_full_ratio = _safe_div(robust_full_ratio, var_forecast + theta_var)

    ratios = {
        "standard": standard_ratio,
        "robust_variance_only": robust_var_ratio,
        "robust_full_box": robust_full_ratio,
    }
    hedge_returns = {name: asset - ratio * hedge for name, ratio in ratios.items()}
    exposures = {name: (-ratio).clip(lower=0.0, upper=max_hedge_weight) for name, ratio in ratios.items()}

    if evaluation_start:
        evaluation_mask = returns.index >= evaluation_start
        asset_eval = asset.loc[evaluation_mask]
        ratios_eval = {name: ratio.loc[evaluation_mask] for name, ratio in ratios.items()}
        hedge_returns_eval = {name: series.loc[evaluation_mask] for name, series in hedge_returns.items()}
        exposures_eval = {name: exposure.loc[evaluation_mask] for name, exposure in exposures.items()}
    else:
        asset_eval = asset
        ratios_eval = ratios
        hedge_returns_eval = hedge_returns
        exposures_eval = exposures

    comparison: dict[str, Any] = {}
    base_turnover = exposures_eval["standard"].diff().abs().dropna().mean()
    base_std = exposures_eval["standard"].dropna().std(ddof=0)
    for name, exposure in exposures_eval.items():
        turnover = exposure.diff().abs()
        std = exposure.dropna().std(ddof=0)
        comparison[name] = {
            "hedge_ratio_summary": _series_summary(ratios_eval[name]),
            "long_inverse_exposure_summary": _series_summary(exposure),
            "mean_abs_daily_turnover": _finite(turnover.mean()),
            "exposure_std": _finite(std),
            "latest_raw_hedge_ratio": _finite(ratios_eval[name].dropna().iloc[-1])
            if not ratios_eval[name].dropna().empty
            else None,
            "latest_long_inverse_exposure": _finite(exposure.dropna().iloc[-1]) if not exposure.dropna().empty else None,
            "turnover_reduction_vs_standard": _finite(1.0 - turnover.mean() / base_turnover)
            if base_turnover and abs(base_turnover) > 1e-12 and name != "standard"
            else None,
            "exposure_std_reduction_vs_standard": _finite(1.0 - std / base_std)
            if base_std and abs(base_std) > 1e-12 and name != "standard"
            else None,
            "effectiveness": _hedge_effectiveness(asset_eval, hedge_returns_eval[name], tail_quantile=tail_quantile),
            "zero_or_near_zero_exposure_rate": _finite((exposure.fillna(0.0) <= 1e-6).mean()),
        }

    common = pd.DataFrame(
        {
            "asset": asset,
            "hedge": hedge,
            "var_forecast": var_forecast,
            "cov_forecast": cov_forecast,
            "theta_var": theta_var,
            "theta_cov": theta_cov,
            "standard_ratio": standard_ratio,
            "robust_variance_only_ratio": robust_var_ratio,
            "robust_full_box_ratio": robust_full_ratio,
            "robust_variance_only_exposure": exposures["robust_variance_only"],
            "robust_full_box_exposure": exposures["robust_full_box"],
        }
    ).dropna()
    if evaluation_start:
        common = common[common.index >= evaluation_start]

    return {
        "window": window,
        "uncertainty_window": uncertainty_window,
        "max_hedge_weight_for_diagnostics": max_hedge_weight,
        "evaluation_start": evaluation_start,
        "observation_count": int(common.shape[0]),
        "data_start_after_warmup": str(common.index.min()) if not common.empty else None,
        "data_end_after_warmup": str(common.index.max()) if not common.empty else None,
        "forecast_proxy_summary": {
            "hedge_variance_forecast": _series_summary(var_forecast),
            "asset_hedge_covariance_forecast": _series_summary(cov_forecast),
            "hedge_variance_uncertainty_theta": _series_summary(theta_var),
            "covariance_uncertainty_theta": _series_summary(theta_cov),
        },
        "method_comparison": comparison,
    }


def build_review(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = None,
    start: str = "2020-01-01",
    asset_ticker: str = "0050.TW",
    hedge_ticker: str = "00632R.TW",
    window: int = 126,
    uncertainty_window: int = 126,
    max_hedge_weight: float = 0.30,
    tail_quantile: float = 0.25,
    evaluation_start: str | None = None,
    letf_readiness_path: Path = DEFAULT_LETF_READINESS,
    latest_strategy_path: Path = DEFAULT_LATEST_STRATEGY,
) -> dict[str, Any]:
    tickers = [asset_ticker, hedge_ticker]
    panel = _load_close_panel(db_path, tickers=tickers, start=start, as_of=as_of)
    close = panel[tickers].dropna() if all(ticker in panel.columns for ticker in tickers) else pd.DataFrame()
    returns = np.log(close / close.shift(1)).dropna() if not close.empty else pd.DataFrame(columns=tickers)
    data_end = str(close.index.max()) if not close.empty else None

    letf_readiness = _load_optional(letf_readiness_path)
    latest_strategy = _load_optional(latest_strategy_path)
    latest_00632r_weight = _strategy_weight(latest_strategy, hedge_ticker)

    if returns.shape[0] >= window + uncertainty_window + 5:
        hedge_review = _compute_hedges(
            returns,
            asset_ticker=asset_ticker,
            hedge_ticker=hedge_ticker,
            window=window,
            uncertainty_window=uncertainty_window,
            max_hedge_weight=max_hedge_weight,
            tail_quantile=tail_quantile,
            evaluation_start=evaluation_start,
        )
    else:
        hedge_review = {
            "window": window,
            "uncertainty_window": uncertainty_window,
            "max_hedge_weight_for_diagnostics": max_hedge_weight,
            "evaluation_start": evaluation_start,
            "observation_count": 0,
            "data_start_after_warmup": None,
            "data_end_after_warmup": None,
            "forecast_proxy_summary": {},
            "method_comparison": {},
        }

    robust = (hedge_review.get("method_comparison") or {}).get("robust_variance_only") or {}
    full_box = (hedge_review.get("method_comparison") or {}).get("robust_full_box") or {}
    robust_latest = _finite(robust.get("latest_long_inverse_exposure"))
    full_box_zero_rate = _finite(full_box.get("zero_or_near_zero_exposure_rate"))

    blockers = [
        "research_only_robust_hedge_review",
        "daily_close_proxy_not_high_frequency_realized_covariance",
        "forecast_uncertainty_proxy_not_paper_exact_ar_har_realized_covariance",
        "live_hedge_policy_not_validated_for_robust_ratio",
        "transaction_cost_and_execution_slippage_not_revalidated",
    ]
    if close.empty or returns.empty:
        blockers.append("missing_required_ohlcv")
    if letf_readiness.get("decision", {}).get("allow_00632r_open") is not True:
        blockers.append("letf_readiness_blocks_00632r_open")
    if full_box_zero_rate is not None and full_box_zero_rate >= 0.80:
        blockers.append("full_box_covariance_uncertainty_too_conservative")

    advisory_exposure = 0.0 if robust_latest is None else min(max(robust_latest, 0.0), max_hedge_weight)
    live_allowed = False

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2604_02126_robust_hedge_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_end": data_end,
        "source_paper": {
            "path": SOURCE_PAPER,
            "title": "Hedging market risk and uncertainty via a robust portfolio approach",
            "arxiv": "2604.02126v2",
            "paper_date": "2026-07-08",
            "imported_concept": "robust dynamic minimum-variance hedge ratio under volatility/covariance forecast uncertainty",
            "paper_formula": "h*=sgn(cov_sf)*(abs(cov_sf)-theta_cov)^+/(var_f+theta_var); variance-only practical case h*=cov_sf/(var_f+theta_var)",
        },
        "policy": "research_only_robust_hedge_no_00632r_open_no_weight_change",
        "status": "blocked_for_live_promotion",
        "data": {
            "db_path": str(db_path),
            "start": start,
            "asset_ticker": asset_ticker,
            "hedge_ticker": hedge_ticker,
            "available_tickers": [ticker for ticker in tickers if ticker in panel.columns and panel[ticker].notna().any()],
            "required_tickers": tickers,
            "return_type": "daily_log_return_from_close",
        },
        "hedge_review": hedge_review,
        "latest_strategy_context": {
            "path": str(latest_strategy_path),
            "latest_strategy_00632r_target_weight": latest_00632r_weight,
            "robust_variance_only_advisory_long_inverse_exposure": _finite(advisory_exposure),
            "advisory_minus_latest_strategy_00632r_weight": _finite(advisory_exposure - latest_00632r_weight)
            if latest_00632r_weight is not None
            else None,
            "advisory_is_cap_only_diagnostic": True,
        },
        "assessment": {
            "paper_advantage_importable_as_shadow": True,
            "best_import_candidate": "robust_variance_only_hedge_ratio",
            "full_box_covariance_uncertainty_importable_now": False,
            "reason_full_box_not_preferred": "The paper itself finds covariance-box uncertainty can make hedge ratios collapse toward zero; keep it as a conservatism diagnostic.",
            "main_expected_benefit": "more stable 00632R hedge sizing and lower hedge-ratio turnover under forecast uncertainty",
            "main_live_blocker": "GroupA+ still lacks validated live inverse-ETF hedge policy and high-frequency realized covariance inputs.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "robust_hedge_review_complete": bool(hedge_review.get("method_comparison")),
            "promote_to_live": live_allowed,
            "target_weight_change_allowed": live_allowed,
            "auto_rebalance_allowed": live_allowed,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "robust_hedge_ratio_can_cap_00632r_shadow": True,
            "robust_hedge_ratio_can_increase_00632r_live": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "letf_tracking_error_effective_fee_readiness": str(letf_readiness_path),
            "latest_strategy_preview": str(latest_strategy_path),
        },
    }


def _history_path(history_dir: Path, as_of: str | None, data_end: str | None) -> Path:
    stamp = str(as_of or data_end or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"2604_02126_robust_hedge_review_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, review.get("as_of"), review.get("actual_data_end")).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--asset-ticker", default="0050.TW")
    parser.add_argument("--hedge-ticker", default="00632R.TW")
    parser.add_argument("--window", type=int, default=126)
    parser.add_argument("--uncertainty-window", type=int, default=126)
    parser.add_argument("--max-hedge-weight", type=float, default=0.30)
    parser.add_argument("--tail-quantile", type=float, default=0.25)
    parser.add_argument("--evaluation-start", default=None)
    parser.add_argument("--letf-readiness", default=str(DEFAULT_LETF_READINESS))
    parser.add_argument("--latest-strategy", default=str(DEFAULT_LATEST_STRATEGY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        db_path=_resolve(args.db),
        as_of=args.as_of,
        start=args.start,
        asset_ticker=args.asset_ticker,
        hedge_ticker=args.hedge_ticker,
        window=args.window,
        uncertainty_window=args.uncertainty_window,
        max_hedge_weight=args.max_hedge_weight,
        tail_quantile=args.tail_quantile,
        evaluation_start=args.evaluation_start,
        letf_readiness_path=_resolve(args.letf_readiness),
        latest_strategy_path=_resolve(args.latest_strategy),
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    robust = ((review.get("hedge_review") or {}).get("method_comparison") or {}).get("robust_variance_only") or {}
    print(f"2604.02126 robust hedge review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "actual_data_end": review["actual_data_end"],
                "robust_latest_00632r_advisory_exposure": review["latest_strategy_context"][
                    "robust_variance_only_advisory_long_inverse_exposure"
                ],
                "robust_turnover_reduction_vs_standard": robust.get("turnover_reduction_vs_standard"),
                "allow_00632r_open": review["decision"]["allow_00632r_open"],
                "blocking_reasons": review["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
